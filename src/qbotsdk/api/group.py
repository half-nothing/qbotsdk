# Copyright (c) 2026-present Half_nothing.

"""群组（QQ 群）域接口，读写。"""

from __future__ import annotations

from collections.abc import AsyncIterator

from aiohttp import FormData

from qbotsdk.model.draft import GroupMessageDraft, MessageMarkdown
from qbotsdk.model.group import Group, GroupBotState, GroupMember, GroupMembersPage, GroupMuteState
from qbotsdk.model.keyboard import Keyboard
from qbotsdk.model.media import FileType, MediaInfo, UploadedFile
from qbotsdk.model.message import GroupMessageReceipt
from qbotsdk.module.http_client import HTTPClient
from qbotsdk.module.pagination import paginate
from qbotsdk.module.rate_limit import RateLimiter

from ._parse import expect_object

# 二进制直传上限，官方文档对图片/语音写 20MB、视频 30MB、文件 200MB
# 但 multipart 直传字段本身限制 5MB，超过要走 url 或分片上传。
_MAX_UPLOAD_BYTES = 5 * 1024 * 1024


class GroupResource:
    def __init__(self, http: HTTPClient, *, limiter: RateLimiter | None = None) -> None:
        self._http = http
        self._limiter = limiter

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
        if self._limiter is not None:
            self._limiter.check("group", group_openid)
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

    async def upload_file(
        self,
        group_openid: str,
        file_type: FileType,
        /,
        *,
        url: str | None = None,
        file_data: bytes | None = None,
        file_name: str | None = None,
        srv_send_msg: bool = False,
    ) -> UploadedFile:
        """上传群富媒体（图片 / 视频 / 语音 / 文件）。

        url 与 file_data 二选一，前者交给服务端下载，后者按 multipart 直传，上限 5MB。
        返回的 file_info 直接填进 send_message 的 media。
        srv_send_msg=True 时服务端上传后立即发送，会占用主动消息频次。
        """

        if (url is None) == (file_data is None):
            raise ValueError("upload_file needs exactly one of url or file_data")

        path = f"/v2/groups/{group_openid}/files"

        if url is not None:
            payload = await self._http.post(
                path,
                json={
                    "file_type": int(file_type),
                    "url": url,
                    "srv_send_msg": srv_send_msg,
                },
            )
            return UploadedFile.model_validate(expect_object(payload, path))

        assert file_data is not None  # 由上面的二选一校验保证
        if len(file_data) > _MAX_UPLOAD_BYTES:
            raise ValueError("file_data must not exceed 5 MB, use url instead")
        if file_name is None:
            raise ValueError("file_data needs file_name so the server can infer the type")

        name = file_name

        def build_form() -> FormData:
            form = FormData()
            form.add_field("file_type", str(int(file_type)))
            form.add_field("srv_send_msg", "true" if srv_send_msg else "false")
            form.add_field("file_data", file_data, filename=name)
            form.add_field("file_name", name)
            return form

        payload = await self._http.post_form(path, form=build_form)
        return UploadedFile.model_validate(expect_object(payload, path))
