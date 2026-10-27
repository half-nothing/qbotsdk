# Copyright (c) 2026-present Half_nothing.

"""表情表态对象。

- 表情对象(Emoji): https://bot.q.qq.com/wiki/develop/api-v2/openapi/emoji/model.html
- 表情表态对象(MessageReaction): https://bot.q.qq.com/wiki/develop/api-v2/openapi/reaction/model.html
- 用户列表(ReactionUsers): https://bot.q.qq.com/wiki/develop/pythonsdk/api/reaction/get_reaction_users.html
"""

from __future__ import annotations

from enum import IntEnum

from pydantic import Field

from .base import QQModel
from .user import GuildUser


class EmojiType(IntEnum):
    """表情类型。"""

    SYSTEM = 1  # 系统表情, id 是数字
    EMOJI = 2  # emoji 表情, id 是 emoji 本身


class ReactionTargetType(IntEnum):
    """表态对象类型。"""

    MESSAGE = 0  # 消息
    POST = 1  # 帖子
    COMMENT = 2  # 评论
    REPLY = 3  # 回复


class Emoji(QQModel):
    """表情对象。"""

    id: str = Field(alias="id", description="表情 ID, 系统表情用数字, emoji 用 emoji 本身")
    type: int = Field(alias="type", description="表情类型, 参考 EmojiType")


class ReactionTarget(QQModel):
    """表态对象。"""

    id: str = Field(alias="id", description="表态对象 ID")
    type: int = Field(alias="type", description="表态对象类型, 参考 ReactionTargetType")


class MessageReaction(QQModel):
    """消息上的表情表态。"""

    user_id: str = Field(alias="user_id", description="用户 ID")
    guild_id: str = Field(alias="guild_id", description="频道 ID")
    channel_id: str = Field(alias="channel_id", description="子频道 ID")
    target: ReactionTarget = Field(alias="target", description="表态对象")
    emoji: Emoji = Field(alias="emoji", description="表态所用表情")


class ReactionUsers(QQModel):
    """某个表情表态下的用户列表。"""

    users: list[GuildUser] = Field(default_factory=list, alias="users", description="用户列表")
    cookie: str = Field(default="", alias="cookie", description="下一页游标, 空串表示没有下一页")
    is_end: bool = Field(default=False, alias="is_end", description="是否最后一页")
