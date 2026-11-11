# Copyright (c) 2026-present Half_nothing.

"""命令与权限测试共用的假事件与假 API。"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from qbotsdk.model.event import (
    C2CMessageCreate,
    ChannelMessageCreate,
    GroupMessageCreate,
    InteractionCreate,
    parse_event,
)
from qbotsdk.model.message import GroupMessageReceipt, UserMessageReceipt


class FakeGroupSender:
    """记录发出去的群消息, 不碰网络。"""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def send_message(self, group_openid: str, **kwargs: Any) -> GroupMessageReceipt:
        self.calls.append({"group_openid": group_openid, **kwargs})
        return GroupMessageReceipt(id=f"m{len(self.calls)}", timestamp=datetime.now(UTC))


class FakeUserSender:
    """记录发出去的单聊消息, 不碰网络。"""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def send_message(self, user_openid: str, **kwargs: Any) -> UserMessageReceipt:
        self.calls.append({"user_openid": user_openid, **kwargs})
        return UserMessageReceipt(id=f"u{len(self.calls)}", timestamp=datetime.now(UTC))


class FakeInteraction:
    def __init__(self) -> None:
        self.calls: list[int] = []

    async def respond(self, interaction_id: str, *, code: int = 0) -> None:
        self.calls.append(code)


class FakeChannelSender:
    """频道消息用不到回复, 只为满足 `ApiProtocol`。"""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def send_message(self, *args: Any, **kwargs: Any) -> Any:
        self.calls.append({"args": args, **kwargs})
        return None


class FakeApi:
    def __init__(self) -> None:
        self.group = FakeGroupSender()
        self.user_message = FakeUserSender()
        self.interaction = FakeInteraction()
        self.channel = FakeChannelSender()


def group_event(
    content: str,
    *,
    openid: str = "member-1",
    group: str = "group-1",
    mentions: list[dict[str, Any]] | None = None,
) -> GroupMessageCreate:
    """构造一条已绑定的群消息事件。"""

    payload = {
        "id": "msg-1",
        "author": {"id": openid, "member_openid": openid},
        "content": content,
        "group_openid": group,
        "timestamp": "2024-01-01T00:00:00+08:00",
        "mentions": mentions or [],
    }
    event = parse_event("GROUP_MESSAGE_CREATE", payload)
    assert isinstance(event, GroupMessageCreate)
    event.bind(FakeApi())
    return event


def c2c_event(content: str, *, openid: str = "user-1") -> C2CMessageCreate:
    payload = {
        "id": "c2c-1",
        "author": {"id": openid, "user_openid": openid},
        "content": content,
        "timestamp": "2024-01-01T00:00:00+08:00",
    }
    event = parse_event("C2C_MESSAGE_CREATE", payload)
    assert isinstance(event, C2CMessageCreate)
    event.bind(FakeApi())
    return event


def channel_event(
    content: str,
    *,
    channel: str = "channel-1",
    guild: str = "guild-1",
    author: str = "user-9",
) -> ChannelMessageCreate:
    """构造一条已绑定的频道 @ 消息事件。"""

    payload: dict[str, Any] = json.loads(
        (Path(__file__).parents[1] / "data" / "channel_message.json").read_text(encoding="utf-8")
    )
    payload.update(content=content, channel_id=channel, guild_id=guild)
    payload["author"] = {**payload.get("author", {}), "id": author}
    event = ChannelMessageCreate.model_validate(payload)
    event.bind(FakeApi())
    return event


def interaction_event(button_data: str, *, openid: str = "member-1", group: str = "group-1") -> Any:
    payload = {
        "application_id": "101984245",
        "chat_type": 1,
        "data": {"resolved": {"button_data": button_data}, "type": 11},
        "group_member_openid": openid,
        "group_openid": group,
        "id": "interaction-1",
        "scene": "group",
        "timestamp": "2026-07-20T21:53:54+08:00",
        "type": 11,
        "version": 1,
    }
    event = InteractionCreate.model_validate(payload)
    event.bind(FakeApi())
    return event
