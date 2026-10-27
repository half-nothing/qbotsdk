# Copyright (c) 2026-present Half_nothing.

"""单聊消息域接口。

接口文档: https://bot.q.qq.com/wiki/develop/api-v2/autogen/api/v2_users_user_openid_messages.post.html
被动回复有效期 60 分钟, 每条消息最多回 4 次。
"""

from __future__ import annotations

from ..model.draft import InputNotify, MessageMarkdown, UserMessageDraft
from ..model.keyboard import Keyboard
from ..model.media import FileType, MediaInfo, UploadedFile
from ..model.message import UserMessageReceipt
from ..module.http_client import HTTPClient
from ._parse import expect_object


class UserMessageResource:
    def __init__(self, http: HTTPClient) -> None:
        self._http = http

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

        被动回复需带 reply_to，有效期 60 分钟
        同一个 msg_id + msg_seq 重复发送会被拒，要回第二次请显式传 msg_seq=2
        is_wakeup=True 是互动召回消息，与 reply_to / event_id 互斥。
        """

        path = f"/v2/users/{user_openid}/messages"
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
        return UserMessageReceipt.model_validate(expect_object(payload, path))

    async def notify_input(self, user_openid: str, *, seconds: int = 60) -> UserMessageReceipt:
        """给用户展示「机器人正在输入」，最多 60 秒。

        这是独立的 msg_type=6 消息，不承载正文。
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
        url: str,
        srv_send_msg: bool = False,
    ) -> UploadedFile:
        """上传单聊富媒体。

        只实现 url 方式：单聊的二进制直传官方文档没有给字段表
        返回的 file_info 填进 send_message 的 media。
        srv_send_msg=True 时服务端上传后立即发送，会占用主动消息频次。
        """

        path = f"/v2/users/{user_openid}/files"
        payload = await self._http.post(
            path,
            json={
                "file_type": int(file_type),
                "url": url,
                "srv_send_msg": srv_send_msg,
            },
        )
        return UploadedFile.model_validate(expect_object(payload, path))
