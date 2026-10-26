# Copyright (c) 2026-present Half_nothing.

"""群组（QQ 群）模型，字段逐条对应官方「群聊管理」响应体。"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import Field

from .base import QQModel


class GroupMemberRole(StrEnum):
    """群成员角色。"""

    MEMBER = "member"
    OWNER = "owner"
    ADMIN = "admin"


class RecvMsgSetting(StrEnum):
    """机器人在群内接收消息的范围。"""

    ALL = "all"
    ONLY_MENTION = "only_mention"
    MENTION_AND_CONTEXT = "mention_and_context"


class MuteMode(StrEnum):
    """全员禁言模式。"""

    NONE = "none"
    ALWAYS = "always"
    SCHEDULE = "schedule"


class Group(QQModel):
    """群基本信息，GET /v2/groups/{group_openid}/info`。"""

    group_openid: str = Field(alias="group_openid")
    group_name: str = Field(alias="group_name")
    group_finger_memo: str = Field(alias="group_finger_memo", description="群简介")
    group_class_text: str = Field(alias="group_class_text", description="群分类")
    group_tags: list[str] = Field(alias="group_tags", default_factory=list)
    group_member_num: int = Field(alias="group_member_num")


class GroupMember(QQModel):
    """群成员，GET /v2/groups/{group_openid}/members。"""

    member_openid: str = Field(alias="member_openid")
    username: str = Field(alias="username")
    member_role: GroupMemberRole = Field(alias="member_role")
    bot: bool = Field(alias="bot")
    joined_at: datetime = Field(alias="joined_at", description="入群时间，RFC3339")
    # 官方标注「如有」，未绑定统一标识时不返回
    union_openid: str | None = Field(alias="union_openid", default=None)


class GroupMembersPage(QQModel):
    """群成员分页，官方每次最多 30 条，`next_cursor` 为空串表示末页。"""

    members: list[GroupMember] = Field(alias="members")
    next_cursor: str = Field(alias="next_cursor")


class GroupBotState(QQModel):
    """机器人在群内的状态，GET /v2/groups/{group_openid}/bot_state。"""

    member_openid: str = Field(alias="member_openid")
    joined_at: datetime = Field(alias="joined_at", description="入群时间，RFC3339")
    allow_proactive_msg: bool = Field(alias="allow_proactive_msg")
    recv_msg_setting: RecvMsgSetting = Field(alias="recv_msg_setting")
    member_role: GroupMemberRole = Field(alias="member_role")


class MuteScheduleRule(QQModel):
    """定时禁言规则。"""

    task_id: str = Field(alias="task_id")
    start_at: datetime = Field(alias="start_at")
    end_at: datetime = Field(alias="end_at")
    enabled: bool = Field(alias="enabled")


class MuteRecurringRule(QQModel):
    """周期禁言规则，时间只有 HH:mm，没有日期。"""

    task_id: str = Field(alias="task_id")
    weekdays: list[int] = Field(alias="weekdays", description="1=周一 … 7=周日")
    start_time: str = Field(alias="start_time", description="HH:mm，北京时间")
    end_time: str = Field(alias="end_time", description="HH:mm，小于 start_time 表示跨天")
    enabled: bool = Field(alias="enabled")


class GlobalMuteRule(QQModel):
    """群级禁言规则。"""

    mode: MuteMode = Field(alias="mode")
    schedule_rules: list[MuteScheduleRule] = Field(alias="schedule_rules", default_factory=list)
    recurring_rules: list[MuteRecurringRule] = Field(alias="recurring_rules", default_factory=list)


class MemberMuteState(QQModel):
    """处于禁言中的成员。"""

    member_openid: str = Field(alias="member_openid")
    mute_expire_at: datetime = Field(alias="mute_expire_at")
    username: str = Field(alias="username")
    union_openid: str | None = Field(alias="union_openid", default=None)


class GroupMuteState(QQModel):
    """群禁言状态，`GET /v2/groups/{group_openid}/restrict_chat_setting`。"""

    global_rule: GlobalMuteRule = Field(alias="global_rule")
    members: list[MemberMuteState] = Field(alias="members", default_factory=list)
