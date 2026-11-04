# Copyright (c) 2026-present Half_nothing.

"""命令层与 Bot 的接线：路由器不订阅事件，调用方在自己的回调里手动分派。"""

from __future__ import annotations

from async_event_bus import EventContext

from qbotsdk.bot import Bot
from qbotsdk.commands import Context, ExecutionResult, Reply, Router
from qbotsdk.gateway.payload import GatewayPayload
from qbotsdk.model.event import GroupMessageCreate


def gateway_frame(content: str) -> GatewayPayload:
    return GatewayPayload.model_validate(
        {
            "op": 0,
            "s": 1,
            "t": "GROUP_MESSAGE_CREATE",
            "d": {
                "id": "msg-1",
                "author": {"id": "member-1", "member_openid": "member-1"},
                "content": content,
                "group_openid": "group-1",
                "timestamp": "2024-01-01T00:00:00+08:00",
                "mentions": [],
            },
        }
    )


async def test_a_user_listener_dispatches_to_the_router() -> None:
    bot = Bot("app", "secret")
    router = Router(reply_mention=False)
    seen: list[str] = []
    results: list[ExecutionResult] = []

    @router.command("ping", on=GroupMessageCreate)
    async def ping(ctx: Context) -> Reply:
        seen.append(ctx.principal)
        return Reply.ok()

    @bot.on(GroupMessageCreate)
    async def listener(ctx: EventContext[GroupMessageCreate]) -> None:
        results.append(await router.handle(ctx.event))

    bot.dispatcher.handle(gateway_frame("/ping"))
    await bot.dispatcher.join()

    assert seen == ["group:group-1:member-1"]
    assert results[0].status.value == "handled"
    assert results[0].replied is False


async def test_the_user_listener_keeps_running_for_other_traffic() -> None:
    bot = Bot("app", "secret")
    router = Router(reply_mention=False)
    recorded: list[str] = []
    results: list[ExecutionResult] = []

    @router.command("ping", on=GroupMessageCreate)
    async def ping(ctx: Context) -> Reply:
        return Reply(text="pong")

    @bot.on(GroupMessageCreate)
    async def listener(ctx: EventContext[GroupMessageCreate]) -> None:
        results.append(await router.handle(ctx.event))
        recorded.append("listener")

    bot.dispatcher.handle(gateway_frame("hello"))
    await bot.dispatcher.join()

    assert recorded == ["listener"]
    assert results[0].status.value == "not_found"
    assert results[0].handled is False


async def test_the_bot_never_subscribes_the_router_by_itself() -> None:
    bot = Bot("app", "secret")
    router = Router(reply_mention=False)
    seen: list[str] = []

    @router.command("ping", on=GroupMessageCreate)
    async def ping(ctx: Context) -> Reply:
        seen.append("ping")
        return Reply(text="pong")

    bot.dispatcher.handle(gateway_frame("/ping"))
    await bot.dispatcher.join()

    assert seen == []
    assert [route.name for route in router.routes] == ["ping"]
