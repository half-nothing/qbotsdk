# Copyright (c) 2026-present Half_nothing.

"""群组（QQ 群）域接口，读写。"""

from __future__ import annotations

from collections.abc import AsyncIterator

from ..model.draft import GroupMessageDraft, MessageMarkdown
from ..model.group import (
    Group,
    GroupBotState,
    GroupMember,
    GroupMembersPage,
    GroupMuteState,
)
from ..model.keyboard import Keyboard
from ..model.media import MediaInfo
from ..model.message import GroupMessageReceipt
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

    async def send_message(
        self,
        group_openid: str,
        *,
        content: str | None = None,
        markdown: MessageMarkdown | None = None,
        media: MediaInfo | None = None,
        keyboard: Keyboard | None = None,
        reply_to: str | None = None,
        event_id: str | None = None,
        msg_seq: int | None = None,
    ) -> GroupMessageReceipt:
        """发群消息。

        被动回复有效期为 5 分钟, 每条消息最多回 5 次。
        同一个 msg_id + msg_seq 重复发送会被拒
        要回第二次请显式传 msg_seq=2
        """

        path = f"/v2/groups/{group_openid}/messages"
        if reply_to is not None and msg_seq is None:
            msg_seq = 1
        draft = GroupMessageDraft(
            content=content,
            markdown=markdown,
            media=media,
            keyboard=keyboard,
            msg_id=reply_to,
            event_id=event_id,
            msg_seq=msg_seq,
        )
        payload = await self._http.post(
            path,
            json=draft.model_dump(by_alias=True, exclude_none=True, mode="json"),
        )
        return GroupMessageReceipt.model_validate(expect_object(payload, path))

    async def recall_message(self, group_openid: str, message_id: str) -> None:
        """撤回群消息, 发送后 2 分钟内有效, 接口限制 10 QPS。"""

        path = f"/v2/groups/{group_openid}/messages/{message_id}"
        await self._http.request("DELETE", path)
