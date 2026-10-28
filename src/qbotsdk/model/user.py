# Copyright (c) 2026-present Half_nothing.

"""用户对象。"""

from __future__ import annotations

from pydantic import Field

from .base import QQModel


class User(QQModel):
    """最小的用户标识：只有 `id`。"""

    id: str = Field(alias="id")

    @property
    def openid(self) -> str | None:
        """场景相关的 openid；基类没有这个概念。"""

        return None


class GuildUser(User):
    """频道场景的用户，消息作者、成员列表里的 user、READY 里的机器人自己。"""

    username: str = Field(alias="username")
    # READY 的示例里没有 avatar, 频道成员与消息作者里都有, 因此允许缺省
    avatar: str | None = Field(alias="avatar", default=None)
    # 官方文档写了 bot, 但部分接口不返回, 都调用这个库了默认就是机器人
    bot: bool = Field(alias="bot", default=True)
    union_openid: str | None = Field(alias="union_openid", default=None)
    union_user_account: str | None = Field(alias="union_user_account", default=None)
    # 以下两个只在成员列表的 user 对象里出现
    public_flags: int | None = Field(alias="public_flags", default=None)
    system: bool | None = Field(alias="system", default=None)


class GroupUser(User):
    """群聊事件里的作者，以member_openid标识群成员。"""

    member_openid: str = Field(alias="member_openid")
    username: str = Field(alias="username", default="")
    # 官方在事件里给出作者是否为机器人; 缺省按人类处理
    bot: bool = Field(alias="bot", default=False)
    union_openid: str | None = Field(alias="union_openid", default=None)
    user_openid: str | None = Field(alias="user_openid", default=None)
    member_role: str | None = Field(alias="member_role", default=None)

    @property
    def openid(self) -> str | None:
        return self.member_openid


class MentionUser(GroupUser):
    """群聊消息 mentions 里的被 @ 成员。

    is_you 表示被 @ 的是不是机器人自己, cope 描述这次 @ 的作用范围。
    """

    is_you: bool = Field(alias="is_you", default=False)
    scope: str | None = Field(alias="scope", default=None)


class C2CUser(User):
    """单聊事件里的作者，以 user_openid 标识用户。"""

    user_openid: str = Field(alias="user_openid")
    username: str = Field(alias="username", default="")
    bot: bool = Field(alias="bot", default=False)
    union_openid: str | None = Field(alias="union_openid", default=None)
    union_user_account: str | None = Field(alias="union_user_account", default=None)

    @property
    def openid(self) -> str | None:
        return self.user_openid
