# Copyright (c) 2026-present Half_nothing.

"""用户域接口。"""

from __future__ import annotations

from collections.abc import AsyncIterator

from ..model.guild import Guild
from ..model.user import User
from ..module.http_client import HTTPClient
from ..module.pagination import paginate
from ._parse import expect_list, expect_object

_ME_PATH = "/users/@me"
_GUILDS_PATH = "/users/@me/guilds"


class UserResource:
    def __init__(self, http: HTTPClient) -> None:
        self._http = http

    async def me(self) -> User:
        """当前机器人自身信息。"""

        payload = expect_object(await self._http.get(_ME_PATH), _ME_PATH)
        return User.model_validate(payload)

    async def guilds(
        self,
        *,
        before: str | None = None,
        after: str | None = None,
        limit: int = 100,
    ) -> list[Guild]:
        """机器人加入的频道列表，limit 上限 100；before 与 after 同给时 after 失效。"""

        params: dict[str, str | int] = {"limit": limit}
        if before is not None:
            params["before"] = before
        if after is not None:
            params["after"] = after
        payload = expect_list(await self._http.get(_GUILDS_PATH, params=params), _GUILDS_PATH)
        return [Guild.model_validate(item) for item in payload]

    async def iter_guilds(self, *, limit: int = 100) -> AsyncIterator[Guild]:
        """自动翻页遍历全部频道，某页不足 limit 即结束。"""

        async def fetch_page(cursor: str | None) -> list[Guild]:
            return await self.guilds(after=cursor, limit=limit)

        def cursor_of(page: list[Guild]) -> str | None:
            return page[-1].id

        async for guild in paginate(fetch_page, cursor_of=cursor_of, page_size=limit):
            yield guild
