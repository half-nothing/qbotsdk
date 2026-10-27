# Copyright (c) 2026-present Half_nothing.

"""AT_MESSAGE_CREATE 事件（频道 @ 机器人）。

事件体在官方 api-v2 没有独立页面，字段按「消息对象(Message)」表格建模：
https://bot.q.qq.com/wiki/develop/api-v2/server-inter/message/template/model.html
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

import pytest

from qbotsdk.model.event import ChannelMessageCreate, parse_event
from qbotsdk.model.message import MessageAttachment

DATA_DIR = Path(__file__).parent / "data"


def load_object(name: str) -> dict[str, Any]:
    return cast("dict[str, Any]", json.loads((DATA_DIR / name).read_text(encoding="utf-8")))


class FakeChannel:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def send_message(
        self,
        channel_id: str,
        *,
        content: str | None = None,
        markdown: Any = None,
        image: str | None = None,
        reply_to: str | None = None,
        event_id: str | None = None,
    ) -> Any:
        self.calls.append(
            {
                "channel_id": channel_id,
                "content": content,
                "image": image,
                "reply_to": reply_to,
                "event_id": event_id,
            }
        )
        return "sent"


class FakeApi:
    def __init__(self) -> None:
        self.channel = FakeChannel()

    @property
    def group(self) -> Any:
        raise NotImplementedError

    @property
    def user_message(self) -> Any:
        raise NotImplementedError

    @property
    def interaction(self) -> Any:
        raise NotImplementedError


def test_at_message_parses_send_response_shape() -> None:
    event = ChannelMessageCreate.model_validate(load_object("channel_message.json"))

    assert event.channel_id == "xxxxxx"
    assert event.guild_id == "xxxxxx"
    assert event.content == "<@!1234>hello world"
    assert event.author.username == "abc"
    assert event.attachments == []


def test_at_message_reads_optional_table_fields() -> None:
    payload = load_object("channel_message.json")
    payload["attachments"] = [{"url": "https://example.com/a.png"}]
    payload["seq_in_channel"] = "12"
    payload["mentions"] = [{"id": "9", "username": "bob", "avatar": "", "bot": False}]
    payload["member"] = {
        "user": {"id": "8", "username": "abc"},
        "roles": ["1"],
        "joined_at": "2021-05-13T14:45:45+08:00",
    }

    event = ChannelMessageCreate.model_validate(payload)

    assert event.seq_in_channel == "12"
    assert event.mentions[0].username == "bob"
    assert event.member is not None
    assert event.member.roles == ["1"]
    assert isinstance(event.attachments[0], MessageAttachment)
    assert event.attachments[0].url == "https://example.com/a.png"


def test_parse_event_maps_at_message_create() -> None:
    event = parse_event("AT_MESSAGE_CREATE", load_object("channel_message.json"))

    assert isinstance(event, ChannelMessageCreate)


async def test_reply_sends_to_channel_with_msg_id() -> None:
    event = ChannelMessageCreate.model_validate(load_object("channel_message.json"))
    api = FakeApi()
    event.bind(cast("Any", api))

    await event.reply("收到")

    call = api.channel.calls[0]
    assert call["channel_id"] == "xxxxxx"
    assert call["content"] == "收到"
    assert call["reply_to"] == "xxxxxx"
    assert call["event_id"] == "xxxxxx"


async def test_reply_without_bot_raises() -> None:
    event = ChannelMessageCreate.model_validate(load_object("channel_message.json"))

    with pytest.raises(ValueError, match="reply\\(\\) needs an event dispatched by Bot"):
        await event.reply("收到")
