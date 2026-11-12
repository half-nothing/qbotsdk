# Copyright (c) 2026-present Half_nothing.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""群组(QQ 群)域接口, 读写。"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from pathlib import Path
from typing import BinaryIO

from qbotsdk.exceptions import QQBotError
from qbotsdk.model import (
    FileType,
    Group,
    GroupBotState,
    GroupMember,
    GroupMembersPage,
    GroupMessageDraft,
    GroupMessageReceipt,
    GroupMuteState,
    JoinRequestAction,
    JoinRequestPage,
    Keyboard,
    MediaInfo,
    MessageMarkdown,
    UploadedFile,
)
from qbotsdk.module import HttpClient, RateLimiter, SendHook, SendRecord, notify_send, paginate

from ._parse import expect_object
from ._upload import open_source, upload_file_content, upload_file_url

__all__ = ["GroupResource"]


class GroupResource:
    def __init__(
        self,
        http: HttpClient,
        *,
        limiter: RateLimiter | None = None,
        hook: SendHook | None = None,
    ) -> None:
        self._http = http
        self._limiter = limiter
        self._hook = hook

    async def get(self, group_openid: str) -> Group:
        """群基本信息, 频率限制 30 QPM。"""

        path = f"/v2/groups/{group_openid}/info"
        return Group.model_validate(expect_object(await self._http.get(path), path))

    async def bot_state(self, group_openid: str) -> GroupBotState:
        """机器人在群内的状态: 是否收主动推送、接收消息范围、自身角色。"""

        path = f"/v2/groups/{group_openid}/bot_state"
        return GroupBotState.model_validate(expect_object(await self._http.get(path), path))

    async def members(self, group_openid: str, *, cursor: str = "") -> GroupMembersPage:
        """
        群成员分页, 每次最多 30 条。

        `cursor` 首次不传, 后续传上一页的 `next_cursor`;
        返回整页而不是列表, 因为末页标志 `next_cursor` 与成员在同一层。
        """

        path = f"/v2/groups/{group_openid}/members"
        params = {"cursor": cursor} if cursor else None
        payload = await self._http.get(path, params=params)
        return GroupMembersPage.model_validate(expect_object(payload, path))

    async def member(self, group_openid: str, member_openid: str) -> GroupMember:
        """单个群成员。"""

        path = f"/v2/groups/{group_openid}/members/{member_openid}"
        return GroupMember.model_validate(expect_object(await self._http.get(path), path))

    async def join_requests(
        self, group_openid: str, *, cursor: str = "", limit: int = 20
    ) -> JoinRequestPage:
        """入群申请列表, 分页; 机器人需为群管理员, 频率限制 30 QPM。"""

        path = f"/v2/groups/{group_openid}/join_request_list"
        params: dict[str, str | int] = {"limit": limit}
        if cursor:
            params["cursor"] = cursor
        payload = await self._http.get(path, params=params)
        return JoinRequestPage.model_validate(expect_object(payload, path))

    async def review_join_request(
        self,
        group_openid: str,
        member_openid: str,
        join_request_id: str,
        *,
        action: JoinRequestAction,
        reject_reason: str | None = None,
        add_to_member_blacklist: bool = False,
    ) -> None:
        """审批入群申请, 频率限制 60 QPM。

        `action` 只有 `approve` 与 `decline` 两种;
        `reject_reason` 与 `add_to_member_blacklist` 仅在拒绝时有效。
        """

        path = f"/v2/groups/{group_openid}/approval_join_request/{member_openid}"
        op = JoinRequestAction(action)
        body: dict[str, object] = {"op": op.value}
        if join_request_id is not None:
            body["join_request_id"] = join_request_id
        if op is JoinRequestAction.DECLINE:
            if reject_reason is not None:
                body["reject_reason"] = reject_reason
            if add_to_member_blacklist:
                body["add_to_member_blacklist"] = True
        await self._http.post(path, json=body)

    async def approve_join_request(
        self, group_openid: str, member_openid: str, join_request_id: str
    ) -> None:
        """通过入群申请。"""

        await self.review_join_request(
            group_openid,
            member_openid,
            join_request_id,
            action=JoinRequestAction.APPROVE,
        )

    async def decline_join_request(
        self,
        group_openid: str,
        member_openid: str,
        join_request_id: str,
        *,
        reject_reason: str | None = None,
        add_to_member_blacklist: bool = False,
    ) -> None:
        """拒绝入群申请, 可选同时拉黑。"""

        await self.review_join_request(
            group_openid,
            member_openid,
            join_request_id,
            action=JoinRequestAction.DECLINE,
            reject_reason=reject_reason,
            add_to_member_blacklist=add_to_member_blacklist,
        )

    async def mute_setting(self, group_openid: str) -> GroupMuteState:
        """群禁言状态, 机器人为群管理员时才有权限(错误码 11253)。"""

        path = f"/v2/groups/{group_openid}/restrict_chat_setting"
        return GroupMuteState.model_validate(expect_object(await self._http.get(path), path))

    async def iter_members(self, group_openid: str) -> AsyncIterator[GroupMember]:
        """按 `next_cursor` 翻页遍历群成员, 末页或空页结束。"""

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

        keyboard 只在 Markdown 消息上渲染: 只传 content + keyboard 时,
        content 会被自动搬进 markdown 并把 msg_type 置 2。
        """

        path = f"/v2/groups/{group_openid}/messages"
        proactive = reply_to is None and event_id is None
        draft: GroupMessageDraft | None = None
        try:
            if self._limiter is not None:
                self._limiter.check("group", group_openid, active=proactive)
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
        except QQBotError as error:
            await notify_send(
                self._hook,
                SendRecord(
                    scope="group",
                    target=group_openid,
                    path=path,
                    proactive=proactive,
                    message=draft,
                    error=error,
                ),
            )
            raise
        receipt = GroupMessageReceipt.model_validate(expect_object(payload, path))
        await notify_send(
            self._hook,
            SendRecord(
                scope="group",
                target=group_openid,
                path=path,
                proactive=proactive,
                message=draft,
                message_id=receipt.id,
            ),
        )
        return receipt

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
        file: str | Path | BinaryIO | bytes | None = None,
        file_name: str | None = None,
        srv_send_msg: bool = False,
        progress: Callable[[int, int], None] | None = None,
    ) -> UploadedFile:
        """上传群富媒体(图片 / 视频 / 语音 / 文件)。

        url 与 file 二选一: url 交给服务端下载; file 由 SDK 按体积自动选择
        base64 直传或预上传分片, 调用方不需要关心差别。
        分片所需的 md5 / sha1 / md5_10m 由 SDK 计算, 不接受调用方传入。
        srv_send_msg=True 时服务端上传后立即发送, 会占用主动消息频次并产生发送记录。
        """

        if (url is None) == (file is None):
            raise ValueError("upload_file needs exactly one of url or file")

        path = f"/v2/groups/{group_openid}/files"
        if srv_send_msg and self._limiter is not None:
            self._limiter.check("group", group_openid, active=True)

        uploaded: UploadedFile | None = None
        error: QQBotError | None = None
        try:
            if url is not None:
                uploaded = await upload_file_url(
                    self._http,
                    files_path=path,
                    file_type=file_type,
                    url=url,
                    srv_send_msg=srv_send_msg,
                )
            else:
                assert file is not None
                source = open_source(file, file_name)
                try:
                    uploaded = await upload_file_content(
                        self._http,
                        prefix=f"/v2/groups/{group_openid}",
                        files_path=path,
                        file_type=file_type,
                        source=source,
                        srv_send_msg=srv_send_msg,
                        progress=progress,
                    )
                finally:
                    source.close()
        except QQBotError as exc:
            error = exc
            raise
        finally:
            if srv_send_msg and (uploaded is not None or error is not None):
                await notify_send(
                    self._hook,
                    SendRecord(
                        scope="group",
                        target=group_openid,
                        path=path,
                        proactive=True,
                        message=None,
                        message_id=uploaded.id if uploaded is not None else None,
                        error=error,
                    ),
                )
        assert uploaded is not None
        return uploaded
