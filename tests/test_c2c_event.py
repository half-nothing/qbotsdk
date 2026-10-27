# Copyright (c) 2026-present Half_nothing.

"""单聊消息事件与 `reply()`。"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import pytest

from qbotsdk.model.event import C2CMessageCreate, EventModel, parse_event
from qbotsdk.model.message import UserMessageReceipt
from qbotsdk.model.user import C2CUser

_DATA = Path(__file__).parent / "data"


def load_object(name: str) -> dict[str, Any]:
    return cast("dict[str, Any]", json.loads((_DATA / name).read_text(encoding="utf-8")))


class FakeChatSender:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def send_message(
        self,
        user_openid: str,
        *,
        content: str | None = None,
        markdown: Any = None,
        media: Any = None,
        keyboard: Any = None,
        reply_to: str | None = None,
        event_id: str | None = None,
        msg_seq: int | None = None,
        is_wakeup: bool = False,
    ) -> UserMessageReceipt:
        self.calls.append(
            {
                "user_openid": user_openid,
                "content": content,
                "reply_to": reply_to,
                "msg_seq": msg_seq,
                "is_wakeup": is_wakeup,
            }
        )
        return UserMessageReceipt(
            id=f"m{len(self.calls)}",
            timestamp=datetime(2024, 1, 1, tzinfo=UTC),
        )


class FakeApi:
    def __init__(self) -> None:
        self.user_message = FakeChatSender()

    @property
    def group(self) -> Any:
        raise NotImplementedError


def test_c2c_message_create_parses_snapshot() -> None:
    event = C2CMessageCreate.model_validate(load_object("c2c_message_create.json"))

    assert isinstance(event.author, C2CUser)
    assert event.author.openid == "A1B2C3D4E5F6A1B2C3D4E5F6A1B2C3D4"
    assert event.content == "你好"
    assert event.message_scene is not None
    assert event.message_scene.ext["msg_idx"] == "xxx"
    assert event.timestamp.isoformat() == "2024-01-01T00:00:00+08:00"


def test_c2c_quote_message_parses_nested_elements() -> None:
    event = C2CMessageCreate.model_validate(load_object("c2c_message_create_quote.json"))

    element = event.msg_elements[0]
    assert element.message_type == 103
    assert element.content == "每天坚持阅读半小时，可以提升专注力。"
    assert element.attachments[0].content_type == "image/png"
    assert element.ark_data is not None
    assert element.ark_data.fields["title"] == "阅读计划"
    assert element.author is not None
    assert element.author.openid == "A1B2C3D4E5F6A1B2C3D4E5F6A1B2C3D4"
    assert element.msg_elements[0].content == "被引用的原文"


def test_parse_event_routes_c2c_message() -> None:
    event = parse_event("C2C_MESSAGE_CREATE", load_object("c2c_message_create.json"))

    assert isinstance(event, C2CMessageCreate)


async def test_reply_carries_msg_id_and_sequence() -> None:
    event = C2CMessageCreate.model_validate(load_object("c2c_message_create.json"))
    api = FakeApi()
    event.bind(cast("Any", api))

    first = await event.reply("hi")
    second = await event.reply("again")

    assert first.id == "m1"
    assert second.id == "m2"
    assert api.user_message.calls[0] == {
        "user_openid": "A1B2C3D4E5F6A1B2C3D4E5F6A1B2C3D4",
        "content": "hi",
        "reply_to": "ROBOT1.0_IrExO5_vr3n6JfGk4VlA9G5QqQ1lQV6m6J9h7bE0C8w!",
        "msg_seq": 1,
        "is_wakeup": False,
    }
    assert api.user_message.calls[1]["msg_seq"] == 2


async def test_reply_accepts_explicit_sequence() -> None:
    event = C2CMessageCreate.model_validate(load_object("c2c_message_create.json"))
    api = FakeApi()
    event.bind(cast("Any", api))

    await event.reply("hi", msg_seq=3)

    assert api.user_message.calls[0]["msg_seq"] == 3


async def test_reply_rejects_sequence_over_limit() -> None:
    event = C2CMessageCreate.model_validate(load_object("c2c_message_create.json"))
    api = FakeApi()
    event.bind(cast("Any", api))

    with pytest.raises(ValueError, match="passive reply limit reached"):
        await event.reply("hi", msg_seq=5)

    assert api.user_message.calls == []


async def test_reply_without_bot_raises() -> None:
    event = C2CMessageCreate.model_validate(load_object("c2c_message_create.json"))

    with pytest.raises(ValueError, match="needs an event dispatched by Bot"):
        await event.reply("hi")


def test_c2c_event_is_not_frozen() -> None:
    event = C2CMessageCreate.model_validate(load_object("c2c_message_create.json"))
    event.content = "changed"

    assert event.content == "changed"


def test_event_models_map_contains_c2c() -> None:
    from qbotsdk.model.event import EVENT_MODELS

    assert EVENT_MODELS["C2C_MESSAGE_CREATE"] is C2CMessageCreate
    assert issubclass(C2CMessageCreate, EventModel)
