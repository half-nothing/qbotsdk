# Copyright (c) 2026-present Half_nothing.

"""执行管线：绑定、错误映射、权限、中间件与守卫。"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from qbotsdk.commands import (
    Context,
    ExecutionResult,
    GroupContext,
    GuardFailed,
    Messages,
    Reply,
    Router,
    Status,
    UsageError,
)
from qbotsdk.model.event import GroupMessageCreate
from qbotsdk.permissions import Grant, MemoryPermissionStorage, PermissionChecker
from tests.commands.support import FakeApi, group_event

ON = GroupMessageCreate


async def test_command_replies_and_reports_the_execution() -> None:
    router = Router()

    @router.command("ping", on=ON)
    async def ping(ctx: Context) -> Reply:
        return Reply(text="pong")

    event = group_event("/ping")
    result = await router.handle(event)

    assert isinstance(result, ExecutionResult)
    assert result.status is Status.HANDLED
    assert result.command == "ping"
    assert result.reply is not None
    assert result.reply.text == "pong"
    assert result.replied is True
    assert result.error is None
    assert bool(result) is True
    assert isinstance(event.api, FakeApi)
    assert event.api.group.calls[0]["content"] == "pong"


async def test_handler_receives_converted_arguments() -> None:
    router = Router()

    @router.command("repeat <count:int> <word>", on=ON)
    async def repeat(ctx: Context, count: int, word: str) -> Reply:
        return Reply(text=f"{word}*{count}")

    event = group_event("/repeat 3 hi")
    await router.handle(event)

    assert isinstance(event.api, FakeApi)
    assert event.api.group.calls[0]["content"] == "hi*3"


async def test_conversion_failure_reports_the_placeholder() -> None:
    router = Router()

    @router.command("repeat <count:int>", on=ON)
    async def repeat(ctx: Context, count: int) -> Reply:
        return Reply(text="ok")

    event = group_event("/repeat abc")
    result = await router.handle(event)

    assert result.status is Status.FAILED
    assert result.error is not None
    assert isinstance(event.api, FakeApi)
    assert event.api.group.calls[0]["content"] == (
        "Invalid value for <count>: expected int, got 'abc'."
    )


async def test_mention_placeholder_strips_the_rendered_marker() -> None:
    router = Router()

    @router.command("kick <member:mention>", on=ON)
    async def kick(ctx: Context, member: str) -> Reply:
        return Reply(text=member)

    event = group_event(
        "/kick <@member-2>",
        mentions=[{"id": "m2", "member_openid": "member-2", "username": "bob"}],
    )
    await router.handle(event)

    assert isinstance(event.api, FakeApi)
    assert event.api.group.calls[0]["content"] == "member-2"


async def test_mention_placeholder_accepts_a_bare_openid() -> None:
    router = Router()

    @router.command("kick <member:mention>", on=ON)
    async def kick(ctx: Context, member: str) -> Reply:
        return Reply(text=member)

    event = group_event("/kick member-3")
    await router.handle(event)

    assert isinstance(event.api, FakeApi)
    assert event.api.group.calls[0]["content"] == "member-3"


async def test_raw_token_mode_passes_argv_untouched() -> None:
    router = Router()
    received: list[list[str]] = []

    @router.command("grant <word> <rest:rest>", on=ON, bind_args=False)
    async def grant(ctx: Context, argv: list[str]) -> Reply:
        received.append(argv)
        return Reply(text="ok")

    await router.handle(group_event("/grant 3 hello  world"))

    assert received == [["3", "hello", "world"]]


async def test_returning_a_plain_string_is_a_failure() -> None:
    router = Router()

    @router.command("plain", on=ON)
    async def plain(ctx: Context) -> Reply:
        return "pong"  # type: ignore[return-value]

    event = group_event("/plain")
    result = await router.handle(event)

    assert result.status is Status.FAILED
    assert result.error is not None
    assert result.replied is True
    assert isinstance(event.api, FakeApi)
    assert event.api.group.calls[0]["content"] == Messages().internal_error


async def test_usage_error_without_text_falls_back_to_usage_line() -> None:
    router = Router()

    @router.command("kick <target>", on=ON, usage="/kick <target>")
    async def kick(ctx: Context, target: str) -> Reply:
        raise UsageError()

    @router.command("plain", on=ON)
    async def plain(ctx: Context) -> Reply:
        raise UsageError()

    event = group_event("/kick bob")
    await router.handle(event)
    assert isinstance(event.api, FakeApi)
    assert event.api.group.calls[0]["content"] == "Invalid arguments. Usage: /kick <target>"

    other = group_event("/plain")
    await router.handle(other)
    assert isinstance(other.api, FakeApi)
    assert other.api.group.calls[0]["content"] == "Invalid arguments. Usage: /plain"


async def test_stopping_on_a_dead_node_answers_with_usage() -> None:
    router = Router()

    @router.command("permission show", on=ON)
    async def show(ctx: Context) -> Reply:
        return Reply.ok()

    @router.command("permission grant <key>", on=ON)
    async def grant(ctx: Context, key: str) -> Reply:
        return Reply.ok()

    event = group_event("/permission")
    result = await router.handle(event)

    assert result.status is Status.FAILED
    assert isinstance(result.error, UsageError)
    assert result.replied is True
    assert isinstance(event.api, FakeApi)
    assert event.api.group.calls[0]["content"] == (
        "Invalid arguments. Usage: /permission <grant|show>"
    )


async def test_rest_binds_a_string_tuple() -> None:
    router = Router()

    @router.command("echo <text:rest>", on=ON)
    async def echo(ctx: Context, text: tuple[str, ...]) -> Reply:
        return Reply(text="|".join(text))

    event = group_event("/echo a b c")
    await router.handle(event)

    assert isinstance(event.api, FakeApi)
    assert event.api.group.calls[0]["content"] == "a|b|c"


async def test_declared_options_are_converted_and_bound() -> None:
    router = Router()

    @router.command("roll <sides:int>", on=ON, options={"loud": bool, "times": int})
    async def roll(ctx: Context, sides: int, *, loud: bool = False, times: int = 1) -> Reply:
        return Reply(text=f"{sides} {loud} {times}")

    event = group_event("/roll 20 --loud --times=3")
    await router.handle(event)

    assert isinstance(event.api, FakeApi)
    assert event.api.group.calls[0]["content"] == "20 True 3"


async def test_undeclared_option_is_rejected() -> None:
    router = Router()

    @router.command("roll <sides:int>", on=ON, options={"loud": bool})
    async def roll(ctx: Context, sides: int, *, loud: bool = False) -> Reply:
        return Reply.ok()

    event = group_event("/roll 20 --quiet")
    result = await router.handle(event)

    assert result.status is Status.FAILED
    assert isinstance(event.api, FakeApi)
    assert event.api.group.calls[0]["content"] == "Unknown option --quiet."


async def test_options_require_the_right_shape() -> None:
    router = Router()

    @router.command("roll <sides:int>", on=ON, options={"loud": bool, "times": int})
    async def roll(ctx: Context, sides: int, *, loud: bool = False, times: int = 1) -> Reply:
        return Reply.ok()

    missing = group_event("/roll 20 --times")
    await router.handle(missing)
    assert isinstance(missing.api, FakeApi)
    assert missing.api.group.calls[0]["content"] == "Option --times requires a value."

    extra = group_event("/roll 20 --loud=1")
    await router.handle(extra)
    assert isinstance(extra.api, FakeApi)
    assert extra.api.group.calls[0]["content"] == "Option --loud does not take a value."

    bad = group_event("/roll 20 --times=many")
    await router.handle(bad)
    assert isinstance(bad.api, FakeApi)
    assert bad.api.group.calls[0]["content"] == (
        "Invalid value for --times: expected int, got 'many'."
    )


async def test_double_dash_stops_option_parsing() -> None:
    router = Router()

    @router.command("kick <member>", on=ON, options={"force": bool})
    async def kick(ctx: Context, member: str, *, force: bool = False) -> Reply:
        return Reply(text=f"{member} {force}")

    event = group_event("/kick -- --force")
    await router.handle(event)

    assert isinstance(event.api, FakeApi)
    assert event.api.group.calls[0]["content"] == "--force False"


async def test_usage_error_can_carry_its_own_text() -> None:
    router = Router()

    @router.command("boom", on=ON)
    async def boom(ctx: Context) -> Reply:
        raise UsageError("custom text")

    event = group_event("/boom")
    await router.handle(event)

    assert isinstance(event.api, FakeApi)
    assert event.api.group.calls[0]["content"] == "custom text"


async def test_unexpected_exception_maps_to_internal_error() -> None:
    router = Router()

    @router.command("boom", on=ON)
    async def boom(ctx: Context) -> Reply:
        raise RuntimeError("explode")

    event = group_event("/boom")
    result = await router.handle(event)

    assert result.status is Status.FAILED
    assert result.error is not None
    assert isinstance(event.api, FakeApi)
    assert event.api.group.calls[0]["content"] == Messages().internal_error


async def test_permission_without_checker_fails_closed() -> None:
    router = Router()

    @router.command("danger", on=ON, permission="server.stop")
    async def danger(ctx: Context) -> Reply:
        return Reply(text="done")

    event = group_event("/danger")
    result = await router.handle(event)

    assert result.status is Status.DENIED
    assert isinstance(event.api, FakeApi)
    assert event.api.group.calls[0]["content"] == Messages().denied


async def test_checker_allows_and_denies() -> None:
    store = MemoryPermissionStorage()
    checker = PermissionChecker(store)
    router = Router(checker=checker)

    @router.command("danger", on=ON, permission="server.stop")
    async def danger(ctx: Context) -> Reply:
        return Reply(text="done")

    denied = group_event("/danger")
    assert (await router.handle(denied)).status is Status.DENIED

    await store.grant("group:group-1:member-1", Grant("server.stop"))
    allowed = group_event("/danger")
    assert (await router.handle(allowed)).status is Status.HANDLED
    assert isinstance(allowed.api, FakeApi)
    assert allowed.api.group.calls[0]["content"] == "done"


async def test_middlewares_wrap_in_registration_order() -> None:
    order: list[str] = []
    router = Router()

    async def outer(ctx: Context, nxt: Callable[[Context], Awaitable[Reply]]) -> Reply:
        order.append("outer-in")
        reply = await nxt(ctx)
        order.append("outer-out")
        return reply

    async def inner(ctx: Context, nxt: Callable[[Context], Awaitable[Reply]]) -> Reply:
        order.append("inner-in")
        reply = await nxt(ctx)
        order.append("inner-out")
        return reply

    router.use(outer)
    router.use(inner)

    @router.command("ping", on=ON)
    async def ping(ctx: Context) -> Reply:
        order.append("handler")
        return Reply(text="pong")

    await router.handle(group_event("/ping"))

    assert order == ["outer-in", "inner-in", "handler", "inner-out", "outer-out"]


async def test_a_middleware_may_short_circuit_the_handler() -> None:
    seen: list[str] = []
    router = Router()

    async def stop(ctx: Context, nxt: Callable[[Context], Awaitable[Reply]]) -> Reply:
        return Reply(text="blocked")

    router.use(stop)

    @router.command("ping", on=ON)
    async def ping(ctx: Context) -> Reply:
        seen.append("ping")
        return Reply(text="pong")

    event = group_event("/ping")
    result = await router.handle(event)

    assert seen == []
    assert result.status is Status.HANDLED
    assert isinstance(event.api, FakeApi)
    assert event.api.group.calls[0]["content"] == "blocked"


async def test_guard_failure_is_mapped_to_its_message() -> None:
    router = Router()

    async def block(ctx: Context) -> None:
        raise GuardFailed("nope, not now")

    router.guard(block)

    @router.command("ping", on=ON)
    async def ping(ctx: Context) -> Reply:
        return Reply(text="pong")

    event = group_event("/ping")
    result = await router.handle(event)

    assert result.status is Status.DENIED
    assert isinstance(event.api, FakeApi)
    assert event.api.group.calls[0]["content"] == "nope, not now"


async def test_handler_can_stay_silent_with_reply_ok() -> None:
    router = Router()

    @router.command("quiet", on=ON)
    async def quiet(ctx: Context) -> Reply:
        return Reply.ok()

    event = group_event("/quiet")
    result = await router.handle(event)

    assert result.status is Status.HANDLED
    assert result.replied is False
    assert isinstance(event.api, FakeApi)
    assert event.api.group.calls == []


async def test_markdown_reply_is_sent_as_markdown() -> None:
    router = Router()

    @router.command("rich", on=ON)
    async def rich(ctx: Context) -> Reply:
        return Reply(text="# 标题", markdown=True)

    event = group_event("/rich")
    await router.handle(event)

    assert isinstance(event.api, FakeApi)
    call = event.api.group.calls[0]
    assert call["content"] is None
    assert call["markdown"].content == "# 标题"


async def test_a_handler_that_replied_itself_is_not_answered_twice() -> None:
    router = Router()

    @router.command("hello", on=ON)
    async def hello(ctx: GroupContext) -> Reply:
        await ctx.reply("hi there")
        return Reply(text="ignored")

    event = group_event("/hello")
    result = await router.handle(event)

    assert isinstance(event.api, FakeApi)
    assert [call["content"] for call in event.api.group.calls] == ["hi there"]
    assert result.replied is True
    assert result.reply is not None
    assert result.reply.text == "ignored"
