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

"""单聊消息域接口。

接口文档: https://bot.q.qq.com/wiki/develop/api-v2/autogen/api/v2_users_user_openid_messages.post.html
被动回复有效期 60 分钟, 每条消息最多回 4 次。
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import BinaryIO

from qbotsdk.exceptions import QQBotError
from qbotsdk.model import (
    FileType,
    InputNotify,
    Keyboard,
    MediaInfo,
    MessageMarkdown,
    UploadedFile,
    UserMessageDraft,
    UserMessageReceipt,
)
from qbotsdk.module import HttpClient, RateLimiter, SendHook, SendRecord, notify_send

from ._parse import expect_object
from ._upload import open_source, upload_file_content, upload_file_url

__all__ = ["UserMessageResource"]


class UserMessageResource:
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

    async def send_message(
        self,
        user_openid: str,
        *,
        content: str | None = None,
        markdown: MessageMarkdown | None = None,
        media: MediaInfo | None = None,
        keyboard: Keyboard | None = None,
        reply_to: str | None = None,
        event_id: str | None = None,
        msg_seq: int | None = None,
        is_wakeup: bool = False,
    ) -> UserMessageReceipt:
        """发单聊消息。

        被动回复需带reply_to指向回复消息id, 有效期 60 分钟。
        同一个 msg_id + msg_seq 重复发送会被拒, 要回第二次传msg_seq=2。
        is_wakeup是互动召回消息, 与 reply_to / event_id 互斥。

        keyboard 只在 Markdown 消息上渲染。
        """

        path = f"/v2/users/{user_openid}/messages"
        proactive = reply_to is None and event_id is None
        draft: UserMessageDraft | None = None
        try:
            if self._limiter is not None:
                self._limiter.check("c2c", user_openid, active=proactive)
            if reply_to is not None and msg_seq is None:
                msg_seq = 1
            draft = UserMessageDraft(
                content=content,
                markdown=markdown,
                media=media,
                keyboard=keyboard,
                msg_id=reply_to,
                event_id=event_id,
                msg_seq=msg_seq,
                is_wakeup=is_wakeup or None,
            )
            payload = await self._http.post(
                path,
                json=draft.model_dump(by_alias=True, exclude_none=True, mode="json"),
            )
        except QQBotError as error:
            await notify_send(
                self._hook,
                SendRecord(
                    scope="c2c",
                    target=user_openid,
                    path=path,
                    proactive=proactive,
                    message=draft,
                    error=error,
                ),
            )
            raise
        receipt = UserMessageReceipt.model_validate(expect_object(payload, path))
        await notify_send(
            self._hook,
            SendRecord(
                scope="c2c",
                target=user_openid,
                path=path,
                proactive=proactive,
                message=draft,
                message_id=receipt.id,
            ),
        )
        return receipt

    async def notify_input(self, user_openid: str, *, seconds: int = 60) -> UserMessageReceipt:
        """给用户展示机器人正在输入, 最多 60 秒。

        这是独立的 msg_type=6 消息, 不承载正文。
        """

        path = f"/v2/users/{user_openid}/messages"
        draft = UserMessageDraft(input_notify=InputNotify(input_second=seconds))
        payload = await self._http.post(
            path,
            json=draft.model_dump(by_alias=True, exclude_none=True, mode="json"),
        )
        return UserMessageReceipt.model_validate(expect_object(payload, path))

    async def recall_message(self, user_openid: str, message_id: str) -> None:
        """撤回单聊消息, 发送后 2 分钟内有效。"""

        path = f"/v2/users/{user_openid}/messages/{message_id}"
        await self._http.request("DELETE", path)

    async def upload_file(
        self,
        user_openid: str,
        file_type: FileType,
        /,
        *,
        url: str | None = None,
        file: str | Path | BinaryIO | bytes | None = None,
        file_name: str | None = None,
        srv_send_msg: bool = False,
        progress: Callable[[int, int], None] | None = None,
    ) -> UploadedFile:
        """上传单聊富媒体(图片 / 视频 / 语音 / 文件)。

        构造与群聊一致: url 与 file 二选一, file 由 SDK 按体积自动选择直传或分片,
        摘要由 SDK 计算。srv_send_msg=True 时服务端上传后立即发送,
        会占用主动消息频次并产生发送记录。
        """

        if (url is None) == (file is None):
            raise ValueError("upload_file needs exactly one of url or file")

        path = f"/v2/users/{user_openid}/files"
        if srv_send_msg and self._limiter is not None:
            self._limiter.check("c2c", user_openid, active=True)

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
                        prefix=f"/v2/users/{user_openid}",
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
                        scope="c2c",
                        target=user_openid,
                        path=path,
                        proactive=True,
                        message=None,
                        message_id=uploaded.id if uploaded is not None else None,
                        error=error,
                    ),
                )
        assert uploaded is not None
        return uploaded
