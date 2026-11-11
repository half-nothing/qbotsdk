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

"""频道成员模型。

参考文档: https://bot.q.qq.com/wiki/develop/api-v2/server-inter/channel/role/member/get_members.html
"""

from __future__ import annotations

from datetime import datetime

from pydantic import Field

from .base import QQModel
from .user import GuildUser

__all__ = ["Member"]


class Member(QQModel):
    """GET /guilds/{guild_id}/members 的数组元素。"""

    user: GuildUser = Field(alias="user")
    nick: str | None = Field(alias="nick", default=None)
    roles: list[str] = Field(alias="roles", default_factory=list)
    joined_at: datetime = Field(alias="joined_at")
    deaf: bool = Field(alias="deaf", default=False)
    mute: bool = Field(alias="mute", default=False)
    pending: bool = Field(alias="pending", default=False)
