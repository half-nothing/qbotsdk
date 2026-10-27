# Copyright (c) 2026-present Half_nothing.

"""频道身份组模型。

参考文档：https://bot.q.qq.com/wiki/develop/api-v2/server-inter/channel/role-group/get_guild_roles.html
"""

from __future__ import annotations

from pydantic import Field

from .base import QQModel


class Role(QQModel):
    """频道身份组对象。"""

    id: str = Field(alias="id")
    name: str = Field(alias="name")
    color: int = Field(alias="color")
    hoist: int = Field(alias="hoist")
    number: int = Field(alias="number")
    member_limit: int = Field(alias="member_limit")


class RolesResult(QQModel):
    """`GET /guilds/{guild_id}/roles` 的返回对象。"""

    guild_id: str = Field(alias="guild_id")
    roles: list[Role] = Field(alias="roles")
    role_num_limit: str = Field(alias="role_num_limit")
