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

"""频道(guild)域接口。"""

from __future__ import annotations

from collections.abc import AsyncIterator

from qbotsdk.model import Channel, Guild, Member, RolesResult
from qbotsdk.module import HttpClient, paginate

from ._parse import expect_list, expect_object

__all__ = ["GuildResource"]


class GuildResource:
    def __init__(self, http: HttpClient) -> None:
        self._http = http

    async def get(self, guild_id: str) -> Guild:
        """频道详情。"""

        path = f"/guilds/{guild_id}"
        return Guild.model_validate(expect_object(await self._http.get(path), path))

    async def channels(self, guild_id: str) -> list[Channel]:
        """子频道列表。"""

        path = f"/guilds/{guild_id}/channels"
        payload = expect_list(await self._http.get(path), path)
        return [Channel.model_validate(item) for item in payload]

    async def members(
        self,
        guild_id: str,
        *,
        after: str = "0",
        limit: int = 100,
    ) -> list[Member]:
        """
        成员列表, 游标翻页
        after 传上一页最后一个成员的 user.id, limit 上限 400。
        平台可能重复返回已给过的成员, 翻页时需按 `user.id` 去重。
        """

        path = f"/guilds/{guild_id}/members"
        params: dict[str, str | int] = {"after": after, "limit": limit}
        payload = expect_list(await self._http.get(path, params=params), path)
        return [Member.model_validate(item) for item in payload]

    async def iter_members(self, guild_id: str, *, limit: int = 100) -> AsyncIterator[Member]:
        """自动翻页遍历频道成员, 按 `user.id` 去重, 空页结束。"""

        async def fetch_page(cursor: str | None) -> list[Member]:
            return await self.members(guild_id, after=cursor or "0", limit=limit)

        def cursor_of(page: list[Member]) -> str | None:
            return page[-1].user.id

        def key_of(member: Member) -> str:
            return member.user.id

        async for member in paginate(fetch_page, cursor_of=cursor_of, key_of=key_of):
            yield member

    async def roles(self, guild_id: str) -> RolesResult:
        """身份组列表。"""

        path = f"/guilds/{guild_id}/roles"
        return RolesResult.model_validate(expect_object(await self._http.get(path), path))
