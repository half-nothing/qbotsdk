# Copyright (c) 2026-present Half_nothing.

"""群组资源层：路径拼接、游标翻页、群相关模型的字段映射。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import aiohttp.web

from qbotsdk.bot import Bot
from qbotsdk.model import JoinRequestAction
from qbotsdk.model.group import GroupMemberRole, JoinRequestAction, MuteMode, RecvMsgSetting
from tests.support import MockServer

DATA = Path(__file__).parents[1] / "data"
GROUP_OPENID = "G1"
MEMBERS_PATH = f"/v2/groups/{GROUP_OPENID}/members"


def snapshot(name: str) -> Any:
    return json.loads((DATA / name).read_text(encoding="utf-8"))


def json_route(server: MockServer, method: str, path: str, payload: object) -> None:
    async def handler(request: aiohttp.web.Request) -> aiohttp.web.StreamResponse:
        return aiohttp.web.json_response(payload)

    server.route(method, path, handler)


def calls_to(server: MockServer, path: str) -> list[Any]:
    return [call for call in server.calls if call.path == path]


async def test_group_info(bot: Bot, server: MockServer) -> None:
    payload = snapshot("group.json")
    json_route(server, "GET", f"/v2/groups/{GROUP_OPENID}/info", payload)

    group = await bot.api.group.get(GROUP_OPENID)

    assert group.group_name == payload["group_name"]
    assert group.group_tags == payload["group_tags"]
    assert group.group_member_num == 256
    assert group.group_finger_memo == payload["group_finger_memo"]


async def test_group_members_pagination(bot: Bot, server: MockServer) -> None:
    first_page = snapshot("group_members.json")
    last_member = {
        "member_openid": "LAST",
        "username": "最后一页",
        "member_role": "owner",
        "bot": False,
        "joined_at": "2025-07-02T10:30:00+08:00",
    }

    async def handler(request: aiohttp.web.Request) -> aiohttp.web.StreamResponse:
        if request.query.get("cursor"):
            # 末页：next_cursor 为空串，但仍带一条成员
            return aiohttp.web.json_response({"members": [last_member], "next_cursor": ""})
        return aiohttp.web.json_response(first_page)

    server.route("GET", MEMBERS_PATH, handler)

    members = [member async for member in bot.api.group.iter_members(GROUP_OPENID)]

    assert [member.member_openid for member in members] == [
        *(item["member_openid"] for item in first_page["members"]),
        "LAST",
    ]
    # 首屏不带 cursor，第二屏带上一页的 next_cursor
    assert [call.query for call in calls_to(server, MEMBERS_PATH)] == [
        {},
        {"cursor": first_page["next_cursor"]},
    ]


async def test_group_member_detail(bot: Bot, server: MockServer) -> None:
    payload = snapshot("group_member.json")
    member_openid = str(payload["member_openid"])
    json_route(server, "GET", f"{MEMBERS_PATH}/{member_openid}", payload)

    member = await bot.api.group.member(GROUP_OPENID, member_openid)

    assert member.username == payload["username"]
    assert member.member_role is GroupMemberRole.ADMIN
    assert member.joined_at.year == 2025


async def test_group_bot_state(bot: Bot, server: MockServer) -> None:
    payload = snapshot("group_bot_state.json")
    json_route(server, "GET", f"/v2/groups/{GROUP_OPENID}/bot_state", payload)

    state = await bot.api.group.bot_state(GROUP_OPENID)

    assert state.allow_proactive_msg is False
    assert state.recv_msg_setting is RecvMsgSetting.ONLY_MENTION
    assert state.member_role is GroupMemberRole.MEMBER


async def test_group_mute_setting(bot: Bot, server: MockServer) -> None:
    payload = snapshot("group_mute.json")
    json_route(server, "GET", f"/v2/groups/{GROUP_OPENID}/restrict_chat_setting", payload)

    state = await bot.api.group.mute_setting(GROUP_OPENID)

    assert state.global_rule.mode is MuteMode.SCHEDULE
    assert len(state.global_rule.schedule_rules) == 2
    assert state.global_rule.recurring_rules[0].weekdays == [1, 2, 3, 4, 5, 6, 7]
    # HH:mm 不做时间解析，保持官方给的原样
    assert state.global_rule.recurring_rules[0].start_time == "13:05"
    assert state.members[0].mute_expire_at.year == 2026


JOIN_REQUEST_PATH = f"/v2/groups/{GROUP_OPENID}/join_request_list"
JOIN_REQUEST_PAYLOAD = {
    "list": [
        {
            "join_request_id": "req-1",
            "risk_tips": "",
            "union_openid": "U1",
            "member_openid": "M1",
            "username": "申请人",
            "apply_at": "2026-08-05T14:19:09+08:00",
            "apply_source": "self_apply",
            "invited_by": "",
            "bot": False,
            "verify_info": {
                "method": "verify_message",
                "verify_message": "让我进群",
                "review_qa_list": [],
            },
        }
    ],
    "next_cursor": "cursor-2",
}


async def test_join_request_list(bot: Bot, server: MockServer) -> None:
    json_route(server, "GET", JOIN_REQUEST_PATH, JOIN_REQUEST_PAYLOAD)

    page = await bot.api.group.join_requests(GROUP_OPENID, limit=50)

    request = page.join_request_list[0]
    assert page.next_cursor == "cursor-2"
    assert request.join_request_id == "req-1"
    assert request.username == "申请人"
    assert request.apply_at.year == 2026
    assert request.verify_info is not None
    assert request.verify_info.verify_message == "让我进群"
    # 首次不带游标, 只带 limit
    assert calls_to(server, JOIN_REQUEST_PATH)[0].query == {"limit": "50"}


async def test_join_request_list_passes_cursor(bot: Bot, server: MockServer) -> None:
    json_route(server, "GET", JOIN_REQUEST_PATH, {"list": [], "next_cursor": ""})

    page = await bot.api.group.join_requests(GROUP_OPENID, cursor="cursor-1")

    assert page.join_request_list == []
    assert calls_to(server, JOIN_REQUEST_PATH)[0].query == {"limit": "20", "cursor": "cursor-1"}


async def test_approve_join_request(bot: Bot, server: MockServer) -> None:
    path = f"/v2/groups/{GROUP_OPENID}/approval_join_request/M1"
    json_route(server, "POST", path, {})

    await bot.api.group.approve_join_request(GROUP_OPENID, "M1", join_request_id="req-1")

    assert calls_to(server, path)[0].json == {"op": "approve", "join_request_id": "req-1"}


async def test_decline_join_request_with_reason_and_blacklist(bot: Bot, server: MockServer) -> None:
    path = f"/v2/groups/{GROUP_OPENID}/approval_join_request/M2"
    json_route(server, "POST", path, {})

    await bot.api.group.decline_join_request(
        GROUP_OPENID,
        "M2",
        join_request_id="req-2",
        reject_reason="不欢迎广告",
        add_to_member_blacklist=True,
    )

    assert calls_to(server, path)[0].json == {
        "op": "decline",
        "join_request_id": "req-2",
        "reject_reason": "不欢迎广告",
        "add_to_member_blacklist": True,
    }


async def test_review_join_request_omits_decline_only_fields_when_approving(
    bot: Bot, server: MockServer
) -> None:
    path = f"/v2/groups/{GROUP_OPENID}/approval_join_request/M3"
    json_route(server, "POST", path, {})

    await bot.api.group.review_join_request(
        GROUP_OPENID,
        "M3",
        "111",
        action=JoinRequestAction.APPROVE,
        reject_reason="should be ignored",
        add_to_member_blacklist=True,
    )

    # 通过申请时拒绝原因与拉黑都不该出现在请求体里
    assert calls_to(server, path)[0].json == {"op": "approve"}
