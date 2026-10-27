# Copyright (c) 2026-present Half_nothing.

"""网关下发的 `t` 事件模型。"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import Field

from .base import QQModel
from .scene import Attachment, MessageElement, MessageScene
from .user import GroupUser, GuildUser


class ReadyEvent(QQModel):
    """t = READY，鉴权成功后下发。"""

    version: int = Field(alias="version", default=0)
    session_id: str = Field(alias="session_id", default="")
    user: GuildUser = Field(alias="user")
    shard: list[int] = Field(alias="shard", default_factory=list)


class ResumedEvent(QQModel):
    """t = RESUMED，Resume 补发完成后下发。官方 `d` 是空对象。"""


class GroupAtMessageCreate(QQModel):
    """t = GROUP_AT_MESSAGE_CREATE，群聊里 @ 机器人。"""

    id: str = Field(alias="id")
    author: GroupUser = Field(alias="author")
    content: str = Field(alias="content", default="")
    group_openid: str = Field(alias="group_openid")
    timestamp: datetime = Field(alias="timestamp")
    message_type: int | None = Field(alias="message_type", default=None)
    message_scene: MessageScene | None = Field(alias="message_scene", default=None)
    attachments: list[Attachment] = Field(alias="attachments", default_factory=list)
    mentions: list[GroupUser] = Field(alias="mentions", default_factory=list)
    msg_elements: list[MessageElement] = Field(alias="msg_elements", default_factory=list)


class UnknownEvent(QQModel):
    """未建模的事件，保留 t 与原始 d。"""

    t: str = Field(alias="t")
    data: Any = Field(alias="data", default=None)
