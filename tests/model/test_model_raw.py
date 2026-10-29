# Copyright (c) 2026-present Half_nothing.

"""`QQModel.raw`: 直接留一份解析用的 dict, 既不序列化也不用再 loads。"""

from __future__ import annotations

import json
from typing import Any

from qbotsdk.gateway.payload import GatewayPayload
from qbotsdk.model.event import GroupMessageCreate, parse_event
from qbotsdk.model.user import GroupUser, User


def _event_data() -> dict[str, Any]:
    return {
        "id": "msg-1",
        "author": {
            "id": "member-1",
            "member_openid": "member-1",
            "username": "user-a",
            "secret_flag": 7,
        },
        "content": "<@member-2> hi",
        "group_openid": "group-1",
        "timestamp": "2024-01-01T00:00:00+08:00",
        "mentions": [{"id": "member-2", "member_openid": "member-2", "new_flag": True}],
        "unknown_top": {"k": "v"},
    }


def test_raw_is_the_parsed_dict() -> None:
    event = parse_event("GROUP_MESSAGE_CREATE", _event_data())

    assert isinstance(event, GroupMessageCreate)
    assert event.raw is not None
    # 官方新加的字段直接按下标取, 不用 json.loads
    assert event.raw["unknown_top"] == {"k": "v"}


def test_nested_model_keeps_its_own_slice() -> None:
    event = parse_event("GROUP_MESSAGE_CREATE", _event_data())

    assert isinstance(event, GroupMessageCreate)
    assert isinstance(event.author, GroupUser)
    assert event.author.raw is not None
    assert event.author.raw["secret_flag"] == 7


def test_raw_is_not_serialized() -> None:
    event = parse_event("GROUP_MESSAGE_CREATE", _event_data())

    assert "raw" not in event.model_dump()
    assert "__raw__" not in event.model_dump(by_alias=True)


def test_mutation_of_raw_does_not_touch_fields() -> None:
    event = parse_event("GROUP_MESSAGE_CREATE", _event_data())
    assert event.raw is not None

    event.raw["content"] = "changed"

    assert isinstance(event, GroupMessageCreate)
    assert event.content == "<@member-2> hi"


def test_gateway_frame_keeps_parsed_dict() -> None:
    frame = {"op": 0, "s": 1, "t": "GROUP_MESSAGE_CREATE", "d": _event_data()}
    payload = GatewayPayload.model_validate_json(json.dumps(frame))

    assert payload.raw is not None
    assert payload.raw["op"] == 0

    event = parse_event(payload.t or "", payload.d)
    assert isinstance(event, GroupMessageCreate)
    assert event.raw is not None
    assert event.raw["group_openid"] == "group-1"


def test_rest_model_also_gets_raw() -> None:
    user = User.model_validate({"id": "1", "unknown_field": 1})

    assert user.raw is not None
    assert user.raw["unknown_field"] == 1
