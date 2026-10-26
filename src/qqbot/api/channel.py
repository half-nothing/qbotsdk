# Copyright (c) 2026-present Half_nothing.

"""子频道域接口。"""

from __future__ import annotations

from ..model.channel import Channel
from ..module.http_client import HTTPClient
from ._parse import expect_object


class ChannelResource:
    def __init__(self, http: HTTPClient) -> None:
        self._http = http

    async def get(self, channel_id: str) -> Channel:
        """子频道详情。"""

        path = f"/channels/{channel_id}"
        return Channel.model_validate(expect_object(await self._http.get(path), path))
