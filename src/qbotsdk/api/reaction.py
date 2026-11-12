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

"""表情表态接口。

- 发表 / 删除: https://bot.q.qq.com/wiki/develop/pythonsdk/api/reaction/post_reaction.html
- 用户列表: https://bot.q.qq.com/wiki/develop/pythonsdk/api/reaction/get_reaction_users.html
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from qbotsdk.model import GuildUser, ReactionUsers
from qbotsdk.module import HttpClient, paginate

__all__ = ["ReactionResource"]

_MAX_LIMIT = 100
_DEFAULT_LIMIT = 20


class ReactionResource:
    """子频道消息上的表情表态。"""

    def __init__(self, http: HttpClient) -> None:
        self._http = http

    @staticmethod
    def _path(channel_id: str, message_id: str, emoji_type: int) -> str:
        return f"/channels/{channel_id}/messages/{message_id}/reactions/{emoji_type}"

    async def add(
        self,
        channel_id: str,
        message_id: str,
        emoji_type: int,
        emoji_id: str,
    ) -> None:
        """给消息发表表情表态。

        Args:
            channel_id: 子频道 ID
            message_id: 消息 ID
            emoji_type: 表情类型, 参考 EmojiType
            emoji_id: 表情 ID, 系统表情是数字, emoji 表情是 emoji 本身
        """

        path = f"{self._path(channel_id, message_id, emoji_type)}/{emoji_id}"
        await self._http.put(path)

    async def remove(
        self,
        channel_id: str,
        message_id: str,
        emoji_type: int,
        emoji_id: str,
    ) -> None:
        """删除机器人自己发表的表态。"""

        path = f"{self._path(channel_id, message_id, emoji_type)}/{emoji_id}"
        await self._http.request("DELETE", path)

    async def users(
        self,
        channel_id: str,
        message_id: str,
        emoji_type: int,
        *,
        emoji_id: str | None = None,
        cookie: str = "",
        limit: int = _DEFAULT_LIMIT,
    ) -> ReactionUsers:
        """拉取某个表情表态的用户列表。

        Args:
            channel_id: 子频道 ID
            message_id: 消息 ID
            emoji_type: 表情类型, 参考 EmojiType
            emoji_id: 表情 ID, 同一种类型下要区分具体表情时传
            cookie: 上一页返回的 cookie, 第一页留空
            limit: 本页最多返回多少用户, 1-100
        """

        if not 1 <= limit <= _MAX_LIMIT:
            raise ValueError("limit must be between 1 and 100")
        params: dict[str, str] = {"cookie": cookie, "limit": str(limit)}
        if emoji_id is not None:
            params["emoji_id"] = emoji_id
        path = self._path(channel_id, message_id, emoji_type)
        payload = await self._http.get(path, params=params)
        return ReactionUsers.model_validate(payload)

    async def iter_users(
        self,
        channel_id: str,
        message_id: str,
        emoji_type: int,
        *,
        emoji_id: str | None = None,
        limit: int = _DEFAULT_LIMIT,
    ) -> AsyncIterator[GuildUser]:
        """逐条产出该表情下的用户, 按 user.id 去重。"""

        next_cookie = ""
        is_end = False

        async def fetch_page(cursor: str | None) -> list[GuildUser]:
            nonlocal next_cookie, is_end
            page = await self.users(
                channel_id,
                message_id,
                emoji_type,
                emoji_id=emoji_id,
                cookie=cursor or "",
                limit=limit,
            )
            next_cookie = page.cookie
            is_end = page.is_end
            return page.users

        def cursor_of(_: list[GuildUser]) -> str | None:
            return None if is_end else next_cookie

        async for user in paginate(fetch_page, cursor_of=cursor_of, key_of=lambda user: user.id):
            yield user
