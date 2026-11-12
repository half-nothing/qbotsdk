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

"""消息域。

群消息的「回复」并不是单独接口, 就是往群里发一条带 `msg_id` 的消息。
事件层 (`event.reply()`) 会自动填 `msg_id` 与递增的 `msg_seq`, 这一层留给
拿到 `msg_id` 但手上没有事件对象的场景。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .group import GroupResource

if TYPE_CHECKING:
    from qbotsdk.model.draft import MessageMarkdown
    from qbotsdk.model.keyboard import Keyboard
    from qbotsdk.model.media import MediaInfo
    from qbotsdk.model.message import GroupMessageReceipt
    from qbotsdk.module.http_client import HttpClient
    from qbotsdk.module.send_hook import SendHook

__all__ = ["MessageResource"]


class MessageResource:
    def __init__(self, http: HttpClient, *, hook: SendHook | None = None) -> None:
        self._http = http
        self._group = GroupResource(http, hook=hook)

    async def reply(
        self,
        group_openid: str,
        /,
        *,
        msg_id: str,
        content: str | None = None,
        markdown: MessageMarkdown | None = None,
        media: MediaInfo | None = None,
        keyboard: Keyboard | None = None,
        msg_seq: int | None = None,
    ) -> GroupMessageReceipt:
        """回复群消息。

        被动回复有效期为 5 分钟, 每条消息最多回 5 次
        回第二次要显式给 msg_seq=2
        """

        return await self._group.send_message(
            group_openid,
            content=content,
            markdown=markdown,
            media=media,
            keyboard=keyboard,
            reply_to=msg_id,
            msg_seq=msg_seq,
        )
