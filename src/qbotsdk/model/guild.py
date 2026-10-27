# Copyright (c) 2026-present Half_nothing.

"""频道 (Guild) 模型。

参考文档：https://bot.q.qq.com/wiki/develop/api-v2/autogen/api/guilds_guild_id.get.html
"""

from __future__ import annotations

from datetime import datetime

from pydantic import Field

from .base import QQModel


class Guild(QQModel):
    """频道对象。"""

    id: str = Field(alias="id")
    name: str = Field(alias="name")
    icon: str = Field(alias="icon")
    owner_id: str = Field(alias="owner_id")
    # 当前机器人是否为频道创建者
    owner: bool = Field(alias="owner")
    member_count: int = Field(alias="member_count")
    max_members: int = Field(alias="max_members")
    description: str = Field(alias="description")
    joined_at: datetime = Field(alias="joined_at")
