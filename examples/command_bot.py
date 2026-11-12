# Copyright (c) 2026-present Half_nothing.

"""命令与权限示例: 事件一等公民、命令树、参数绑定、-- 选项、权限与按钮回调

环境变量:
    QQ_BOT_APP_ID / QQ_BOT_APP_SECRET  机器人凭证, 必填
    QQ_BOT_OWNER                       可选, 启动时授这个人 permission.*, 写完整主体,
                                       如 group:group-openid:member-openid 或 user:openid
    QQ_BOT_PERMISSION_FILE             可选, 权限落盘的 JSON 路径
    QQ_BOT_REDIS_URL                   可选, 权限与会话都走 Redis, 优先于上面两个
    QQ_BOT_SESSION_FILE                可选, 会话落盘路径, 默认 .qbotsdk/session.json

群里发这些指令:
    /ping                    无权限要求
    /echo 随便 什么 文本       bind_args=False, 原样拿到 argv
    /roll                    不带参数
    /roll 20                 带参数, 两条注册表达「可选参数」
    /greet 小明 --loud --times=3     `--` 选项, 注册时声明类型、自动绑到形参
    /me                      打印场景键与账号键
    /help                    列出自己有权限用的命令
    /button                  回一条带回调按钮的消息
    /vote                    回一条前缀回调按钮的消息, 载荷形如 vote:yes
    /shout 你好              自定义转换器, 注册成 upper 后把参数转大写
    /secret                  需要 demo.ping, 点过按钮才会被授权
    /admin ban <@某人>        需要 demo.admin, 来自 include 进来的子路由器
    /math add 1 2            子路由器 include 进来, 前缀叠加

    频道里发 /say 你好: 频道消息走 ChannelContext, 只能用 markdown 与 image,
    没有键盘、也没有 msg_seq。

    单聊发 /ping、/help 也能用: 同一条命令可以同时注册在多个事件类型上。

    /permission show         查看自己的权限
    /permission grant @某人 demo.admin   需要机器人开启「接收全部群消息」才能拿到 @ 信息
    /permission role add <角色> <权限>    角色是权限的集合, 可以继承
"""

import asyncio
import os
import random
import sys
import time
from collections.abc import Awaitable, Callable
from typing import Literal

from async_event_bus import EventContext
from loguru import logger
from pydantic import BaseModel

from qbotsdk import Bot
from qbotsdk.adapter import WebSocketAdapter
from qbotsdk.commands import (
    ChannelContext,
    Context,
    GroupContext,
    GuardFailed,
    InteractionContext,
    Messages,
    Reply,
    Router,
    UsageError,
)
from qbotsdk.model.event import (
    C2CMessageCreate,
    ChannelMessageCreate,
    GroupMessageCreate,
    InteractionCreate,
)
from qbotsdk.model.keyboard import (
    Button,
    ButtonAction,
    ButtonActionType,
    ButtonPermission,
    ButtonPermissionType,
    ButtonRenderData,
    ButtonStyle,
    Keyboard,
    KeyboardContent,
    KeyboardRow,
)
from qbotsdk.permissions import (
    Grant,
    Permission,
    PermissionChecker,
    PermissionGroup,
    install_permission_commands,
)
from qbotsdk.permissions.store import (
    CachedPermissionStorage,
    FilePermissionStorage,
    MemoryPermissionStorage,
    PermissionStorage,
)
from qbotsdk.storage import FileSessionStorage, RedisSessionStorage

logger.remove()
logger.add(sys.stderr, level="TRACE")

# 文本命令默认挂的事件: 群全量与单聊各有一棵树, 互不干扰。
# 想同时响应多种事件就一起写上, handler 的 ctx 标基类 Context。
TEXT_EVENTS = (GroupMessageCreate, C2CMessageCreate)


class Demo(PermissionGroup, namespace="demo"):
    """示例权限键: demo.ping、demo.admin, 声明在类体里, 导入即注册。"""

    PING = Permission("ping", "点过按钮才拿得到的演示权限")
    ADMIN = Permission("admin", "管理命令, 可继承")


class ClickPayload(BaseModel):
    """按钮载荷;`action` 用 Literal 声明, 路由器靠它把回调分给本模型。"""

    action: Literal["demo.click"]
    note: str = ""


def build_store() -> CachedPermissionStorage:
    """权限存储: Redis > 文件 > 内存, 外层统一套一层缓存。"""

    redis_url = os.environ.get("QQ_BOT_REDIS_URL")
    path = os.environ.get("QQ_BOT_PERMISSION_FILE")
    store: PermissionStorage
    if redis_url:
        # 惰性导入: 没装 qbotsdk[redis] 时只有走到这里才会报错
        from qbotsdk.permissions.store import RedisPermissionStorage

        store = RedisPermissionStorage.from_url(redis_url)
    elif path:
        store = FilePermissionStorage(path)
    else:
        store = MemoryPermissionStorage()
    return CachedPermissionStorage(store)


def build_adapter() -> WebSocketAdapter:
    """长连接适配器: 会话信息同样可以放 Redis 或文件。"""

    redis_url = os.environ.get("QQ_BOT_REDIS_URL")
    if redis_url:
        return WebSocketAdapter(session_storage=RedisSessionStorage.from_url(redis_url))
    path = os.environ.get("QQ_BOT_SESSION_FILE", ".qbotsdk/session.json")
    return WebSocketAdapter(session_storage=FileSessionStorage(path))


def build_keyboard() -> Keyboard:
    """一个回调按钮, 点击后走 INTERACTION_CREATE。"""

    button = Button(
        id="click",
        render_data=ButtonRenderData(label="点我", visited_label="点过了", style=ButtonStyle.BLUE),
        action=ButtonAction(
            type=ButtonActionType.CALLBACK,
            data=ClickPayload(action="demo.click", note="按钮示例").model_dump_json(),
            permission=ButtonPermission(type=ButtonPermissionType.EVERYONE),
        ),
    )
    return Keyboard(content=KeyboardContent(rows=[KeyboardRow(buttons=[button])]))


class UppercaseConverter:
    """自定义转换器: 只要 `annotation` 与一个静态方法 `parse`。

    注册的是类本身, 不用实例化;转换器拿不到事件, 转换失败就抛异常, 路由器会把它变成用法提示。
    """

    annotation = str

    @staticmethod
    def parse(raw: str) -> str:
        return raw.upper()


def build_vote_keyboard() -> Keyboard:
    """前缀回调按钮: 载荷可以是任意字符串, 命中 `vote:` 前缀就算这个回调。"""

    buttons = [
        Button(
            id=f"vote-{value}",
            render_data=ButtonRenderData(label=label, visited_label="已投", style=ButtonStyle.GREY),
            action=ButtonAction(
                type=ButtonActionType.CALLBACK,
                data=f"vote:{value}",
                permission=ButtonPermission(type=ButtonPermissionType.EVERYONE),
            ),
        )
        for value, label in (("yes", "同意"), ("no", "反对"))
    ]
    return Keyboard(content=KeyboardContent(rows=[KeyboardRow(buttons=buttons)]))


async def timing(ctx: Context, call_next: Callable[[Context], Awaitable[Reply]]) -> Reply:
    """中间件: 包住匹配之后的整条管线, 异常照常往上抛。"""

    started = time.perf_counter()
    reply = await call_next(ctx)
    logger.info(
        "command {} took {:.1f}ms",
        ctx.command or ctx.kind,
        (time.perf_counter() - started) * 1000,
    )
    return reply


async def require_group(ctx: Context) -> None:
    """守卫: 在进入 handler 之前拒绝整类场景。"""

    if ctx.kind != "group":
        raise GuardFailed("admin commands only work in groups")


def build_router(store: CachedPermissionStorage) -> Router:
    """一个路由器装下所有命令;子路由器通过 include 并进来。"""

    checker = PermissionChecker(store)
    router = Router(
        checker=checker,
        reply_unknown=True,
        # 内置文案可以整条替换;这里演示只换「未知命令」那一句
        messages=Messages(unknown_command="没有这条命令, 发 /help 看看。"),
    )
    router.use(timing)
    router.add_converter("upper", UppercaseConverter)
    install_permission_commands(router, store)

    @router.command("ping", on=TEXT_EVENTS, description="回 pong")
    async def ping(ctx: Context) -> Reply:
        return Reply(text="pong")

    @router.command(
        "echo <text:rest>",
        on=GroupMessageCreate,
        bind_args=False,
        usage="echo <text:rest>",
        description="原样回显",
    )
    async def echo(ctx: GroupContext, argv: list[str]) -> Reply:
        # bind_args=False: <text:rest> 收到的 token 原样进 argv, 转换与关键字绑定都跳过
        return Reply(text=" ".join(argv) or "(空)")

    @router.command("roll", on=TEXT_EVENTS, usage="roll [<sides:int>]", description="掷骰子")
    async def roll(ctx: Context) -> Reply:
        # 可选参数靠注册第二条命令表达, 不在模板里写默认值
        return Reply(text=f"掷出了 {random.randint(1, 6)}")

    @router.command(
        "roll <sides:int>",
        on=TEXT_EVENTS,
        usage="roll [<sides:int>]",
        description="掷指定面数的骰子",
    )
    async def roll_sides(ctx: Context, sides: int) -> Reply:
        if sides < 2:
            # UsageError 回用法行, 其它异常统一回 internal_error
            raise UsageError("sides must be at least 2")
        return Reply(text=f"掷出了 {random.randint(1, sides)}")

    @router.command(
        "greet <name:str>",
        on=GroupMessageCreate,
        options={"loud": bool, "times": int},
        usage="greet <name> [--loud] [--times=3]",
        description="演示 -- 选项",
    )
    async def greet(ctx: GroupContext, name: str, *, loud: bool = False, times: int = 1) -> Reply:
        # 选项在注册时声明类型, 匹配阶段收走 --loud / --times=3, 转换后按名字绑到这里
        lines = [f"你好, {name}!" if not loud else f"你好, {name}!".upper()]
        return Reply(text="\n".join(lines * max(1, min(times, 5))))

    @router.command("me", on=TEXT_EVENTS, description="看看自己的权限主体")
    async def me(ctx: Context) -> Reply:
        account = ctx.account or "(频道不参与账号级)"
        return Reply(text=f"场景键 `{ctx.principal}`\n账号键 `{account}`", markdown=True)

    @router.command("help", on=TEXT_EVENTS, description="列出可用命令")
    async def help_command(ctx: Context) -> Reply:
        lines: list[str] = []
        seen: set[str] = set()
        checker = router.checker
        for route in router.commands:
            if route.hidden:
                continue
            if (
                route.permission is not None
                and checker is not None
                and not await checker.allows(ctx.principal, route.permission)
            ):
                continue
            usage = route.usage or route.name
            if usage in seen:
                # 同一个 handler 注册了两条路径时, usage 可能一样
                continue
            seen.add(usage)
            lines.append(f"/{usage}  {route.description}".rstrip())
        return Reply(text="\n".join(lines) or "没有可用的命令")

    @router.command("button", on=GroupMessageCreate, description="发一条带按钮的消息")
    async def button(ctx: GroupContext) -> Reply:
        return Reply(text="点一下按钮", keyboard=build_keyboard())

    @router.command("vote", on=GroupMessageCreate, description="发一条前缀回调按钮")
    async def vote(ctx: GroupContext) -> Reply:
        return Reply(text="投一票", keyboard=build_vote_keyboard())

    @router.command(
        "shout <text:upper>",
        on=TEXT_EVENTS,
        usage="shout <text>",
        description="自定义转换器, 把参数转大写",
    )
    async def shout(ctx: Context, text: str) -> Reply:
        return Reply(text=text)

    @router.command(
        "say <text:rest>",
        on=ChannelMessageCreate,
        usage="say <text>",
        description="频道消息只能用 markdown 与 image",
    )
    async def say(ctx: ChannelContext, text: tuple[str, ...]) -> Reply:
        # ChannelContext.reply 只接受 content / markdown / image, 传键盘会被类型检查拦下
        return Reply(text=f"**{' '.join(text)}**", markdown=True)

    @router.command(
        "secret",
        on=TEXT_EVENTS,
        permission=Demo.PING,
        description="需要 demo.ping",
    )
    async def secret(ctx: Context) -> Reply:
        return Reply(text="按钮回调已经把 demo.ping 授给你了")

    @router.button(ClickPayload, ack="pre")
    async def on_click(ctx: InteractionContext, payload: ClickPayload) -> Reply:
        # 互动事件发不出消息;ack="pre" 已经替我们回了 OK, 这里只做业务
        await store.grant(ctx.principal, Grant(Demo.PING.key))
        logger.info("button clicked by {} note={}", ctx.principal, payload.note)
        return Reply.ok()

    @router.button_prefix("vote", ack="pre")
    async def on_vote(ctx: InteractionContext, payload: str) -> Reply:
        # 前缀回调拿到的就是原始 data, 这里形如 vote:yes;
        # ack="pre" 会先替我们回 OK, handler 只写日志
        _, _, value = payload.partition(":")
        logger.info("{} voted {}", ctx.principal, value)
        return Reply.ok()

    # 子路由器: include 时前缀叠加, 父级的 checker 与中间件会继承下去
    math = Router()

    @math.command("add <a:int> <b:int>", on=GroupMessageCreate, description="加法")
    async def add(ctx: GroupContext, a: int, b: int) -> Reply:
        return Reply(text=f"{a} + {b} = {a + b}")

    router.include(math, prefix="math")

    # 管理员子路由器: 守卫挂在它自己身上, include 后只作用于这里的路由
    admin = Router()
    admin.guard(require_group)

    @admin.command(
        "ban <member:mention>",
        on=(GroupMessageCreate, C2CMessageCreate),
        permission=Demo.ADMIN,
        usage="admin ban <@成员>",
        description="踢人(演示用)",
    )
    async def ban(ctx: Context, member: str) -> Reply:
        return Reply(text=f"ban {member}")

    router.include(admin, prefix="admin")

    return router


async def main() -> None:
    store = build_store()
    router = build_router(store)

    # 第一个管理员: /permission grant 要 permission.grant, 没有这一行就只能手动塞存储;
    # 授 permission.* 等于把 show / grant / revoke / role 四个键一起给
    owner = os.environ.get("QQ_BOT_OWNER", "").strip()
    if owner:
        await store.grant(owner, Grant("permission.*"))
        logger.info("bootstrapped permission.* for {}", owner)

    async with Bot(
        app_id=os.environ["QQ_BOT_APP_ID"],
        app_secret=os.environ["QQ_BOT_APP_SECRET"],
        adapter=build_adapter(),
    ) as bot:
        # 命令层不自己订阅事件: 在自己的回调里决定要不要交给它,
        # 这样同一个事件还能先做记录、过滤或别的处理。
        # 多个 Router 就按顺序试, 前一个返回 not_found 再交给下一个。
        @bot.on(GroupMessageCreate)
        async def on_group_message(ctx: EventContext[GroupMessageCreate]) -> None:
            result = await router.handle(ctx.event)
            if not result.handled:
                logger.debug("not a command: {}", ctx.event.content)
            else:
                logger.info("group command {} -> {}", result.command, result.status)

        @bot.on(C2CMessageCreate)
        async def on_c2c_message(ctx: EventContext[C2CMessageCreate]) -> None:
            result = await router.handle(ctx.event)
            if not result.handled:
                logger.debug("not a command (c2c): {}", ctx.event.content)

        @bot.on(ChannelMessageCreate)
        async def on_channel_message(ctx: EventContext[ChannelMessageCreate]) -> None:
            # 频道消息同样交给同一个路由器: 命令按事件类型分树, 互不干扰
            result = await router.handle(ctx.event)
            if not result.handled:
                logger.debug("not a command (channel): {}", ctx.event.content)

        @bot.on(InteractionCreate)
        async def on_interaction(ctx: EventContext[InteractionCreate]) -> None:
            result = await router.handle(ctx.event)
            if not result.handled:
                logger.debug("unclaimed button: {}", ctx.event.data)

        await bot.start()
        print("已连接, 群里试 /ping、/roll 20、/greet 小明 --loud、/echo 你好、/help")
        print("  /button 之后用 /secret 看动态授权;/math add 1 2 看 include")
        print("  /permission grant @某人 demo.admin   # 需要机器人开启接收全部群消息")
        await bot.wait_for_exit()


if __name__ == "__main__":
    asyncio.run(main())
