# Copyright (c) 2026-present Half_nothing.

"""路由器, 按事件类型分桶的注册表, 以及一次分派的执行管线。"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Iterable, Mapping
from dataclasses import dataclass, replace
from json import loads
from typing import TYPE_CHECKING, Any

from loguru import logger
from pydantic import BaseModel

from qbotsdk.model.event import EventModel, InteractionCode, InteractionCreate

from .adapters import Invocation, adapt_event
from .context import (
    C2CContext,
    ChannelContext,
    Context,
    GroupContext,
    InteractionContext,
    Kind,
    Sender,
)
from .convert import DEFAULT_CONVERTERS, Converter
from .errors import CommandError, GuardFailed, PermissionDenied, UsageError
from .execution import ExecutionResult, Status
from .messages import Messages
from .reply import Reply
from .route import (
    AckPolicy,
    Binding,
    CallbackHandler,
    CommandHandler,
    PayloadTrigger,
    Route,
    TextTrigger,
    action_of,
    build_binding,
    check_callback_handler,
    event_types,
)
from .template import compile_template
from .trie import Node, Partial, TextMatch, insert, resolve, usage_for

if TYPE_CHECKING:
    from qbotsdk.model.draft import MessageMarkdown
    from qbotsdk.model.keyboard import Keyboard
    from qbotsdk.model.media import MediaInfo
    from qbotsdk.permissions.checker import PermissionChecker
    from qbotsdk.permissions.node import Permission

    from .context import ReplyResult

Middleware = Callable[[Context, Callable[[Context], Awaitable[Reply]]], Awaitable[Reply]]
Guard = Callable[[Context], Awaitable[None]]

# 每种事件对应一个有专属 reply() 签名的上下文子类
_CONTEXT_TYPES: dict[Kind, type[Context]] = {
    "group": GroupContext,
    "c2c": C2CContext,
    "channel": ChannelContext,
    "interaction": InteractionContext,
}

# 文本路由：每个事件类型一棵命令树
_TextTree = dict[type[EventModel], Node]


@dataclass(frozen=True, slots=True)
class _CallbackMatch:
    route: Route
    trigger: PayloadTrigger
    payload: BaseModel | str


def strip_prefix(text: str, prefix: str) -> str | None:
    """剥掉命令前缀；不是以它开头、或剥完为空则返回 None。"""

    stripped = text.lstrip()
    if not stripped.startswith(prefix):
        return None
    remainder = stripped[len(prefix) :].strip()
    return remainder or None


def _permission_key(permission: Permission | str | None) -> str | None:
    if permission is None:
        return None
    key = permission if isinstance(permission, str) else permission.key
    if not key:
        raise ValueError("permission key must not be empty")
    return key


def _mention_openid(ctx: Context) -> str | None:
    """能 @ 到发送者时返回它的 id; 单聊没有可 @ 的对象。"""

    if ctx.kind == "group":
        account = ctx.account
        if account is not None and account.startswith("user:"):
            return account[len("user:") :] or None
        return None
    if ctx.kind == "channel":
        author = getattr(ctx.event, "author", None)
        user_id = getattr(author, "id", None)
        if isinstance(user_id, str) and user_id:
            return user_id
    return None


def _wrap(
    middleware: Middleware, nxt: Callable[[Context], Awaitable[Reply]]
) -> Callable[[Context], Awaitable[Reply]]:
    async def call(ctx: Context) -> Reply:
        return await middleware(ctx, nxt)

    return call


class Router:
    """命令与按钮的注册表, 也是执行入口。

    一条路由声明它属于哪些事件类型；`handle()` 按 `type(event)` 取对应分桶,
    因此同一个路由器可以同时服务群、单聊、频道与互动事件, 而互不干扰。
    """

    def __init__(
        self,
        *,
        prefix: str = "/",
        checker: PermissionChecker | None = None,
        middlewares: Iterable[Middleware] = (),
        guards: Iterable[Guard] = (),
        messages: Messages | None = None,
        converters: Mapping[str, Converter] | None = None,
        strict: bool = False,
        reply_unknown: bool = False,
        reply_mention: bool = True,
    ) -> None:
        """创建路由器。

        Args:
            prefix:     命令前缀, 默认 `/`；传空串表示不剥前缀。
            checker:    权限检查器, 声明了 permission 却没有它时一律拒绝。
            middlewares: 中间件, 按外层到内层的顺序执行。
            guards:     守卫, 在权限检查之前执行。
            messages:   文案集合, 可整体替换或只改某几条。
            converters: 额外的转换器, 与内建的合并, 同名覆盖。
            strict:     True 时注册期校验权限键是否已登记。
            reply_unknown: 前缀命中但没有对应命令时是否回 `messages.unknown_command`。
                        命令层是可选模块, 默认不回, 避免抢先用户的其它回调。
            reply_mention: 回复正文前是否带 @发送者, 默认带；单聊不带, 频道只在 markdown 里带。
        """

        self._prefix = prefix
        self._checker = checker
        self._middlewares: list[Middleware] = list(middlewares)
        self._guards: list[Guard] = list(guards)
        self._messages = messages if messages is not None else Messages()
        self._converters: dict[str, Converter] = dict(DEFAULT_CONVERTERS)
        if converters is not None:
            self._converters.update(converters)
        self._strict = strict
        self._reply_unknown = reply_unknown
        self._reply_mention = reply_mention
        self._text: _TextTree = {}
        self._models: dict[type[EventModel], dict[str, Route]] = {}
        self._literals: dict[type[EventModel], dict[str, Route]] = {}
        self._prefixes: dict[type[EventModel], dict[str, Route]] = {}
        self._routes: list[Route] = []

    @property
    def prefix(self) -> str:
        return self._prefix

    @property
    def checker(self) -> PermissionChecker | None:
        return self._checker

    @property
    def messages(self) -> Messages:
        return self._messages

    @property
    def converters(self) -> Mapping[str, Converter]:
        return self._converters

    @property
    def reply_unknown(self) -> bool:
        """前缀命中但没有对应命令时是否回一句「命令不存在」。"""

        return self._reply_unknown

    @property
    def routes(self) -> tuple[Route, ...]:
        """全部路由, 按注册顺序。"""

        return tuple(self._routes)

    @property
    def reply_mention(self) -> bool:
        """回复正文前是否默认带 @发送者。"""

        return self._reply_mention

    @property
    def commands(self) -> tuple[Route, ...]:
        """按名字排序的文本命令。"""

        return tuple(
            sorted((route for route in self._routes if route.is_command), key=lambda r: r.name)
        )

    @property
    def events(self) -> frozenset[type[EventModel]]:
        """所有路由声明过的事件类型, 用于自检与文档。"""

        merged: set[type[EventModel]] = set()
        for route in self._routes:
            merged.update(route.on)
        return frozenset(merged)

    def add_converter(self, name: str, converter: Converter) -> None:
        """注册自定义转换器, 已注册的模板不受影响。"""

        if not name:
            raise ValueError("converter name must not be empty")
        self._converters[name] = converter

    def use(self, middleware: Middleware) -> Middleware:
        """追加一个中间件, 返回它本身以便当装饰器用。"""

        self._middlewares.append(middleware)
        return middleware

    def guard(self, guard: Guard) -> Guard:
        """追加一个守卫, 返回它本身以便当装饰器用。"""

        self._guards.append(guard)
        return guard

    def command(
        self,
        path: str,
        *,
        on: type[EventModel] | Iterable[type[EventModel]],
        description: str = "",
        usage: str | None = None,
        permission: Permission | str | None = None,
        hidden: bool = False,
        bind_args: bool = True,
        options: Mapping[str, type] | None = None,
        mention: bool | None = None,
    ) -> Callable[[CommandHandler], CommandHandler]:
        """登记一条文本命令, 被装饰的函数就是 handler。

        同一个 handler 可以多次注册来提供多条路径, 每条路径各自校验形参与选项。

        Args:
            path:    命令模板, 例如 `"server <name:str>"`；末尾 `<text:rest>` 吃掉剩余 token。
            on:      这条命令在哪些事件上生效, 群聊要显式区分全量消息与仅 @ 机器人。
            usage:   用法说明, `UsageError` 没有文案时用它。
            permission: 需要的权限键。
            hidden:  不在 `/help` 列表里展示。
            bind_args: False 时不做转换与关键字绑定, handler 收 `argv: list[str]`。
            options: 额外的 `--name` 选项, 值为 bool/int/float/str。
        """

        events = event_types(on)
        key = _permission_key(permission)
        template = compile_template(path, converters=self._converters)
        _check_options(options or {})
        trigger = TextTrigger(template=template, bind_args=bind_args)
        declared = dict(options or {})

        def decorator(handler: CommandHandler) -> CommandHandler:
            binding = build_binding(
                handler,
                template,
                bind_args=bind_args,
                converters=self._converters,
                options=declared,
            )
            route = Route(
                on=events,
                trigger=trigger,
                handler=handler,
                binding=binding,
                permission=key,
                description=description,
                usage=usage,
                hidden=hidden,
                mention=mention,
                options=declared,
            )
            self._check_registry(route)
            self._add_text_route(route)
            return handler

        return decorator

    def button(
        self,
        target: type[BaseModel] | str,
        *,
        on: type[EventModel] | Iterable[type[EventModel]] = InteractionCreate,
        permission: Permission | str | None = None,
        ack: AckPolicy = "pre",
    ) -> Callable[[CallbackHandler], CallbackHandler]:
        """登记一条按钮回调；`target` 是载荷模型或字面量字符串。

        按钮目前只有 `InteractionCreate` 一个来源, `on` 因此有默认值。
        """

        events = event_types(on)
        key = _permission_key(permission)
        if ack not in ("pre", "post", "none"):
            raise ValueError("ack must be 'pre', 'post' or 'none'")
        trigger = (
            PayloadTrigger(key=target)
            if isinstance(target, str)
            else PayloadTrigger(key=action_of(target), model=target)
        )

        def decorator(handler: CallbackHandler) -> CallbackHandler:
            check_callback_handler(handler)
            route = Route(
                on=events,
                trigger=trigger,
                handler=handler,
                permission=key,
                ack=ack,
            )
            self._check_registry(route)
            self._add_payload_route(route)
            return handler

        return decorator

    def button_prefix(
        self,
        prefix: str,
        *,
        on: type[EventModel] | Iterable[type[EventModel]] = InteractionCreate,
        permission: Permission | str | None = None,
        ack: AckPolicy = "pre",
    ) -> Callable[[CallbackHandler], CallbackHandler]:
        """登记前缀回调, 匹配 `action` 形如 `prefix:后缀` 的载荷。"""

        if not prefix:
            raise ValueError("callback prefix must not be empty")
        events = event_types(on)
        key = _permission_key(permission)
        if ack not in ("pre", "post", "none"):
            raise ValueError("ack must be 'pre', 'post' or 'none'")
        trigger = PayloadTrigger(key=prefix, prefix=True)

        def decorator(handler: CallbackHandler) -> CallbackHandler:
            check_callback_handler(handler)
            route = Route(
                on=events,
                trigger=trigger,
                handler=handler,
                permission=key,
                ack=ack,
            )
            self._check_registry(route)
            self._add_payload_route(route)
            return handler

        return decorator

    def include(self, router: Router, *, prefix: str = "") -> None:
        """把另一个路由器整体并进来, 前缀叠加。

        子路由器的中间件与守卫只作用于它自己的路由, 挂到复制出的路由上,
        不会并进当前路由器; 执行时当前路由器的钩子在外, 子路由器钩子在内。
        """

        if router is self:
            raise ValueError("a router cannot include itself")
        if router.prefix not in ("", self._prefix):
            raise ValueError(
                f"cannot include a router with prefix {router.prefix!r} "
                f"into a router with prefix {self._prefix!r}"
            )
        base = tuple(prefix.split())
        if self._checker is None and router._checker is not None:
            self._checker = router._checker
        if router._strict:
            self._strict = True
        for name, converter in router._converters.items():
            self._converters.setdefault(name, converter)

        for route in router._routes:
            inherited = replace(
                route,
                guards=(*router._guards, *route.guards),
                middlewares=(*router._middlewares, *route.middlewares),
            )
            if not isinstance(inherited.trigger, TextTrigger):
                self._check_registry(inherited)
                self._add_payload_route(inherited)
                continue
            source = " ".join(base + tuple(inherited.name.split())) if base else inherited.name
            renamed = replace(
                inherited,
                trigger=replace(
                    inherited.trigger,
                    template=compile_template(source, converters=self._converters),
                ),
            )
            self._check_registry(renamed)
            self._add_text_route(renamed)

    def _add_text_route(self, route: Route) -> None:
        assert isinstance(route.trigger, TextTrigger)
        for event_type in route.on:
            root = self._text.setdefault(event_type, Node())
            insert(root, route.trigger.template, route)
        self._routes.append(route)

    def _add_payload_route(self, route: Route) -> None:
        assert isinstance(route.trigger, PayloadTrigger)
        trigger = route.trigger
        for event_type in route.on:
            if trigger.prefix:
                index = self._prefixes.setdefault(event_type, {})
                label = f"callback prefix {trigger.key!r}"
            elif trigger.model is None:
                index = self._literals.setdefault(event_type, {})
                label = f"callback {trigger.key!r}"
            else:
                index = self._models.setdefault(event_type, {})
                label = f"callback action {trigger.key!r}"
            if trigger.key in index:
                raise ValueError(f"{label} is already registered")
            index[trigger.key] = route
        self._routes.append(route)

    def _check_registry(self, route: Route) -> None:
        if not self._strict or route.permission is None:
            return
        from qbotsdk.permissions.node import permission_registry

        if route.permission not in permission_registry:
            raise ValueError(f"unknown permission {route.permission!r}")

    def match(self, text: str, *, on: type[EventModel]) -> TextMatch | Partial | None:
        """按前缀与命令树匹配一段文本；返回值可能是命中、缺参数或未命中。"""

        remainder = strip_prefix(text, self._prefix)
        if remainder is None:
            return None
        root = self._text.get(on)
        if root is None:
            return None
        return resolve(root, remainder.split())

    def _match_callback(self, on: type[EventModel], data: str | None) -> _CallbackMatch | None:
        if not data:
            return None
        try:
            parsed = loads(data)
        except ValueError:
            parsed = None
        if isinstance(parsed, dict):
            action = parsed.get("action")
            if isinstance(action, str):
                route = self._models.get(on, {}).get(action)
                if route is not None:
                    trigger = _payload_trigger(route)
                    if trigger.model is not None:
                        try:
                            payload = trigger.model.model_validate(parsed)
                        except ValueError:
                            logger.warning(
                                "Ignoring button payload that failed validation: {}", data
                            )
                        else:
                            return _CallbackMatch(route, trigger, payload)
        route = self._literals.get(on, {}).get(data)
        if route is not None:
            return _CallbackMatch(route, _payload_trigger(route), data)
        for prefix, route in self._prefixes.get(on, {}).items():
            if data.startswith(f"{prefix}:"):
                return _CallbackMatch(route, _payload_trigger(route), data)
        return None

    async def handle(self, event: EventModel) -> ExecutionResult:
        """处理一条事件并返回执行结果。

        调用方在自己的事件回调里手动调用它；
        未命中任何路由时 `handled` 为 False,
        路由器不会发送任何东西
        """

        invocation = adapt_event(event)
        if invocation is None:
            return ExecutionResult()
        if invocation.kind == "interaction":
            return await self._handle_interaction(invocation)
        return await self._handle_text(invocation)

    async def _handle_text(self, invocation: Invocation) -> ExecutionResult:
        found = self.match(invocation.text, on=type(invocation.event))
        if isinstance(found, Partial):
            return await self._handle_partial(invocation, found)
        if found is None:
            return await self._handle_unknown(invocation)
        match = found
        route = match.route

        async def action(inner: Context) -> Reply:
            result = await self._invoke_command(inner, match)
            return self._to_reply(result, kind="command")

        ctx = self._context(invocation, command=route.name, route=route)
        reply, status, error = await self._execute(
            ctx,
            permission=route.permission,
            ack="none",
            action=action,
            guards=route.guards,
            middlewares=route.middlewares,
        )
        await self._send(ctx, reply, mention=route.mention)
        return self._result(
            ctx, status=status, command=route.name, handler=route.handler, reply=reply, error=error
        )

    async def _handle_partial(self, invocation: Invocation, partial: Partial) -> ExecutionResult:
        """停在有子节点却没有 handler 的节点上, 回一句用法。"""

        usage = usage_for(partial, prefix=self._prefix)
        if usage is None:
            return await self._handle_unknown(invocation)
        command = " ".join(partial.path)
        ctx = self._context(invocation, command=command)
        reply = Reply(text=self._messages.usage.format(usage=usage))
        await self._send(ctx, reply)
        return self._result(
            ctx,
            status=Status.FAILED,
            command=command,
            reply=reply,
            error=UsageError(),
        )

    async def _handle_unknown(self, invocation: Invocation) -> ExecutionResult:
        """前缀命中却查不到命令时的可选提示；普通聊天文本仍然静默。"""

        if not self._reply_unknown:
            return ExecutionResult()
        if strip_prefix(invocation.text, self._prefix) is None:
            return ExecutionResult()
        text = self._messages.unknown_command
        if not text:
            return ExecutionResult()
        ctx = self._context(invocation, command=None)
        await self._send(ctx, Reply(text=text), mention=False)
        return self._result(ctx, status=Status.NOT_FOUND, command=None, reply=None, error=None)

    async def _handle_interaction(self, invocation: Invocation) -> ExecutionResult:
        match = self._match_callback(type(invocation.event), invocation.button_data)
        if match is None:
            return ExecutionResult()
        route = match.route

        async def action(inner: Context) -> Reply:
            result = await self._invoke_callback(inner, match)
            return self._to_reply(result, kind="callback")

        ctx = self._context(invocation, command=route.name, route=route)
        reply, status, error = await self._execute(
            ctx,
            permission=route.permission,
            ack=route.ack,
            action=action,
            guards=route.guards,
            middlewares=route.middlewares,
        )
        await self._send(ctx, reply)
        return self._result(
            ctx, status=status, command=route.name, handler=route.handler, reply=reply, error=error
        )

    def _context(
        self, invocation: Invocation, *, command: str | None, route: Route | None = None
    ) -> Context:
        context_type = _CONTEXT_TYPES[invocation.kind]
        ctx = context_type(
            event=invocation.event,
            kind=invocation.kind,
            principal=invocation.principal,
            account=invocation.account,
            api=invocation.event.api,
            mentions=invocation.mentions,
            command=command,
            route=route,
        )
        ctx._sender = self._delivery(ctx, invocation)
        return ctx

    def _delivery(self, ctx: Context, invocation: Invocation) -> Sender:
        """按事件类型组装投递函数, 顺带把「已经回过」记到上下文里。"""

        if ctx.kind == "interaction":

            async def acknowledge(
                content: str | None = None,
                *,
                markdown: MessageMarkdown | None = None,
                media: MediaInfo | None = None,
                image: str | None = None,
                keyboard: Keyboard | None = None,
                msg_seq: int | None = None,
            ) -> ReplyResult | None:
                await self._respond(ctx, InteractionCode.OK)
                return None

            return acknowledge

        sender = invocation.sender
        if sender is None:
            raise RuntimeError("message events must provide a sender")

        async def tracked(
            content: str | None = None,
            *,
            markdown: MessageMarkdown | None = None,
            media: MediaInfo | None = None,
            image: str | None = None,
            keyboard: Keyboard | None = None,
            msg_seq: int | None = None,
        ) -> ReplyResult | None:
            result = await sender(
                content,
                markdown=markdown,
                media=media,
                image=image,
                keyboard=keyboard,
                msg_seq=msg_seq,
            )
            ctx.state["replied"] = True
            return result

        return tracked

    async def _execute(
        self,
        ctx: Context,
        *,
        permission: str | None,
        ack: AckPolicy,
        action: Callable[[Context], Awaitable[Reply]],
        guards: tuple[Guard, ...] = (),
        middlewares: tuple[Middleware, ...] = (),
    ) -> tuple[Reply, Status, CommandError | None]:
        interaction = ctx.kind == "interaction"

        async def core(inner: Context) -> Reply:
            for guard in self._guards:
                await guard(inner)
            for guard in guards:
                await guard(inner)
            if permission is not None:
                await self._authorize(inner, permission)
            if interaction and ack == "pre":
                await self._respond(inner, InteractionCode.OK)
            reply = await action(inner)
            if interaction and ack == "post":
                await self._respond(inner, InteractionCode.OK)
            return reply

        chain: Callable[[Context], Awaitable[Reply]] = core
        for middleware in reversed((*self._middlewares, *middlewares)):
            chain = _wrap(middleware, chain)
        try:
            reply = await chain(ctx)
        except CommandError as exc:
            await self._on_error(ctx, exc)
            status = (
                Status.DENIED if isinstance(exc, (PermissionDenied, GuardFailed)) else Status.FAILED
            )
            return self._map_error(ctx, exc), status, exc
        except Exception as exc:
            logger.exception("Command handler failed")
            await self._on_error(ctx, exc)
            return (
                Reply(text=self._messages.internal_error),
                Status.FAILED,
                CommandError(str(exc)),
            )
        return reply, Status.HANDLED, None

    def _result(
        self,
        ctx: Context,
        *,
        status: Status,
        command: str | None,
        reply: Reply | None,
        error: CommandError | None,
        handler: Callable[..., Awaitable[object]] | None = None,
    ) -> ExecutionResult:
        return ExecutionResult(
            status=status,
            command=command,
            handler=handler,
            reply=reply,
            replied=bool(ctx.state.get("replied")),
            error=error,
        )

    async def _authorize(self, ctx: Context, permission: str) -> None:
        if self._checker is None:
            logger.warning(
                "Command declares permission {!r} but the router has no checker", permission
            )
            await self._respond(ctx, InteractionCode.NO_PERMISSION)
            raise PermissionDenied()
        if not await self._checker.allows(ctx.principal, permission):
            await self._respond(ctx, InteractionCode.NO_PERMISSION)
            raise PermissionDenied()

    async def _respond(self, ctx: Context, code: InteractionCode) -> None:
        event = ctx.event
        if not isinstance(event, InteractionCreate) or not event.needs_response:
            return
        if ctx.state.get("responded"):
            return
        ctx.state["responded"] = True
        ctx.state["replied"] = True
        await event.respond(code)

    async def _on_error(self, ctx: Context, exc: Exception) -> None:
        if ctx.kind == "interaction" and not isinstance(exc, PermissionDenied):
            await self._respond(ctx, InteractionCode.FAILED)

    def _map_error(self, ctx: Context, exc: CommandError) -> Reply:
        if isinstance(exc, PermissionDenied):
            return Reply(text=self._messages.denied)
        if isinstance(exc, UsageError):
            if exc.message:
                return Reply(text=exc.message)
            usage = self._usage(ctx.command)
            return Reply(text=usage if usage else self._messages.missing_arguments)
        return Reply(text=exc.user_message or self._messages.internal_error)

    async def _send(self, ctx: Context, reply: Reply, *, mention: bool | None = None) -> None:
        if not reply.should_send or ctx.state.get("replied"):
            return
        if isinstance(ctx, InteractionContext):
            await ctx.reply()
            return
        if reply.text is None:
            return
        from qbotsdk.model.draft import MessageMarkdown

        marked = self._with_mention(ctx, reply, mention)
        markdown_text = marked if marked is not None else (reply.text if reply.markdown else None)
        markdown = MessageMarkdown(content=markdown_text) if markdown_text is not None else None
        if isinstance(ctx, ChannelContext):
            await ctx.reply(reply.text, markdown=markdown)
        elif isinstance(ctx, (GroupContext, C2CContext)):
            await ctx.reply(marked or reply.text, markdown=markdown, keyboard=reply.keyboard)
        else:
            await ctx.reply(reply.text)

    def _with_mention(self, ctx: Context, reply: Reply, mention: bool | None) -> str | None:
        """按「回复自己的设置 → 命令的设置 → 路由器的默认」决定是否在正文前 @。

        返回带 @ 标记的正文；不需要 @ 时返回 `None`。@ 只在 markdown 消息里生效，
        所以返回了正文时调用方要按 markdown 发送。
        """

        enabled = reply.mention if reply.mention is not None else mention
        if enabled is None:
            enabled = self._reply_mention
        if not enabled or reply.text is None:
            return None
        openid = _mention_openid(ctx)
        if openid is None:
            return None
        return f'<qqbot-at-user id="{openid}" />\n{reply.text}'

    def _usage(self, command: str | None) -> str | None:
        if command is None:
            return None
        for route in self._routes:
            if route.is_command and route.name == command:
                usage = route.usage if route.usage is not None else f"{self._prefix}{command}"
                return self._messages.usage.format(usage=usage)
        return None

    def _to_reply(self, result: object, *, kind: str) -> Reply:
        if isinstance(result, Reply):
            return result
        raise TypeError(f"{kind} handlers must return Reply, got {type(result).__name__}")

    async def _invoke_command(self, ctx: Context, match: TextMatch) -> object:
        route = match.route
        trigger = route.trigger
        assert isinstance(trigger, TextTrigger)
        template = match.template
        binding = route.binding
        assert binding is not None
        if not trigger.bind_args:
            argv = [*match.values, *match.rest]
            ctx.raw_args = tuple(argv)
            kwargs: dict[str, Any] = {}
            if binding.argv_param is not None:
                kwargs[binding.argv_param] = argv
            if binding.ctx_param is not None:
                kwargs[binding.ctx_param] = ctx
            return await route.handler(**kwargs)

        values: dict[str, object] = {}
        for index, placeholder in enumerate(template.params):
            raw = match.values[index]
            converter = self._converters[placeholder.converter]
            try:
                values[placeholder.name] = converter.parse(raw)
            except (TypeError, ValueError):
                raise UsageError(
                    f"Invalid value for <{placeholder.name}>: "
                    f"expected {placeholder.converter}, got {raw!r}."
                ) from None
        rest_placeholder = template.rest
        if rest_placeholder is not None:
            values[rest_placeholder.name] = tuple(match.rest)

        kwargs = {name: values[name] for name in binding.kwargs}
        kwargs.update(self._option_kwargs(route, match.options, binding))
        if binding.ctx_param is not None:
            kwargs[binding.ctx_param] = ctx
        ctx.args = values
        ctx.raw_args = (*match.values, *match.rest)
        return await route.handler(**kwargs)

    def _option_kwargs(
        self, route: Route, parsed: Mapping[str, object], binding: Binding
    ) -> dict[str, object]:
        """校验并转换 `--` 选项, 缺席的交给 handler 的默认值。"""

        declared = route.options
        for name in parsed:
            if name not in declared:
                raise UsageError(f"Unknown option --{name}.")
        converted: dict[str, object] = {}
        for name, kind in declared.items():
            if name not in parsed:
                continue
            raw = parsed[name]
            if kind is bool:
                if raw is not True:
                    raise UsageError(f"Option --{name} does not take a value.")
                converted[name] = True
                continue
            if raw is True:
                raise UsageError(f"Option --{name} requires a value.")
            try:
                converted[name] = kind(raw)
            except (TypeError, ValueError):
                raise UsageError(
                    f"Invalid value for --{name}: expected {kind.__name__}, got {raw!r}."
                ) from None
        return {param: converted[name] for name, param in binding.options if name in converted}

    async def _invoke_callback(self, ctx: Context, match: _CallbackMatch) -> object:
        return await match.route.handler(ctx, match.payload)


def _payload_trigger(route: Route) -> PayloadTrigger:
    trigger = route.trigger
    if not isinstance(trigger, PayloadTrigger):
        raise TypeError("route is not a payload route")
    return trigger


def _check_options(options: Mapping[str, type]) -> None:
    for name, kind in options.items():
        if not name or not name.replace("-", "").isidentifier():
            raise TypeError(f"option name {name!r} is not a valid identifier")
        if kind not in (bool, int, float, str):
            raise TypeError(f"option {name!r} must be bool, int, float or str")


__all__ = [
    "Guard",
    "Middleware",
    "Router",
    "strip_prefix",
]
