# Copyright (c) 2026-present Half_nothing.

"""群成员加入与入群申请事件。"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from qbotsdk.model.event import (
    EVENT_MODELS,
    GroupJoinRequest,
    GroupMemberAdd,
    UnknownEvent,
    parse_event,
)
from qbotsdk.model.join_request import ReviewQA

MEMBER_ADD: dict[str, Any] = {
    "timestamp": 1784276757,
    "group_openid": "group-1",
    "member_openid": "member-1",
}

JOIN_REQUEST: dict[str, Any] = {
    "group_openid": "group-1",
    "join_request_id": "req-1",
    "risk_tips": "",
    "union_openid": "union-1",
    "member_openid": "member-2",
    "username": "申请人",
    "apply_at": "2026-08-05T16:21:40+08:00",
    "apply_source": "invited",
    "invited_by": "member-1",
    "bot": False,
    "verify_info": {
        "method": "admin_review_qa",
        "review_qa_list": [{"question": "问题", "answer": "答案"}],
    },
    "auto_approved": {"strategy_id": "st-1"},
}


def test_group_member_add_is_mapped() -> None:
    assert EVENT_MODELS["GROUP_MEMBER_ADD"] is GroupMemberAdd

    event = parse_event("GROUP_MEMBER_ADD", MEMBER_ADD)

    assert isinstance(event, GroupMemberAdd)
    assert event.group_openid == "group-1"
    assert event.member_openid == "member-1"
    # 官方这一处给 Unix 秒, 统一解析成带时区的 datetime
    assert event.timestamp == datetime.fromtimestamp(1784276757, tz=UTC)


def test_group_join_request_is_mapped() -> None:
    assert EVENT_MODELS["GROUP_JOIN_REQUEST"] is GroupJoinRequest

    event = parse_event("GROUP_JOIN_REQUEST", JOIN_REQUEST)

    assert isinstance(event, GroupJoinRequest)
    assert event.group_openid == "group-1"
    assert event.join_request_id == "req-1"
    assert event.member_openid == "member-2"
    assert event.username == "申请人"
    assert event.apply_source == "invited"
    assert event.invited_by == "member-1"
    assert event.bot is False
    assert event.verify_info is not None
    assert event.verify_info.method == "admin_review_qa"
    assert event.verify_info.review_qa_list == [ReviewQA(question="问题", answer="答案")]
    assert event.auto_approved is not None
    assert event.auto_approved.strategy_id == "st-1"


def test_group_join_request_keeps_optional_fields_absent() -> None:
    payload = {
        "group_openid": "group-1",
        "join_request_id": "req-2",
        "member_openid": "member-3",
        "username": "另一个申请人",
        "apply_at": "2026-08-05T16:36:32+08:00",
        "apply_source": "self_apply",
        "bot": True,
    }

    event = parse_event("GROUP_JOIN_REQUEST", payload)

    assert isinstance(event, GroupJoinRequest)
    assert event.union_openid is None
    assert event.invited_by is None
    assert event.risk_tips is None
    assert event.verify_info is None
    assert event.auto_approved is None
    assert event.bot is True


def test_group_join_request_keeps_the_raw_payload() -> None:
    event = parse_event("GROUP_JOIN_REQUEST", JOIN_REQUEST)

    assert event.raw is not None
    assert event.raw["join_request_id"] == "req-1"


def test_group_join_request_can_be_bound_to_an_api() -> None:
    event = parse_event("GROUP_JOIN_REQUEST", JOIN_REQUEST)

    event.bind(None)

    assert event.api is None


def test_group_events_do_not_fall_back_to_unknown() -> None:
    assert not isinstance(parse_event("GROUP_MEMBER_ADD", MEMBER_ADD), UnknownEvent)
    assert not isinstance(parse_event("GROUP_JOIN_REQUEST", JOIN_REQUEST), UnknownEvent)
