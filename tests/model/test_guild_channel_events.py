# Copyright (c) 2026-present Half_nothing.

"""频道、群与单聊的开关类事件。"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from qbotsdk.model.channel import ChannelSubType, ChannelType
from qbotsdk.model.event import (
    EVENT_MODELS,
    C2CMsgReceive,
    C2CMsgReject,
    ChannelCreate,
    ChannelDelete,
    ChannelUpdate,
    DirectMessageCreate,
    FriendAdd,
    FriendDel,
    GroupAddRobot,
    GroupDelRobot,
    GroupMemberRemove,
    GroupMsgReceive,
    GroupMsgReject,
    GuildCreate,
    GuildDelete,
    GuildMessageCreate,
    GuildUpdate,
    MessageAuditPass,
    MessageAuditReject,
    UnknownEvent,
    parse_event,
)

DATA = Path(__file__).parents[1] / "data"

GUILD: dict[str, Any] = {
    "id": "guild-1",
    "name": "测试频道",
    "icon": "https://example.com/icon.png",
    "owner_id": "user-1",
    "member_count": 10,
    "max_members": 100,
    "description": "频道简介",
    "joined_at": "2026-08-05T16:21:40+08:00",
    "op_user_id": "user-2",
}

CHANNEL: dict[str, Any] = {
    "id": "channel-1",
    "guild_id": "guild-1",
    "name": "闲聊",
    "type": 0,
    "sub_type": 0,
    "owner_id": "user-1",
    "op_user_id": "user-2",
    "position": 3,
}

GROUP_ROBOT: dict[str, Any] = {
    "timestamp": 1784276757,
    "group_openid": "group-1",
    "op_member_openid": "member-1",
}

FRIEND: dict[str, Any] = {
    "timestamp": 1784276757,
    "openid": "user-1",
    "scene": 1003,
    "scene_param": "callback",
    "author": {"union_openid": "union-1"},
    "short_code": "abc",
}

AUDIT: dict[str, Any] = {
    "audit_id": "audit-1",
    "audit_time": "2026-08-05T16:21:40+08:00",
    "channel_id": "channel-1",
    "create_time": "2026-08-05T16:20:00+08:00",
    "guild_id": "guild-1",
    "message_id": "msg-1",
}


@pytest.mark.parametrize(
    ("event_name", "model"),
    [
        ("GUILD_CREATE", GuildCreate),
        ("GUILD_UPDATE", GuildUpdate),
        ("GUILD_DELETE", GuildDelete),
    ],
)
def test_guild_events_carry_the_channel(event_name: str, model: type[GuildCreate]) -> None:
    assert EVENT_MODELS[event_name] is model

    event = parse_event(event_name, GUILD)

    assert isinstance(event, model)
    assert event.id == "guild-1"
    assert event.name == "测试频道"
    assert event.member_count == 10
    assert event.op_user_id == "user-2"
    assert event.joined_at == datetime(2026, 8, 5, 8, 21, 40, tzinfo=UTC)


def test_guild_delete_accepts_only_the_id_and_operator() -> None:
    event = parse_event("GUILD_DELETE", {"id": "guild-1", "op_user_id": "user-2"})

    assert isinstance(event, GuildDelete)
    assert event.id == "guild-1"
    assert event.name == ""
    assert event.member_count == 0
    assert event.joined_at is None


@pytest.mark.parametrize(
    ("event_name", "model"),
    [
        ("CHANNEL_CREATE", ChannelCreate),
        ("CHANNEL_UPDATE", ChannelUpdate),
        ("CHANNEL_DELETE", ChannelDelete),
    ],
)
def test_channel_events_carry_the_sub_channel(event_name: str, model: type[ChannelCreate]) -> None:
    assert EVENT_MODELS[event_name] is model

    event = parse_event(event_name, CHANNEL)

    assert isinstance(event, model)
    assert event.id == "channel-1"
    assert event.guild_id == "guild-1"
    assert event.type is ChannelType.TEXT
    assert event.sub_type is ChannelSubType.CHAT
    assert event.position == 3


def test_channel_delete_accepts_only_the_id() -> None:
    event = parse_event("CHANNEL_DELETE", {"id": "channel-1", "op_user_id": "user-2"})

    assert isinstance(event, ChannelDelete)
    assert event.guild_id == ""
    assert event.type is None


@pytest.mark.parametrize(
    ("event_name", "model"),
    [
        ("GROUP_ADD_ROBOT", GroupAddRobot),
        ("GROUP_DEL_ROBOT", GroupDelRobot),
        ("GROUP_MSG_RECEIVE", GroupMsgReceive),
        ("GROUP_MSG_REJECT", GroupMsgReject),
    ],
)
def test_group_robot_events(event_name: str, model: type[GroupAddRobot]) -> None:
    assert EVENT_MODELS[event_name] is model

    event = parse_event(event_name, GROUP_ROBOT)

    assert isinstance(event, model)
    assert event.group_openid == "group-1"
    assert event.op_member_openid == "member-1"
    assert event.timestamp == datetime.fromtimestamp(1784276757, tz=UTC)


def test_group_member_remove_keeps_the_optional_user_openid() -> None:
    payload = {
        "timestamp": 1784276757,
        "group_openid": "group-1",
        "member_openid": "member-2",
        "user_openid": "user-2",
    }

    event = parse_event("GROUP_MEMBER_REMOVE", payload)

    assert isinstance(event, GroupMemberRemove)
    assert event.member_openid == "member-2"
    assert event.user_openid == "user-2"

    without_user = parse_event("GROUP_MEMBER_REMOVE", {**payload, "user_openid": None})

    assert isinstance(without_user, GroupMemberRemove)
    assert without_user.user_openid is None


def test_friend_add_keeps_the_scene_and_author() -> None:
    event = parse_event("FRIEND_ADD", FRIEND)

    assert isinstance(event, FriendAdd)
    assert event.openid == "user-1"
    assert event.scene == 1003
    assert event.scene_param == "callback"
    assert event.author is not None
    assert event.author.union_openid == "union-1"
    assert event.short_code == "abc"


def test_friend_del_keeps_only_the_required_fields() -> None:
    event = parse_event("FRIEND_DEL", {"timestamp": 1784276757, "openid": "user-1"})

    assert isinstance(event, FriendDel)
    assert event.openid == "user-1"
    assert event.author is None


@pytest.mark.parametrize(
    ("event_name", "model"),
    [
        ("C2C_MSG_RECEIVE", C2CMsgReceive),
        ("C2C_MSG_REJECT", C2CMsgReject),
    ],
)
def test_c2c_message_switch_events(event_name: str, model: type[C2CMsgReceive]) -> None:
    assert EVENT_MODELS[event_name] is model

    event = parse_event(event_name, {"timestamp": 1784276757, "openid": "user-1"})

    assert isinstance(event, model)
    assert event.openid == "user-1"


@pytest.mark.parametrize(
    ("event_name", "model"),
    [
        ("MESSAGE_CREATE", GuildMessageCreate),
        ("DIRECT_MESSAGE_CREATE", DirectMessageCreate),
    ],
)
def test_channel_message_events_reuse_the_message_body(
    event_name: str, model: type[GuildMessageCreate]
) -> None:
    assert EVENT_MODELS[event_name] is model

    payload = json.loads((DATA / "channel_message.json").read_text(encoding="utf-8"))

    event = parse_event(event_name, payload)

    assert isinstance(event, model)
    assert event.channel_id == payload["channel_id"]
    assert event.guild_id == payload["guild_id"]


@pytest.mark.parametrize(
    ("event_name", "model"),
    [
        ("MESSAGE_AUDIT_PASS", MessageAuditPass),
        ("MESSAGE_AUDIT_REJECT", MessageAuditReject),
    ],
)
def test_message_audit_events(event_name: str, model: type[MessageAuditPass]) -> None:
    assert EVENT_MODELS[event_name] is model

    event = parse_event(event_name, AUDIT)

    assert isinstance(event, model)
    assert event.audit_id == "audit-1"
    assert event.message_id == "msg-1"
    assert event.audit_time == datetime(2026, 8, 5, 8, 21, 40, tzinfo=UTC)


def test_these_events_do_not_fall_back_to_unknown() -> None:
    assert not isinstance(parse_event("GUILD_CREATE", GUILD), UnknownEvent)
    assert not isinstance(parse_event("CHANNEL_CREATE", CHANNEL), UnknownEvent)
    assert not isinstance(parse_event("GROUP_ADD_ROBOT", GROUP_ROBOT), UnknownEvent)
    assert not isinstance(parse_event("FRIEND_ADD", FRIEND), UnknownEvent)
    assert not isinstance(parse_event("MESSAGE_AUDIT_PASS", AUDIT), UnknownEvent)
