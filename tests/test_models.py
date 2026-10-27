# Copyright (c) 2026-present Half_nothing.

"""模型层测试，官方响应示例 JSON 原文 → 模型。"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest
from pydantic import TypeAdapter, ValidationError

from qbotsdk.model import (
    Channel,
    ChannelType,
    Guild,
    GuildUser,
    Member,
    QQModel,
    RolesResult,
    SpeakPermission,
)

DATA = Path(__file__).parent / "data"


def load(name: str) -> object:
    return json.loads((DATA / name).read_text(encoding="utf-8"))


def load_object(name: str) -> dict[str, object]:
    payload = load(name)
    assert isinstance(payload, dict)
    return payload


def load_list(name: str) -> list[dict[str, object]]:
    payload = load(name)
    assert isinstance(payload, list)
    return payload


def as_dict(value: object) -> dict[str, object]:
    assert isinstance(value, dict)
    return value


def missing_fields(payload: dict[str, object], model: type[QQModel]) -> set[str]:
    """返回示例里出现、模型里没有的字段名。"""
    return {key for key in payload if key not in model.model_fields}


def test_guild_list_snapshot() -> None:
    items = load_list("guilds.json")
    guilds = TypeAdapter(list[Guild]).validate_python(items)

    assert len(guilds) == 1
    guild = guilds[0]
    assert guild.id == "696527283900292399"
    assert guild.owner is False
    assert guild.member_count == 17
    assert guild.joined_at == datetime.fromisoformat("2021-12-08T16:12:31+08:00")
    assert missing_fields(items[0], Guild) == set()


def test_guild_detail_snapshot() -> None:
    payload = load_object("guild.json")
    guild = Guild.model_validate(payload)

    assert guild.name == "技术交流频道"
    assert guild.max_members == 1000
    assert guild.owner is False
    assert missing_fields(payload, Guild) == set()


def test_channels_list_is_bare_array() -> None:
    items = load_list("channels.json")
    channels = TypeAdapter(list[Channel]).validate_python(items)

    assert [channel.type for channel in channels] == [ChannelType.TEXT, ChannelType.AUDIO]
    assert channels[0].speak_permission == SpeakPermission.EVERYONE
    assert missing_fields(items[0], Channel) == set()


def test_channel_detail_optional_fields() -> None:
    payload = load_object("channel.json")
    channel = Channel.model_validate(payload)

    assert channel.permissions == "0"
    assert channel.application_id is None
    assert missing_fields(payload, Channel) == set()


def test_member_snapshot_nested_user() -> None:
    items = load_list("members.json")
    members = TypeAdapter(list[Member]).validate_python(items)

    assert len(members) == 2
    member = members[1]
    assert member.user.username == "秦时明月"
    assert member.user.public_flags == 0
    assert member.user.system is False
    assert member.roles == ["4"]
    assert member.joined_at == datetime.fromisoformat("2021-12-02T15:19:00+08:00")
    assert missing_fields(items[0], Member) == set()
    assert missing_fields(as_dict(items[0]["user"]), GuildUser) == set()


def test_roles_snapshot() -> None:
    payload = load_object("roles.json")
    result = RolesResult.model_validate(payload)

    assert result.guild_id == "123456"
    # 官方给的是字符串 "30", 模型保持 str
    assert result.role_num_limit == "30"
    assert [role.id for role in result.roles] == ["4", "2"]
    assert result.roles[1].member_limit == 50
    # 官方是 integer, 模型不做 bool 转换
    assert result.roles[0].hoist == 1
    assert missing_fields(payload, RolesResult) == set()

    roles_payload = payload["roles"]
    assert isinstance(roles_payload, list)
    assert missing_fields(as_dict(roles_payload[0]), type(result.roles[0])) == set()


def test_unknown_field_ignored() -> None:
    payload = load_object("guild.json")
    payload["brand_new_field"] = "whatever"

    guild = Guild.model_validate(payload)
    assert guild.id == "123456789012345678"


def test_models_are_frozen() -> None:
    guild = Guild.model_validate(load_object("guild.json"))
    with pytest.raises(ValidationError):
        guild.name = "changed"


def test_field_name_construction() -> None:
    guild = Guild(
        id="1",
        name="n",
        icon="",
        owner_id="1",
        owner=False,
        member_count=0,
        max_members=0,
        description="",
        joined_at=datetime.fromisoformat("2021-12-08T16:12:31+08:00"),
    )
    assert guild.id == "1"
