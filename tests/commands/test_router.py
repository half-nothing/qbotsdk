# Copyright (c) 2026-present Half_nothing.

"""命令注册、路径匹配与未知命令的测试。"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

import pytest

from qbotsdk.commands import Context, GuardFailed, Messages, Reply, Router, Status
from qbotsdk.commands.router import strip_prefix
from qbotsdk.model.event import C2CMessageCreate, GroupMessageCreate
from tests.commands.support import FakeApi, c2c_event, group_event

ON = GroupMessageCreate


async def test_strip_prefix_handles_whitespace() -> None:
    assert strip_prefix("  /ping", "/") == "ping"
    assert strip_prefix("/", "/") is None
    assert strip_prefix("ping", "/") is None


async def test_non_command_is_ignored_silently() -> None:
    router = Router(reply_mention=False)

    @router.command("ping", on=ON)
    async def ping(ctx: Context) -> Reply:
        return Reply(text="pong")

    event = group_event("hello")
    result = await router.handle(event)

    assert result.status is Status.NOT_FOUND
    assert bool(result) is False
    assert result.replied is False
    assert isinstance(event.api, FakeApi)
    assert event.api.group.calls == []


async def test_a_command_needs_an_explicit_event_type() -> None:
    router = Router(reply_mention=False)

    with pytest.raises(TypeError, match="must name at least one event type"):
        router.command("ping", on=())

    with pytest.raises(TypeError, match="must be an event model class"):
        router.command("ping", on=object)  # type: ignore[arg-type]


async def test_unknown_command_is_quiet_by_default() -> None:
    router = Router(reply_mention=False)

    @router.command("ping", on=ON)
    async def ping(ctx: Context) -> Reply:
        return Reply(text="pong")

    event = group_event("/nope")
    result = await router.handle(event)

    assert result.status is Status.NOT_FOUND
    assert result.replied is False
    assert isinstance(event.api, FakeApi)
    assert event.api.group.calls == []


async def test_unknown_command_can_be_reported() -> None:
    router = Router(reply_unknown=True)

    @router.command("ping", on=ON)
    async def ping(ctx: Context) -> Reply:
        return Reply(text="pong")

    event = group_event("/nope")
    result = await router.handle(event)

    assert result.status is Status.NOT_FOUND
    assert result.replied is True
    assert isinstance(event.api, FakeApi)
    assert event.api.group.calls[0]["content"] == "Unknown command."


async def test_unknown_command_message_can_be_customised() -> None:
    router = Router(reply_unknown=True, messages=Messages(unknown_command="没有这个命令"))
    event = group_event("/nope")
    result = await router.handle(event)

    assert result.replied is True
    assert isinstance(event.api, FakeApi)
    assert event.api.group.calls[0]["content"] == "没有这个命令"


async def test_bare_prefix_is_ignored_silently() -> None:
    router = Router(reply_unknown=True)
    event = group_event("/")

    result = await router.handle(event)

    assert result.status is Status.NOT_FOUND
    assert isinstance(event.api, FakeApi)
    assert event.api.group.calls == []


async def test_command_only_answers_its_own_event_types() -> None:
    router = Router(reply_mention=False)

    @router.command("ping", on=C2CMessageCreate)
    async def ping(ctx: Context) -> Reply:
        return Reply(text="pong")

    group = group_event("/ping")
    assert (await router.handle(group)).status is Status.NOT_FOUND

    direct = c2c_event("/ping")
    assert (await router.handle(direct)).replied is True
    assert isinstance(direct.api, FakeApi)
    assert direct.api.user_message.calls[0]["content"] == "pong"


async def test_more_specific_template_wins() -> None:
    seen: list[str] = []
    router = Router(reply_mention=False)

    @router.command("server <name>", on=ON)
    async def generic(ctx: Context, name: str) -> Reply:
        seen.append(f"generic:{name}")
        return Reply(text="generic")

    @router.command("server stop", on=ON)
    async def exact(ctx: Context) -> Reply:
        seen.append("exact")
        return Reply(text="exact")

    await router.handle(group_event("/server stop"))

    assert seen == ["exact"]


async def test_include_prefixes_commands() -> None:
    child = Router(prefix="", reply_mention=False)

    @child.command("ping", on=ON)
    async def ping(ctx: Context) -> Reply:
        return Reply(text="pong")

    parent = Router(reply_mention=False)
    parent.include(child, prefix="admin")

    event = group_event("/admin ping")
    assert (await parent.handle(event)).replied is True
    assert isinstance(event.api, FakeApi)
    assert event.api.group.calls[0]["content"] == "pong"


async def test_include_accepts_a_default_prefix_child() -> None:
    child = Router()

    @child.command("ping", on=ON)
    async def ping(ctx: Context) -> Reply:
        return Reply(text="pong")

    parent = Router(reply_mention=False)
    parent.include(child, prefix="admin")

    assert [route.name for route in parent.commands] == ["admin ping"]
    event = group_event("/admin ping")
    assert (await parent.handle(event)).replied is True


async def test_include_keeps_child_guards_local() -> None:
    child = Router(reply_mention=False)

    @child.guard
    async def child_only(ctx: Context) -> None:
        raise GuardFailed("child only")

    @child.command("ping", on=ON)
    async def ping(ctx: Context) -> Reply:
        return Reply(text="pong")

    parent = Router(reply_mention=False)

    @parent.command("open", on=ON)
    async def open_command(ctx: Context) -> Reply:
        return Reply(text="open")

    parent.include(child, prefix="admin")

    open_event = group_event("/open")
    assert (await parent.handle(open_event)).status is Status.HANDLED
    assert isinstance(open_event.api, FakeApi)
    assert open_event.api.group.calls[0]["content"] == "open"

    child_event = group_event("/admin ping")
    assert (await parent.handle(child_event)).status is Status.DENIED


async def test_include_keeps_child_middleware_inside_the_parent() -> None:
    order: list[str] = []
    child = Router()

    @child.use
    async def child_middleware(
        ctx: Context, call_next: Callable[[Context], Awaitable[Reply]]
    ) -> Reply:
        order.append("child")
        return await call_next(ctx)

    @child.command("ping", on=ON)
    async def ping(ctx: Context) -> Reply:
        order.append("ping")
        return Reply(text="pong")

    parent = Router()

    @parent.use
    async def parent_middleware(
        ctx: Context, call_next: Callable[[Context], Awaitable[Reply]]
    ) -> Reply:
        order.append("parent")
        return await call_next(ctx)

    @parent.command("open", on=ON)
    async def open_command(ctx: Context) -> Reply:
        order.append("open")
        return Reply(text="open")

    parent.include(child, prefix="admin")

    await parent.handle(group_event("/open"))
    assert order == ["parent", "open"]

    order.clear()
    await parent.handle(group_event("/admin ping"))
    assert order == ["parent", "child", "ping"]


async def test_include_rejects_a_foreign_prefix() -> None:
    parent = Router()

    with pytest.raises(ValueError, match="cannot include a router with prefix"):
        parent.include(Router(prefix="!"), prefix="admin")


async def test_self_include_is_rejected() -> None:
    router = Router(reply_mention=False)

    with pytest.raises(ValueError, match="cannot include itself"):
        router.include(router)


async def test_duplicate_paths_are_rejected() -> None:
    router = Router(reply_mention=False)

    async def ping(ctx: Context) -> Reply:
        return Reply(text="pong")

    router.command("ping", on=ON)(ping)

    with pytest.raises(ValueError, match="already registered"):
        router.command("ping", on=ON)(ping)


async def test_the_same_path_may_serve_two_event_types() -> None:
    router = Router(reply_mention=False)

    async def ping(ctx: Context) -> Reply:
        return Reply(text="pong")

    router.command("ping", on=GroupMessageCreate)(ping)
    router.command("ping", on=C2CMessageCreate)(ping)

    assert [route.name for route in router.commands] == ["ping", "ping"]


async def test_non_async_handler_is_rejected() -> None:
    router = Router(reply_mention=False)

    def ping(ctx: Context) -> Reply:
        return Reply(text="pong")

    with pytest.raises(TypeError, match="must be an async function"):
        router.command("ping", on=ON)(ping)  # type: ignore[arg-type]


async def test_a_handler_must_be_annotated_to_return_reply() -> None:
    router = Router(reply_mention=False)

    async def ping(ctx: Context) -> str:
        return "pong"

    with pytest.raises(TypeError, match="must be annotated to return Reply"):
        router.command("ping", on=ON)(ping)


async def test_one_handler_may_be_registered_at_several_paths() -> None:
    router = Router(reply_mention=False)
    seen: list[Context] = []

    async def stop(ctx: Context) -> Reply:
        seen.append(ctx)
        return Reply(text="stopped")

    router.command("server stop", on=ON)(stop)
    router.command("halt", on=ON)(stop)

    assert (await router.handle(group_event("/halt"))).status is Status.HANDLED
    assert (await router.handle(group_event("/server stop"))).status is Status.HANDLED
    assert [route.name for route in router.commands] == ["halt", "server stop"]

    halt, server_stop = seen[0].route, seen[1].route
    assert halt is not None
    assert server_stop is not None
    assert halt is not server_stop
    assert halt.handler is stop
    assert server_stop.handler is stop
    assert seen[0].command == "halt"
    assert seen[1].command == "server stop"
