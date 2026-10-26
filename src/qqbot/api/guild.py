# Copyright (c) 2026-present Half_nothing.

"""频道（guild）域接口。"""

from __future__ import annotations

from ..model.channel import Channel
from ..model.guild import Guild
from ..model.member import Member
from ..model.role import RolesResult
from ..module.http_client import HTTPClient
from ._parse import expect_list, expect_object


class GuildResource:
    def __init__(self, http: HTTPClient) -> None:
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
        成员列表，游标翻页
        after 传上一页最后一个成员的 user.id，limit 上限 400。
        平台可能重复返回已给过的成员，翻页时需按 `user.id` 去重。
        """

        path = f"/guilds/{guild_id}/members"
        params: dict[str, str | int] = {"after": after, "limit": limit}
        payload = expect_list(await self._http.get(path, params=params), path)
        return [Member.model_validate(item) for item in payload]

    async def roles(self, guild_id: str) -> RolesResult:
        """身份组列表。"""

        path = f"/guilds/{guild_id}/roles"
        return RolesResult.model_validate(expect_object(await self._http.get(path), path))
