# Copyright (c) 2026-present Half_nothing.

"""消息域。

本期只留将来 `reply()` 的入口，真正实现要拿到事件里的 `msg_id`，属于 Phase 3。
"""

from __future__ import annotations

from ..module.http_client import HTTPClient


class MessageResource:
    def __init__(self, http: HTTPClient) -> None:
        self._http = http

    async def reply(self, message_id: str, content: str, /) -> None:
        """按消息 ID 回复，Phase 3 随事件层一起实现。

        这里刻意抛异常而不是静默返回: 静默 `pass` 会让调用方以为消息已发出,
        等线上「机器人不回话」才发现。
        """

        raise NotImplementedError("message.reply is available from the event layer in phase 3")
