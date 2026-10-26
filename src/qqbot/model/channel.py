# Copyright (c) 2026-present Half_nothing.

"""子频道 (Channel) 模型与相关枚举。

参考文档：https://bot.q.qq.com/wiki/develop/api-v2/autogen/api/channels_channel_id.get.html
"""

from __future__ import annotations

from enum import IntEnum

from pydantic import Field

from .base import QQModel


class ChannelType(IntEnum):
    """子频道类型，官方字段是 integer。"""

    TEXT = 0  # 文字
    AUDIO = 2  # 语音
    GROUP = 4  # 分组
    LIVE = 10005  # 直播
    APP = 10006  # 应用
    FORUM = 10007  # 论坛


class ChannelSubType(IntEnum):
    """文字子频道的子类型。"""

    CHAT = 0  # 闲聊
    ANNOUNCEMENT = 1  # 公告
    STRATEGY = 2  # 攻略
    TEAM = 3  # 开黑


class PrivateType(IntEnum):
    """子频道私密类型。"""

    PUBLIC = 0  # 公开
    ADMIN_ONLY = 1  # 群主管理员可见
    ADMIN_AND_MEMBERS = 2  # 群主管理员与指定成员


class SpeakPermission(IntEnum):
    """子频道发言权限。"""

    INVALID = 0  # 无效
    EVERYONE = 1  # 所有人
    ADMIN_AND_MEMBERS = 2  # 群主管理员与指定成员


class Channel(QQModel):
    """子频道对象。"""

    id: str = Field(alias="id")
    guild_id: str = Field(alias="guild_id")
    name: str = Field(alias="name")
    type: ChannelType = Field(alias="type")
    sub_type: ChannelSubType = Field(alias="sub_type")
    position: int = Field(alias="position")
    parent_id: str = Field(alias="parent_id")
    owner_id: str = Field(alias="owner_id")
    # 官方 Python SDK 的列表示例里没有这两个字段, 因此按可选处理
    private_type: PrivateType | None = Field(alias="private_type", default=None)
    speak_permission: SpeakPermission | None = Field(alias="speak_permission", default=None)
    # 仅应用子频道返回
    application_id: str | None = Field(alias="application_id", default=None)
    # 仅子频道详情返回
    permissions: str | None = Field(alias="permissions", default=None)
