# Copyright (c) 2026-present Half_nothing.

"""群聊全量消息事件 `GROUP_MESSAGE_CREATE`。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

from qbotsdk.model.event import (
    EVENT_MODELS,
    GroupAtMessageCreate,
    GroupMessageCreate,
    parse_event,
)
from qbotsdk.model.user import GroupUser, MentionUser

_DATA = Path(__file__).parent / "data"


def load_object(name: str) -> dict[str, Any]:
    return cast("dict[str, Any]", json.loads((_DATA / name).read_text(encoding="utf-8")))


def test_parse_event_routes_group_message_create() -> None:
    payload = load_object("gateway_group_message_create.json")
    event = parse_event("GROUP_MESSAGE_CREATE", payload["d"])

    assert isinstance(event, GroupMessageCreate)
    assert event.group_openid == "group-1"
    assert event.content == "<@member-2> 你好 <@all>"
    assert [user.member_openid for user in event.mentions] == ["bot-1", "member-2"]


def test_group_message_create_is_a_separate_event_type() -> None:
    payload = load_object("gateway_group_message_create.json")
    event = parse_event("GROUP_MESSAGE_CREATE", payload["d"])

    assert not isinstance(event, GroupAtMessageCreate)


def test_group_message_create_keeps_mention_fields() -> None:
    payload = load_object("group_message_create_full.json")
    event = parse_event("GROUP_MESSAGE_CREATE", payload["d"])

    assert isinstance(event, GroupMessageCreate)
    assert event.content == "<@member-2> 11"
    assert event.author.username == "user-a"
    assert event.author.bot is False
    assert event.author.member_role == "owner"
    assert isinstance(event.author, GroupUser)
    assert not isinstance(event.author, MentionUser)

    mention = event.mentions[0]
    assert isinstance(mention, MentionUser)
    assert mention.member_openid == "member-2"
    assert mention.username == "user-b"
    assert mention.bot is False
    assert mention.is_you is False
    assert mention.scope == "single"


def test_mentioned_me_uses_is_you_in_full_mode() -> None:
    payload = load_object("group_message_create_full.json")
    event = parse_event("GROUP_MESSAGE_CREATE", payload["d"])

    assert isinstance(event, GroupMessageCreate)
    assert event.mentioned_me is False

    payload["d"]["mentions"][0]["is_you"] = True
    mentioned = parse_event("GROUP_MESSAGE_CREATE", payload["d"])

    assert isinstance(mentioned, GroupMessageCreate)
    assert mentioned.mentioned_me is True


def test_mentioned_me_is_true_for_group_at_event() -> None:
    payload = load_object("gateway_group_at_message_create.json")
    event = parse_event("GROUP_AT_MESSAGE_CREATE", payload["d"])

    assert isinstance(event, GroupAtMessageCreate)
    assert event.mentioned_me is True


def test_event_models_registers_group_message_create() -> None:
    assert EVENT_MODELS["GROUP_MESSAGE_CREATE"] is GroupMessageCreate


def test_mentioned_me_is_true_for_bot_mention_sample() -> None:
    payload = load_object("group_message_create_mention.json")
    event = parse_event("GROUP_MESSAGE_CREATE", payload["d"])

    assert isinstance(event, GroupMessageCreate)
    assert event.mentioned_me is True

    bot_mention = event.mentions[0]
    assert bot_mention.bot is True
    assert bot_mention.is_you is True
    assert bot_mention.username == "bot-name"
    # 全量模式下 content 里保留了 @ 机器人自己那一段
    assert event.content == "<@bot-1> <@member-2> "


def test_mentions_by_openid_indexes_mentions() -> None:
    payload = load_object("group_message_create_mention.json")
    event = parse_event("GROUP_MESSAGE_CREATE", payload["d"])

    assert isinstance(event, GroupMessageCreate)
    assert set(event.mentions_by_openid) == {"bot-1", "member-2"}
    assert event.mentions_by_openid["member-2"].username == "user-b"


def test_render_mentions_resolves_usernames() -> None:
    payload = load_object("group_message_create_mention.json")
    event = parse_event("GROUP_MESSAGE_CREATE", payload["d"])

    assert isinstance(event, GroupMessageCreate)
    assert event.render_mentions() == "@bot-name @user-b"
    assert event.content == "<@bot-1> <@member-2> "


def test_render_mentions_can_strip_me() -> None:
    payload = load_object("group_message_create_mention.json")
    event = parse_event("GROUP_MESSAGE_CREATE", payload["d"])

    assert isinstance(event, GroupMessageCreate)
    assert event.render_mentions(strip_me=True) == "@user-b"


def test_render_mentions_falls_back_to_openid_and_handles_all() -> None:
    payload = load_object("gateway_group_message_create.json")
    event = parse_event("GROUP_MESSAGE_CREATE", payload["d"])

    assert isinstance(event, GroupMessageCreate)
    assert event.render_mentions() == "@member-2 你好 @全体成员"


def test_render_mentions_indexed_numbers_mentions_in_order() -> None:
    payload = load_object("group_message_create_mention.json")
    event = parse_event("GROUP_MESSAGE_CREATE", payload["d"])

    assert isinstance(event, GroupMessageCreate)
    rendered = event.render_mentions_indexed()
    assert rendered.text == "@0 @1"
    assert [user.member_openid for user in rendered.mentions] == ["bot-1", "member-2"]
    assert event.content == "<@bot-1> <@member-2> "


def test_render_mentions_indexed_renumbers_after_strip_me() -> None:
    payload = load_object("group_message_create_mention.json")
    event = parse_event("GROUP_MESSAGE_CREATE", payload["d"])

    assert isinstance(event, GroupMessageCreate)
    rendered = event.render_mentions_indexed(strip_me=True)
    assert rendered.text == "@0"
    assert [user.member_openid for user in rendered.mentions] == ["member-2"]


def test_render_mentions_indexed_keeps_unknown_tag_and_all() -> None:
    payload = load_object("gateway_group_message_create.json")
    event = parse_event("GROUP_MESSAGE_CREATE", payload["d"])

    assert isinstance(event, GroupMessageCreate)
    rendered = event.render_mentions_indexed()
    assert rendered.text == "@0 你好 @all"
    assert [user.member_openid for user in rendered.mentions] == ["member-2"]
