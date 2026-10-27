# Copyright (c) 2026-present Half_nothing.

"""事件层接线：`Bot.on()`、`ctx.reply()`、`api.message.reply()` 与 start/stop。"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable
from typing import Any

import aiohttp.web
import pytest
from async_event_bus import EventContext

import qbotsdk.module.http_client
import qbotsdk.module.token_manager
from qbotsdk.adapter import WebhookAdapter, WebSocketAdapter
from qbotsdk.bot import Bot
from qbotsdk.model.event import GroupAtMessageCreate, ReadyEvent
from qbotsdk.options import ClientOptions
from tests.support import TOKEN_PATH, FakeGateway, MockServer, load_frame

GROUP = "group-1"
MESSAGES = f"/v2/groups/{GROUP}/messages"
RECEIPT: dict[str, Any] = {
    "id": "sent-1",
    "timestamp": "2026-10-27T10:00:00+08:00",
    "ext_info": {"ref_idx": "REFIDX_1"},
}
OPTIONS = ClientOptions(backoff_base=0.001, backoff_max=0.01)


def json_route(server: MockServer, method: str, path: str, payload: object) -> None:
    async def handler(request: aiohttp.web.Request) -> aiohttp.web.StreamResponse:
        return aiohttp.web.json_response(payload)

    server.route(method, path, handler)


def calls_to(server: MockServer, path: str) -> list[Any]:
    return [call for call in server.calls if call.path == path]


def body_of(call: Any) -> dict[str, Any]:
    assert isinstance(call.json, dict)
    return call.json


async def wait_until(predicate: Callable[[], bool], *, timeout: float = 2.0) -> None:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while loop.time() < deadline:
        if predicate():
            return
        await asyncio.sleep(0.005)
    raise AssertionError("condition was not met in time")


async def test_on_receives_dispatched_event(bot: Bot) -> None:
    seen: list[GroupAtMessageCreate] = []

    @bot.on(GroupAtMessageCreate)
    async def handler(ctx: EventContext[GroupAtMessageCreate]) -> None:
        seen.append(ctx.event)

    bot.dispatcher.handle(load_frame("gateway_group_at_message_create.json"))
    await bot.dispatcher.join()

    assert [event.content for event in seen] == ["hello"]
    assert seen[0].group_openid == GROUP
    assert seen[0].message_scene is not None
    assert seen[0].message_scene.ext["msg_idx"] == "101"


async def test_event_reply_carries_msg_id_and_sequence(bot: Bot, server: MockServer) -> None:
    json_route(server, "POST", MESSAGES, RECEIPT)

    @bot.on(GroupAtMessageCreate)
    async def handler(ctx: EventContext[GroupAtMessageCreate]) -> None:
        await ctx.event.reply("first")
        await ctx.event.reply("second")

    bot.dispatcher.handle(load_frame("gateway_group_at_message_create.json"))
    await bot.dispatcher.join()

    sent = calls_to(server, MESSAGES)
    assert [(body_of(call)["msg_id"], body_of(call)["msg_seq"]) for call in sent] == [
        ("ROBOT1.0_abc", 1),
        ("ROBOT1.0_abc", 2),
    ]
    assert [body_of(call)["content"] for call in sent] == ["first", "second"]


async def test_event_without_bot_cannot_reply() -> None:
    event = GroupAtMessageCreate.model_validate(
        load_frame("gateway_group_at_message_create.json").d
    )

    with pytest.raises(ValueError, match="dispatched by Bot"):
        await event.reply("hi")


def test_event_type_without_reply_has_no_method() -> None:
    # 能不能回复直接看方法在不在, 不需要额外的能力查询接口
    event = ReadyEvent.model_validate(load_frame("gateway_ready.json").d)

    assert not hasattr(event, "reply")


async def test_api_message_reply_delegates(bot: Bot, server: MockServer) -> None:
    json_route(server, "POST", MESSAGES, RECEIPT)

    await bot.api.message.reply(GROUP, msg_id="m-1", content="hi")
    await bot.api.message.reply(GROUP, msg_id="m-1", content="again", msg_seq=2)

    first, second = (body_of(call) for call in calls_to(server, MESSAGES))
    assert first["msg_id"] == "m-1"
    assert first["content"] == "hi"
    # 不带 msg_seq 时资源层补 1, 与事件层一致
    assert first["msg_seq"] == 1
    assert second["msg_seq"] == 2


@pytest.fixture
async def fake_gateway(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[FakeGateway]:
    gw = FakeGateway()
    await gw.start()
    monkeypatch.setattr(qbotsdk.module.token_manager, "TOKEN_URL", f"{gw.url}{TOKEN_PATH}")
    monkeypatch.setattr(qbotsdk.module.http_client, "BASE_URL", gw.url)
    try:
        yield gw
    finally:
        await gw.stop()


async def test_start_connects_and_dispatches(fake_gateway: FakeGateway) -> None:
    seen: list[str] = []
    bot = Bot("app", "secret", options=OPTIONS, adapter=WebSocketAdapter())

    @bot.on(ReadyEvent)
    async def handler(ctx: EventContext[ReadyEvent]) -> None:
        seen.append(ctx.event.session_id)

    try:
        await bot.start()
        await wait_until(lambda: seen == ["xxxxxx"])
        assert fake_gateway.connections == 1
    finally:
        await bot.close()


async def test_start_twice_is_rejected(fake_gateway: FakeGateway) -> None:
    bot = Bot("app", "secret", options=OPTIONS, adapter=WebSocketAdapter())
    try:
        await bot.start()
        with pytest.raises(RuntimeError, match="already started"):
            await bot.start()
    finally:
        await bot.close()


async def test_default_adapter_is_websocket(fake_gateway: FakeGateway) -> None:
    bot = Bot("app", "secret", options=OPTIONS)
    seen: list[str] = []

    @bot.on(ReadyEvent)
    async def handler(ctx: EventContext[ReadyEvent]) -> None:
        seen.append(ctx.event.session_id)

    try:
        assert isinstance(bot.adapter, WebSocketAdapter)
        await bot.start()
        await wait_until(lambda: seen == ["xxxxxx"])
        assert fake_gateway.connections == 1
    finally:
        await bot.close()


async def test_webhook_adapter_starts_a_server() -> None:
    bot = Bot(
        "app",
        "secret",
        adapter=WebhookAdapter("bot-secret", host="127.0.0.1", port=0),
    )
    try:
        await bot.start()
        assert isinstance(bot.adapter, WebhookAdapter)
        assert bot.adapter.port != 0
    finally:
        await bot.close()
