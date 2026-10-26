# Copyright (c) 2026-present Half_nothing.

"""群组（QQ 群）域接口，只读部分。"""

from __future__ import annotations

from collections.abc import AsyncIterator

from ..model.group import (
    Group,
    GroupBotState,
    GroupMember,
    GroupMembersPage,
    GroupMuteState,
)
from ..module.http_client import HTTPClient
from ..module.pagination import paginate
from ._parse import expect_object


class GroupResource:
    def __init__(self, http: HTTPClient) -> None:
        self._http = http

    async def get(self, group_openid: str) -> Group:
        """群基本信息，频率限制 30 QPM。"""

        path = f"/v2/groups/{group_openid}/info"
        return Group.model_validate(expect_object(await self._http.get(path), path))

    async def bot_state(self, group_openid: str) -> GroupBotState:
        """机器人在群内的状态：是否收主动推送、接收消息范围、自身角色。"""

        path = f"/v2/groups/{group_openid}/bot_state"
        return GroupBotState.model_validate(expect_object(await self._http.get(path), path))

    async def members(self, group_openid: str, *, cursor: str = "") -> GroupMembersPage:
        """
        群成员分页，每次最多 30 条。

        `cursor` 首次不传，后续传上一页的 `next_cursor`；
        返回整页而不是列表，因为末页标志 `next_cursor` 与成员在同一层。
        """

        path = f"/v2/groups/{group_openid}/members"
        params = {"cursor": cursor} if cursor else None
        payload = await self._http.get(path, params=params)
        return GroupMembersPage.model_validate(expect_object(payload, path))

    async def member(self, group_openid: str, member_openid: str) -> GroupMember:
        """单个群成员。"""

        path = f"/v2/groups/{group_openid}/members/{member_openid}"
        return GroupMember.model_validate(expect_object(await self._http.get(path), path))

    async def mute_setting(self, group_openid: str) -> GroupMuteState:
        """群禁言状态，机器人为群管理员时才有权限（错误码 11253）。"""

        path = f"/v2/groups/{group_openid}/restrict_chat_setting"
        return GroupMuteState.model_validate(expect_object(await self._http.get(path), path))

    async def iter_members(self, group_openid: str) -> AsyncIterator[GroupMember]:
        """按 `next_cursor` 翻页遍历群成员，末页或空页结束。"""

        state = {"next": ""}

        async def fetch_page(cursor: str | None) -> list[GroupMember]:
            page = await self.members(group_openid, cursor=cursor or "")
            state["next"] = page.next_cursor
            return page.members

        def cursor_of(page: list[GroupMember]) -> str | None:
            return state["next"] or None

        async for member in paginate(fetch_page, cursor_of=cursor_of):
            yield member
