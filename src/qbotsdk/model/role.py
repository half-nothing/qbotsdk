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

"""频道身份组模型。

参考文档: https://bot.q.qq.com/wiki/develop/api-v2/server-inter/channel/role-group/get_guild_roles.html
"""

from __future__ import annotations

from pydantic import Field

from .base import QQModel

__all__ = ["Role", "RolesResult"]


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
