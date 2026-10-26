# Copyright (c) 2026-present Half_nothing.

"""消息相关模型。

- 频道消息: https://bot.q.qq.com/wiki/develop/api-v2/server-inter/channel/message/send.html
- 群消息回执: https://bot.q.qq.com/wiki/develop/api-v2/autogen/api/v2_groups_group_openid_messages.post.html
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import Field

from .base import QQModel
from .user import User


class MessageExtInfo(QQModel):
    """群消息回执里的扩展信息。"""

    ref_idx: str = Field(alias="ref_idx")


class GroupMessageReceipt(QQModel):
    """群发送消息的返回值。

    群聊接口不返回完整消息, 只有消息 ID 与时间戳, 撤回时需要这里的 `id`。
    """

    id: str = Field(alias="id")
    timestamp: datetime = Field(alias="timestamp")
    ext_info: MessageExtInfo | None = Field(alias="ext_info", default=None)


class Message(QQModel):
    """频道消息对象, 频道发送消息接口的返回值。"""

    id: str = Field(alias="id")
    channel_id: str = Field(alias="channel_id")
    guild_id: str = Field(alias="guild_id")
    content: str = Field(alias="content")
    timestamp: datetime = Field(alias="timestamp")
    tts: bool = Field(alias="tts")
    mention_everyone: bool = Field(alias="mention_everyone")
    author: User = Field(alias="author")
    # 示例里是 [{}], 具体结构见 Embed 消息页面, 本期不解析
    embeds: list[dict[str, Any]] = Field(alias="embeds")
    pinned: bool = Field(alias="pinned")
    type: int = Field(alias="type")
    flags: int = Field(alias="flags")
