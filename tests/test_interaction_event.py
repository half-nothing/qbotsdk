# Copyright (c) 2026-present Half_nothing.

"""INTERACTION_CREATE 事件与互动回调。

事件体与响应接口来源：
- https://bot.q.qq.com/wiki/develop/api-v2/autogen/event/interaction_create.html
- https://bot.q.qq.com/wiki/develop/api-v2/autogen/api/interactions_interaction_id.put.html
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

import pytest

from qqbot.model.event import InteractionCode, InteractionCreate, InteractionType, parse_event

DATA_DIR = Path(__file__).parent / "data"


def load_object(name: str) -> dict[str, Any]:
    return cast("dict[str, Any]", json.loads((DATA_DIR / name).read_text(encoding="utf-8")))


class FakeInteraction:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def respond(self, interaction_id: str, *, code: int = 0) -> None:
        self.calls.append({"id": interaction_id, "code": code})


class FakeApi:
    def __init__(self) -> None:
        self.interaction = FakeInteraction()

    @property
    def group(self) -> Any:
        raise NotImplementedError

    @property
    def user_message(self) -> Any:
        raise NotImplementedError

    @property
    def channel(self) -> Any:
        raise NotImplementedError


def test_interaction_create_parses_snapshot() -> None:
    event = InteractionCreate.model_validate(load_object("interaction_create.json"))

    assert event.type is InteractionType.INLINE_KEYBOARD
    assert event.scene == "c2c"
    assert event.chat_type == 2
    assert event.user_openid == "A1B2C3D4E5F6A1B2C3D4E5F6A1B2C3D4"
    assert event.needs_response is True
    assert event.data is not None
    assert event.data.resolved is not None
    assert event.data.resolved.button_data == "confirm:once"
    assert event.data.resolved.button_id == "allow-once"
    assert event.timestamp.isoformat() == "2026-07-20T21:53:54+08:00"


def test_interaction_group_scene_keeps_openids() -> None:
    payload = {
        "application_id": "101984245",
        "chat_type": 1,
        "data": {"resolved": {"button_data": "eyJjb21tYW5kIjogInNhbXBsZSJ9"}, "type": 11},
        "group_member_openid": "A1B2C3D4E5F6A1B2C3D4E5F6A1B2C3D4",
        "group_openid": "B2C3D4E5F6A1B2C3D4E5F6A1B2C3D4E5",
        "id": "06915133-7aef-46ed-94f7-c50939e285ae",
        "scene": "group",
        "timestamp": "2026-07-20T21:53:54+08:00",
        "type": 11,
        "version": 1,
    }

    event = InteractionCreate.model_validate(payload)

    assert event.group_openid == "B2C3D4E5F6A1B2C3D4E5F6A1B2C3D4E5"
    assert event.group_member_openid == "A1B2C3D4E5F6A1B2C3D4E5F6A1B2C3D4"
    assert event.data is not None
    assert event.data.resolved is not None
    assert event.data.resolved.button_data == "eyJjb21tYW5kIjogInNhbXBsZSJ9"


def test_feedback_event_needs_no_response() -> None:
    payload = {
        "application_id": "102057050",
        "data": {"resolved": {"feedback_opt": "LIKE", "checked": 1}, "type": 13},
        "id": "c30c003e-9454-4450-8e5e-665267c088c4",
        "scene": "c2c",
        "timestamp": "2026-07-20T21:54:38+08:00",
        "type": 13,
        "user_openid": "A1B2C3D4E5F6A1B2C3D4E5F6A1B2C3D4",
        "version": 1,
    }

    event = InteractionCreate.model_validate(payload)

    assert event.type is InteractionType.MESSAGE_FEEDBACK
    assert event.needs_response is False
    assert event.data is not None
    assert event.data.resolved is not None
    assert event.data.resolved.feedback_opt == "LIKE"


def test_authorize_event_parses_authorize_data() -> None:
    payload = {
        "application_id": "102057050",
        "data": {"resolved": {"authorize_data": {"opt_scene": "setting", "scope": "c2c_push"}}},
        "id": "c30c003e-9454-4450-8e5e-665267c088c4",
        "scene": "c2c",
        "timestamp": "2026-07-20T21:54:38+08:00",
        "type": 18,
        "user_openid": "A1B2C3D4E5F6A1B2C3D4E5F6A1B2C3D4",
        "version": 1,
    }

    event = parse_event("INTERACTION_CREATE", payload)
    assert isinstance(event, InteractionCreate)
    assert event.data is not None
    assert event.data.resolved is not None
    assert event.data.resolved.authorize_data is not None
    assert event.data.resolved.authorize_data.scope == "c2c_push"


async def test_respond_calls_put_with_code() -> None:
    event = InteractionCreate.model_validate(load_object("interaction_create.json"))
    api = FakeApi()
    event.bind(cast("Any", api))

    await event.respond(InteractionCode.ADMIN_ONLY)

    assert api.interaction.calls == [{"id": "1b13d569-4610-4ab9-bc51-feecc5def6d4", "code": 5}]


async def test_respond_defaults_to_ok() -> None:
    event = InteractionCreate.model_validate(load_object("interaction_create.json"))
    api = FakeApi()
    event.bind(cast("Any", api))

    await event.respond()

    assert api.interaction.calls[0]["code"] == 0


async def test_respond_without_bot_raises() -> None:
    event = InteractionCreate.model_validate(load_object("interaction_create.json"))

    with pytest.raises(ValueError, match="respond\\(\\) needs an event dispatched by Bot"):
        await event.respond()
