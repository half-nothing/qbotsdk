# Copyright (c) 2026-present Half_nothing.

"""频道成员模型。

参考文档：https://bot.q.qq.com/wiki/develop/api-v2/server-inter/channel/role/member/get_members.html
"""

from __future__ import annotations

from datetime import datetime

from pydantic import Field

from .base import QQModel
from .user import GuildUser


class Member(QQModel):
    """`GET /guilds/{guild_id}/members` 的数组元素。"""

    user: GuildUser = Field(alias="user")
    nick: str = Field(alias="nick")
    roles: list[str] = Field(alias="roles")
    joined_at: datetime = Field(alias="joined_at")
    deaf: bool = Field(alias="deaf")
    mute: bool = Field(alias="mute")
    pending: bool = Field(alias="pending")
