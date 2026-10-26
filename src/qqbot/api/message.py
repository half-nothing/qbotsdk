# Copyright (c) 2026-present Half_nothing.

"""消息域，Phase 2 填充。现在只占位，保证 `bot.api.message` 一直存在。"""

from __future__ import annotations

from ..module.http_client import HTTPClient


class MessageResource:
    def __init__(self, http: HTTPClient) -> None:
        self._http = http
