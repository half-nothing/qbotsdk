# Copyright (c) 2026-present Half_nothing.

"""按钮回调: 载荷路由、字面量兜底与 ack 策略。"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from qbotsdk.commands import Context, Reply, Router, Status
from tests.commands.support import FakeApi, interaction_event


class ButtonPayload(BaseModel):
    action: Literal["demo.button"]
    value: str = "x"


async def test_button_routes_json_payload_and_acks_once() -> None:
    router = Router(reply_mention=False)
    seen: list[str] = []

    @router.button(ButtonPayload)
    async def on_button(ctx: Context, payload: ButtonPayload) -> Reply:
        seen.append(payload.value)
        return Reply.ok()

    event = interaction_event('{"action": "demo.button", "value": "v"}')
    result = await router.handle(event)

    assert seen == ["v"]
    assert result.status is Status.HANDLED
    assert result.command == "demo.button"
    assert result.handler is on_button
    assert result.replied is True
    assert isinstance(event.api, FakeApi)
    assert event.api.interaction.calls == [0]


async def test_unknown_button_payload_is_ignored() -> None:
    router = Router(reply_mention=False)

    @router.button(ButtonPayload)
    async def on_button(ctx: Context, payload: ButtonPayload) -> Reply:
        return Reply(text="x")

    event = interaction_event("nope")
    assert (await router.handle(event)).status is Status.NOT_FOUND
    assert isinstance(event.api, FakeApi)
    assert event.api.interaction.calls == []


async def test_literal_button_respects_ack_policy() -> None:
    router = Router(reply_mention=False)

    @router.button("demo.literal", ack="none")
    async def on_literal(ctx: Context, payload: str) -> Reply:
        return Reply.ok()

    event = interaction_event("demo.literal")
    assert (await router.handle(event)).replied is False
    assert isinstance(event.api, FakeApi)
    assert event.api.interaction.calls == []


async def test_ack_none_still_acknowledges_when_content_is_returned() -> None:
    router = Router(reply_mention=False)

    @router.button("demo.literal", ack="none")
    async def on_literal(ctx: Context, payload: str) -> Reply:
        return Reply(text="done")

    event = interaction_event("demo.literal")
    result = await router.handle(event)

    assert result.replied is True
    assert isinstance(event.api, FakeApi)
    assert event.api.interaction.calls == [0]


async def test_button_text_is_never_sent_as_a_message() -> None:
    router = Router(reply_mention=False)

    @router.button("demo.literal")
    async def on_literal(ctx: Context, payload: str) -> Reply:
        return Reply(text="ignored")

    event = interaction_event("demo.literal")
    await router.handle(event)

    assert isinstance(event.api, FakeApi)
    assert event.api.interaction.calls == [0]
    assert event.api.group.calls == []
