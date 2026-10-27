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
from .draft import MessageReference
from .member import Member
from .user import GuildUser


class MessageAttachment(QQModel):
    """消息附件。官方只给了下载地址。"""

    url: str = Field(alias="url")


class MessageExtInfo(QQModel):
    """群消息回执里的扩展信息。"""

    ref_idx: str = Field(alias="ref_idx")


class MessageReceipt(QQModel):
    """发送消息的返回值。"""

    id: str = Field(alias="id")
    timestamp: datetime = Field(alias="timestamp")
    ext_info: MessageExtInfo | None = Field(alias="ext_info", default=None)


class GroupMessageReceipt(MessageReceipt):
    """群聊发送消息的返回值。"""


class UserMessageReceipt(MessageReceipt):
    """单聊发送消息的返回值。"""


class Message(QQModel):
    """频道消息对象。

    来源官方消息对象表格:
    https://bot.q.qq.com/wiki/develop/api-v2/server-inter/message/template/model.html
    """

    id: str = Field(alias="id")
    channel_id: str = Field(alias="channel_id")
    guild_id: str = Field(alias="guild_id")
    content: str = Field(alias="content")
    timestamp: datetime = Field(alias="timestamp")
    tts: bool = Field(alias="tts")
    mention_everyone: bool = Field(alias="mention_everyone")
    author: GuildUser = Field(alias="author")
    # 示例里是 [{}], 具体结构见 Embed 消息页面, 本期不解析
    embeds: list[dict[str, Any]] = Field(alias="embeds")
    pinned: bool = Field(alias="pinned")
    type: int = Field(alias="type")
    flags: int = Field(alias="flags")
    # 以下字段来自 Message 表格, 发送响应示例里没有
    edited_timestamp: datetime | None = Field(alias="edited_timestamp", default=None)
    attachments: list[MessageAttachment] = Field(alias="attachments", default_factory=list)
    mentions: list[GuildUser] = Field(alias="mentions", default_factory=list)
    member: Member | None = Field(alias="member", default=None)
    ark: dict[str, Any] | None = Field(alias="ark", default=None)
    # 官方标注 seq 只在消息事件中有值、2022-08-01 后废弃
    seq: int | None = Field(alias="seq", default=None)
    seq_in_channel: str | None = Field(alias="seq_in_channel", default=None)
    message_reference: MessageReference | None = Field(alias="message_reference", default=None)
