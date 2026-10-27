# Copyright (c) 2026-present Half_nothing.

"""消息域。

群消息的「回复」并不是单独接口, 就是往群里发一条带 `msg_id` 的消息。
事件层 (`event.reply()`) 会自动填 `msg_id` 与递增的 `msg_seq`, 这一层留给
拿到 `msg_id` 但手上没有事件对象的场景。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .group import GroupResource

if TYPE_CHECKING:
    from ..model.draft import MessageMarkdown
    from ..model.keyboard import Keyboard
    from ..model.media import MediaInfo
    from ..model.message import GroupMessageReceipt
    from ..module.http_client import HTTPClient


class MessageResource:
    def __init__(self, http: HTTPClient) -> None:
        self._http = http
        self._group = GroupResource(http)

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
