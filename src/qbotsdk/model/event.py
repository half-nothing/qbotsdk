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

"""网关下发的 t 事件模型。"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import IntEnum
from typing import TYPE_CHECKING, Any, Final, Protocol, override

from async_event_bus import AbstractEvent
from pydantic import ConfigDict, Field, PrivateAttr, field_validator

from .base import QQModel
from .channel import ChannelSubType, ChannelType
from .join_request import AutoApproved, JoinRequest
from .message import Message
from .scene import ARKData, Attachment, MessageElement, MessageScene, split_ext
from .user import C2CUser, GroupUser, GuildUser, MentionUser

if TYPE_CHECKING:
    from .draft import MessageMarkdown
    from .keyboard import Keyboard
    from .media import MediaInfo
    from .message import GroupMessageReceipt, UserMessageReceipt

__all__ = [
    "C2C_REPLY_LIMIT",
    "EVENT_MODELS",
    "GROUP_REPLY_LIMIT",
    "ApiProtocol",
    "AuthorizeData",
    "C2CMessageCreate",
    "C2CMsgReceive",
    "C2CMsgReject",
    "ChannelCreate",
    "ChannelDelete",
    "ChannelEvent",
    "ChannelMessageCreate",
    "ChannelSender",
    "ChannelUpdate",
    "ChatSender",
    "DirectMessageCreate",
    "EventModel",
    "FriendAdd",
    "FriendAuthor",
    "FriendDel",
    "GroupAddRobot",
    "GroupAtMessageCreate",
    "GroupDelRobot",
    "GroupJoinRequest",
    "GroupMemberAdd",
    "GroupMemberRemove",
    "GroupMessageCreate",
    "GroupMsgReceive",
    "GroupMsgReject",
    "GroupSender",
    "GuildCreate",
    "GuildDelete",
    "GuildEvent",
    "GuildMessageCreate",
    "GuildUpdate",
    "InteractionCode",
    "InteractionCreate",
    "InteractionData",
    "InteractionMessageScene",
    "InteractionResolved",
    "InteractionResponder",
    "InteractionType",
    "MessageAudit",
    "MessageAuditPass",
    "MessageAuditReject",
    "ReadyEvent",
    "RenderedMentions",
    "ResumedEvent",
    "UnknownEvent",
    "parse_event",
]

# 官方限制: 群聊每条消息最多被动回复 5 次, 单聊 4 次, 超出会返回 40034128
GROUP_REPLY_LIMIT = 5
C2C_REPLY_LIMIT = 4

# 群聊 content 里的 @ 标记: `<@member_openid>` 或 `<@all>`, 频道消息里还会出现 `<@!openid>`
_MENTION_TAG = re.compile(r"<@!?([^>]+)>")


# 群相关的小事件把时间戳给成 Unix 秒, 其余事件是 RFC3339 字符串
def _parse_epoch(value: object) -> object:
    """把 Unix 秒转成 UTC 时间, 其它形态原样交给 pydantic。"""

    if isinstance(value, int | float):
        return datetime.fromtimestamp(value, tz=UTC)
    return value


# 剥掉 @ 机器人 之后可能留下连续空格, 归成一个
_TIDY_SPACES = re.compile(r"[ \t]{2,}")


class GroupSender(Protocol):
    """ApiClient.group 里事件回复用到的那一小块。"""

    async def send_message(
        self,
        group_openid: str,
        *,
        content: str | None = None,
        markdown: MessageMarkdown | None = None,
        media: MediaInfo | None = None,
        keyboard: Keyboard | None = None,
        reply_to: str | None = None,
        event_id: str | None = None,
        msg_seq: int | None = None,
    ) -> GroupMessageReceipt: ...


class ChatSender(Protocol):
    """ApiClient.user_message 里事件回复用到的那一小块。"""

    async def send_message(
        self,
        user_openid: str,
        *,
        content: str | None = None,
        markdown: MessageMarkdown | None = None,
        media: MediaInfo | None = None,
        keyboard: Keyboard | None = None,
        reply_to: str | None = None,
        event_id: str | None = None,
        msg_seq: int | None = None,
        is_wakeup: bool = False,
    ) -> UserMessageReceipt: ...


class ChannelSender(Protocol):
    """ApiClient.channel 里频道事件回复用到的那一小块。"""

    async def send_message(
        self,
        channel_id: str,
        *,
        content: str | None = None,
        markdown: MessageMarkdown | None = None,
        image: str | None = None,
        reply_to: str | None = None,
        event_id: str | None = None,
    ) -> Message: ...


class InteractionResponder(Protocol):
    """ApiClient.interaction 里回应用到的那一小块。"""

    async def respond(self, interaction_id: str, *, code: int = 0) -> None: ...


class ApiProtocol(Protocol):
    """事件需要的接口面, ApiClient 结构上满足它。"""

    @property
    def group(self) -> GroupSender: ...

    @property
    def user_message(self) -> ChatSender: ...

    @property
    def channel(self) -> ChannelSender: ...

    @property
    def interaction(self) -> InteractionResponder: ...


class EventModel(QQModel, AbstractEvent):
    """SDK 事件模型的公共基类。"""

    model_config = ConfigDict(populate_by_name=True, extra="ignore", frozen=False)

    # 派发前由 Dispatcher 挂上
    _api: ApiProtocol | None = PrivateAttr(default=None)

    # 同一条事件被回复多次时换 msg_seq, 否则服务端按重复消息拒掉
    _reply_seq: int = PrivateAttr(default=0)

    @property
    def api(self) -> ApiProtocol | None:
        """派发这条事件的 Bot 的接口入口。"""

        return self._api

    def bind(self, api: ApiProtocol | None) -> None:
        """把客户端挂到事件上。"""

        self._api = api


class ReadyEvent(EventModel):
    """t = READY, 鉴权成功后下发。"""

    version: int = Field(alias="version", default=0)
    session_id: str = Field(alias="session_id", default="")
    user: GuildUser = Field(alias="user")
    shard: list[int] = Field(alias="shard", default_factory=list)


class ResumedEvent(EventModel):
    """t = RESUMED, Resume 补发完成后下发。官方 `d` 是空对象。"""


@dataclass(frozen=True, slots=True)
class RenderedMentions:
    """把 content 里的 @ 标记渲染后的结果。

    `text` 是渲染过的正文, `mentions` 是按出现顺序去重的成员, 用来查昵称等字段。
    """

    text: str
    mentions: tuple[MentionUser, ...]


class _GroupMessageBase(EventModel):
    """群聊消息事件的公共字段: @ 机器人与全量模式下的载荷一致。"""

    id: str = Field(alias="id")
    author: GroupUser = Field(alias="author")
    content: str = Field(alias="content", default="")
    group_openid: str = Field(alias="group_openid")
    timestamp: datetime = Field(alias="timestamp")
    message_type: int | None = Field(alias="message_type", default=None)
    message_scene: MessageScene | None = Field(alias="message_scene", default=None)
    attachments: list[Attachment] = Field(alias="attachments", default_factory=list)
    mentions: list[MentionUser] = Field(alias="mentions", default_factory=list)
    msg_elements: list[MessageElement] = Field(alias="msg_elements", default_factory=list)

    async def reply(
        self,
        content: str | None = None,
        *,
        markdown: MessageMarkdown | None = None,
        media: MediaInfo | None = None,
        keyboard: Keyboard | None = None,
        msg_seq: int | None = None,
    ) -> GroupMessageReceipt:
        """回复这条群消息。

        自动带本事件的 id 作为 msg_id
        msg_seq 不传时从 1 起按事件自增, 官方上限是每条消息 5 次
        有 markdown 时忽略 content, 两种消息不能同时带
        """

        api = self.api
        if api is None:
            raise ValueError(
                "reply() needs an event dispatched by Bot; use bot.api.group.send_message()"
            )
        if markdown is not None:
            content = None
        if msg_seq is None:
            self._reply_seq += 1
            msg_seq = self._reply_seq
        if msg_seq > GROUP_REPLY_LIMIT:
            raise ValueError("passive reply limit reached")
        return await api.group.send_message(
            self.group_openid,
            content=content,
            markdown=markdown,
            media=media,
            keyboard=keyboard,
            reply_to=self.id,
            msg_seq=msg_seq,
        )

    @property
    def mentioned_me(self) -> bool:
        """机器人自己是否被 @。全量模式下群里每条消息都会下发, 靠 mentions 里的 is_you 判断。"""

        return any(user.is_you for user in self.mentions)

    @property
    def mentions_by_openid(self) -> dict[str, MentionUser]:
        """按 member_openid 索引的 mentions。

        content 里的 <@member_openid> 只能拿到 openid, 要靠这张表还原成成员对象。
        """

        return {user.member_openid: user for user in self.mentions}

    def render_mentions(self, *, strip_me: bool = False) -> str:
        """把 content 里的 @ 标记换成人类可读的 @昵称, 原始 content 保持不变。

        <@member_openid> 换成 @昵称, 昵称缺失时退回 openid
        <@all> 换成 @全体成员, 找不到对应 mention 的标记原样换成 @openid
        strip_me=True 时去掉@机器人自己的那一段
        """

        return self._render(code=False, strip_me=strip_me).text

    def render_mentions_openid(self, *, strip_me: bool = False) -> RenderedMentions:
        """把 content 里的 @ 标记换成 `@openid`, 直接给命令层用。

        保留 `@` 前缀, 命令层仍能一眼看出这是个提及; `mention` 转换器负责剥掉 `@`
        并返回裸 openid。要查昵称等字段用 rendered.mentions 或 `mentions_by_openid`。
        `<@all>` 换成 `@all`, 不并入 mentions。strip_me=True 时去掉 @ 机器人自己的那一段。
        """

        return self._render(code=False, openid=True, strip_me=strip_me)

    def _render(self, *, code: bool, strip_me: bool, openid: bool = False) -> RenderedMentions:
        lookup = self.mentions_by_openid
        used: list[MentionUser] = []

        def replace(match: re.Match[str]) -> str:
            key = match.group(1)
            if key == "all":
                return "@all" if code or openid else "@全体成员"
            user = lookup.get(key)
            if user is None:
                return f"@{key}"
            if user.is_you and strip_me:
                return ""
            if openid:
                if user not in used:
                    used.append(user)
                return f"@{key}"
            if not code:
                return f"@{user.username or key}"
            if user not in used:
                used.append(user)
            return f"@{used.index(user)}"

        text = _MENTION_TAG.sub(replace, self.content)
        # 剥掉 @ 机器人 之后可能留下连续空格, 归成一个
        return RenderedMentions(text=_TIDY_SPACES.sub(" ", text).strip(), mentions=tuple(used))


class GroupAtMessageCreate(_GroupMessageBase):
    """t = GROUP_AT_MESSAGE_CREATE, 群聊里 @ 机器人。

    没有给机器人打开接收全部消息时, 只有@到机器人的消息才会走这个事件。
    开启全量之后不再下发本事件, 全部改走 GroupMessageCreate。
    content 里 @机器人 的前缀已被平台去掉, 消息里 @ 其他人时, 官方没有承诺 content 里保留对应标记。
    """

    @override
    @property
    def mentioned_me(self) -> bool:
        """未开启全量时只有 @ 到机器人本人才会下发本事件, 恒为 True。"""

        return True


class GroupMessageCreate(_GroupMessageBase):
    """t = GROUP_MESSAGE_CREATE, 群聊全量消息。

    给机器人打开接收全部消息后, 群里每条消息都会下发,
    不限于@机器人, 字段与 GROUP_AT_MESSAGE_CREATE 一致。

    开启全量后包括 @ 机器人在内的消息都走本事件,
    不会再下发 GROUP_AT_MESSAGE_CREATE,
    因此判断机器人自己是否被 @ 要看 mentions 条目的 `is_you`。

    该事件里 content 会把 @ 成员写成 <@member_openid>、@ 全体写成 <@all>,
    被@的成员同时出现在 mentions 里。
    """


class _GroupRobotEvent(EventModel):
    """群机器人的增删与消息开关事件共用的时间戳与操作人。"""

    timestamp: datetime = Field(alias="timestamp", description="事件时间, Unix 秒")
    group_openid: str = Field(alias="group_openid", description="群 OpenID")
    op_member_openid: str = Field(alias="op_member_openid", description="操作成员的 OpenID")

    @field_validator("timestamp", mode="before")
    @classmethod
    def _parse_timestamp(cls, value: object) -> object:
        """官方在这几个事件里给的是 Unix 秒, 其余事件是 RFC3339 字符串。"""

        return _parse_epoch(value)


class GroupAddRobot(_GroupRobotEvent):
    """t = GROUP_ADD_ROBOT, 机器人被拉进群。"""


class GroupDelRobot(_GroupRobotEvent):
    """t = GROUP_DEL_ROBOT, 机器人被移出群。"""


class GroupMsgReceive(_GroupRobotEvent):
    """t = GROUP_MSG_RECEIVE, 群开启了机器人的消息接收。"""


class GroupMsgReject(_GroupRobotEvent):
    """t = GROUP_MSG_REJECT, 群关闭了机器人的消息接收。"""


class GroupMemberAdd(EventModel):
    """t = GROUP_MEMBER_ADD, 群成员加入。"""

    timestamp: datetime = Field(alias="timestamp", description="入群时间, Unix 秒")
    group_openid: str = Field(alias="group_openid")
    member_openid: str = Field(alias="member_openid")

    @field_validator("timestamp", mode="before")
    @classmethod
    def _parse_timestamp(cls, value: object) -> object:
        return _parse_epoch(value)


class GroupMemberRemove(EventModel):
    """t = GROUP_MEMBER_REMOVE, 群成员退出。"""

    timestamp: datetime = Field(alias="timestamp", description="退出时间, Unix 秒")
    group_openid: str = Field(alias="group_openid")
    member_openid: str = Field(alias="member_openid")
    # 官方说这个字段可能为空
    user_openid: str | None = Field(alias="user_openid", default=None)

    @field_validator("timestamp", mode="before")
    @classmethod
    def _parse_timestamp(cls, value: object) -> object:
        return _parse_epoch(value)


class _C2CEvent(EventModel):
    """单聊侧的消息开关事件共用体。"""

    timestamp: datetime = Field(alias="timestamp", description="事件时间, Unix 秒")
    openid: str = Field(alias="openid", description="用户 OpenID")

    @field_validator("timestamp", mode="before")
    @classmethod
    def _parse_timestamp(cls, value: object) -> object:
        return _parse_epoch(value)


class C2CMsgReceive(_C2CEvent):
    """t = C2C_MSG_RECEIVE, 用户开启了机器人的单聊消息接收。"""


class C2CMsgReject(_C2CEvent):
    """t = C2C_MSG_REJECT, 用户关闭了机器人的单聊消息接收。"""


class FriendAuthor(QQModel):
    """好友事件里的用户信息。"""

    union_openid: str = Field(alias="union_openid", description="跨应用统一 OpenID")


class FriendAdd(EventModel):
    """t = FRIEND_ADD, 用户添加机器人为好友。"""

    timestamp: datetime = Field(alias="timestamp", description="添加时间, Unix 秒")
    openid: str = Field(alias="openid", description="用户 OpenID")
    scene: int | None = Field(alias="scene", default=None, description="加好友场景值")
    scene_param: str | None = Field(alias="scene_param", default=None, description="自定义回调数据")
    author: FriendAuthor | None = Field(alias="author", default=None)
    short_code: str | None = Field(
        alias="short_code", default=None, description="分享链接短链 code"
    )

    @field_validator("timestamp", mode="before")
    @classmethod
    def _parse_timestamp(cls, value: object) -> object:
        return _parse_epoch(value)


class FriendDel(EventModel):
    """t = FRIEND_DEL, 用户删除机器人好友。"""

    timestamp: datetime = Field(alias="timestamp", description="删除时间, Unix 秒")
    openid: str = Field(alias="openid", description="用户 OpenID")
    author: FriendAuthor | None = Field(alias="author", default=None)

    @field_validator("timestamp", mode="before")
    @classmethod
    def _parse_timestamp(cls, value: object) -> object:
        return _parse_epoch(value)


class GroupJoinRequest(JoinRequest, EventModel):
    """t = GROUP_JOIN_REQUEST, 用户申请加群。

    只有机器人是群管理员时才会下发;
    `join_request_id` 审批时要原样回传, `apply_source=invited` 时 `invited_by` 才有值。
    """

    group_openid: str = Field(alias="group_openid")
    auto_approved: AutoApproved | None = Field(alias="auto_approved", default=None)


class C2CMessageCreate(EventModel):
    """t = C2C_MESSAGE_CREATE, 用户单聊机器人。"""

    id: str = Field(alias="id")
    author: C2CUser = Field(alias="author")
    content: str = Field(alias="content", default="")
    timestamp: datetime = Field(alias="timestamp")
    # 0 文本 / 3 卡片 / 101 并行 / 102 聊天记录 / 103 引用
    message_type: int | None = Field(alias="message_type", default=None)
    message_scene: MessageScene | None = Field(alias="message_scene", default=None)
    attachments: list[Attachment] = Field(alias="attachments", default_factory=list)
    ark_data: ARKData | None = Field(alias="ark_data", default=None)
    msg_elements: list[MessageElement] = Field(alias="msg_elements", default_factory=list)

    async def reply(
        self,
        content: str | None = None,
        *,
        markdown: MessageMarkdown | None = None,
        media: MediaInfo | None = None,
        keyboard: Keyboard | None = None,
        msg_seq: int | None = None,
    ) -> UserMessageReceipt:
        """回复这条单聊消息。

        自动带本事件的 id 作为 msg_id, 被动回复窗口 60 分钟、每条消息最多回 4 次。
        msg_seq 不传时从 1 起按事件自增; 有 markdown 时忽略 content。
        """

        api = self.api
        if api is None:
            raise ValueError(
                "reply() needs an event dispatched by Bot; use bot.api.user_message.send_message()"
            )
        if markdown is not None:
            content = None
        if msg_seq is None:
            self._reply_seq += 1
            msg_seq = self._reply_seq
        if msg_seq > C2C_REPLY_LIMIT:
            raise ValueError("passive reply limit reached")
        return await api.user_message.send_message(
            self.author.user_openid,
            content=content,
            markdown=markdown,
            media=media,
            keyboard=keyboard,
            reply_to=self.id,
            msg_seq=msg_seq,
        )


class ChannelMessageCreate(Message, EventModel):
    """t = AT_MESSAGE_CREATE, 频道里 @ 机器人。

    官方 api-v2 没有这一事件的事件体表格(页面回落到「启动接入」),
    这里按「消息对象(Message)」表格建模, 字段与频道发送接口的响应同源。
    """

    async def reply(
        self,
        content: str | None = None,
        *,
        markdown: MessageMarkdown | None = None,
        image: str | None = None,
    ) -> Message:
        """回复这条频道消息。

        自动带本事件的 id 作为 msg_id, 频道被动回复窗口是 5 分钟; 有 markdown 时忽略 content。
        """

        api = self.api
        if api is None:
            raise ValueError(
                "reply() needs an event dispatched by Bot; use bot.api.channel.send_message()"
            )
        return await api.channel.send_message(
            self.channel_id,
            content=content,
            markdown=markdown,
            image=image,
            reply_to=self.id,
            event_id=self.id,
        )


class GuildEvent(EventModel):
    """GUILD_CREATE / GUILD_UPDATE / GUILD_DELETE 共用的事件体。

    三张文档页的字段表一致: 频道对象加 `op_user_id`。
    删除事件可能只带 `id` 与 `op_user_id`, 因此除 `id` 外都给了默认值。
    """

    id: str = Field(alias="id", description="频道 ID")
    name: str = Field(alias="name", default="")
    icon: str = Field(alias="icon", default="")
    owner_id: str = Field(alias="owner_id", default="")
    member_count: int = Field(alias="member_count", default=0)
    max_members: int = Field(alias="max_members", default=0)
    description: str = Field(alias="description", default="")
    joined_at: datetime | None = Field(alias="joined_at", default=None)
    op_user_id: str = Field(alias="op_user_id", default="", description="操作人 ID")


class GuildCreate(GuildEvent):
    """t = GUILD_CREATE, 机器人加入频道。"""


class GuildUpdate(GuildEvent):
    """t = GUILD_UPDATE, 频道信息变更。"""


class GuildDelete(GuildEvent):
    """t = GUILD_DELETE, 机器人被移出频道。"""


class ChannelEvent(EventModel):
    """CHANNEL_CREATE / CHANNEL_UPDATE / CHANNEL_DELETE 共用的事件体。

    文档字段表只列了 id/guild_id/name/type/sub_type/owner_id/op_user_id,
    示例里还带着 `position`, 这里按可选字段收下; 删除事件可能只带 id 与 op_user_id。
    """

    id: str = Field(alias="id", description="子频道 ID")
    guild_id: str = Field(alias="guild_id", default="")
    name: str = Field(alias="name", default="")
    type: ChannelType | None = Field(alias="type", default=None)
    sub_type: ChannelSubType | None = Field(alias="sub_type", default=None)
    owner_id: str = Field(alias="owner_id", default="")
    op_user_id: str = Field(alias="op_user_id", default="", description="操作人 ID")
    position: int | None = Field(alias="position", default=None)


class ChannelCreate(ChannelEvent):
    """t = CHANNEL_CREATE, 子频道创建。"""


class ChannelUpdate(ChannelEvent):
    """t = CHANNEL_UPDATE, 子频道信息变更。"""


class ChannelDelete(ChannelEvent):
    """t = CHANNEL_DELETE, 子频道删除。"""


class GuildMessageCreate(ChannelMessageCreate):
    """t = MESSAGE_CREATE, 频道里的全量消息。

    字段与 `AT_MESSAGE_CREATE` 同源, 沿用频道消息的 `reply()`。
    """


class DirectMessageCreate(ChannelMessageCreate):
    """t = DIRECT_MESSAGE_CREATE, 频道的私信消息。

    字段与 `AT_MESSAGE_CREATE` 同源, 沿用频道消息的 `reply()`。
    """


class MessageAudit(EventModel):
    """MESSAGE_AUDIT_PASS / MESSAGE_AUDIT_REJECT 共用的事件体。"""

    audit_id: str = Field(alias="audit_id", description="审核 ID")
    audit_time: datetime = Field(alias="audit_time", description="审核时间")
    channel_id: str = Field(alias="channel_id")
    create_time: datetime = Field(alias="create_time", description="消息发送时间")
    guild_id: str = Field(alias="guild_id")
    message_id: str = Field(alias="message_id")


class MessageAuditPass(MessageAudit):
    """t = MESSAGE_AUDIT_PASS, 消息审核通过。"""


class MessageAuditReject(MessageAudit):
    """t = MESSAGE_AUDIT_REJECT, 消息审核驳回。"""


class InteractionType(IntEnum):
    """互动类型。"""

    INLINE_KEYBOARD = 11
    CALLBACK_COMMAND = 12
    MESSAGE_FEEDBACK = 13
    CLEAR_SESSION = 14
    IN_OUT_STORY = 15
    SWITCH_MODEL = 16
    USER_AUTHORIZE = 18
    GROUP_AUTHORIZE = 19
    GROUP_AUTHORIZE_STATUS = 20
    SETTING_ENTRY = 2001


class InteractionCode(IntEnum):
    """回应互动时告诉客户端的结果。"""

    OK = 0
    FAILED = 1
    TOO_FREQUENT = 2
    DUPLICATE = 3
    NO_PERMISSION = 4
    ADMIN_ONLY = 5


class AuthorizeData(EventModel):
    """授权事件的数据。"""

    opt_scene: str | None = Field(alias="opt_scene", default=None)
    scope: str | None = Field(alias="scope", default=None)


class InteractionMessageScene(EventModel):
    """消息反馈场景里的消息信息。`ext` 与群/单聊消息一样是 `k=v` 列表。"""

    ext: dict[str, str] = Field(alias="ext", default_factory=dict)

    @field_validator("ext", mode="before")
    @classmethod
    def _split_ext(cls, value: object) -> object:
        return split_ext(value)


class InteractionResolved(EventModel):
    """互动事件里解析出来的具体数据。"""

    button_data: str | None = Field(alias="button_data", default=None)
    button_id: str | None = Field(alias="button_id", default=None)
    user_id: str | None = Field(alias="user_id", default=None)
    feature_id: str | None = Field(alias="feature_id", default=None)
    message_id: str | None = Field(alias="message_id", default=None)
    feedback_opt: str | None = Field(alias="feedback_opt", default=None)
    checked: int | None = Field(alias="checked", default=None)
    action: str | None = Field(alias="action", default=None)
    message_scene: InteractionMessageScene | None = Field(alias="message_scene", default=None)
    authorize_data: AuthorizeData | None = Field(alias="authorize_data", default=None)


class InteractionData(EventModel):
    """互动事件的数据体。

    官方示例 3(授权事件)只带 `resolved`, 没有外层 `type`, 所以这里可缺省。
    """

    type: InteractionType | None = Field(alias="type", default=None)
    resolved: InteractionResolved | None = Field(alias="resolved", default=None)


class InteractionCreate(EventModel):
    """t = INTERACTION_CREATE, 用户点击消息按钮、快捷菜单等。

    `type=11`(消息按钮)与 `type=12`(快捷菜单)必须调用 `respond()` 回应,
    否则客户端一直 loading 到超时;其余类型可以不回应。
    """

    id: str = Field(alias="id")
    type: InteractionType = Field(alias="type")
    scene: str | None = Field(alias="scene", default=None)
    chat_type: int | None = Field(alias="chat_type", default=None)
    timestamp: datetime = Field(alias="timestamp")
    guild_id: str | None = Field(alias="guild_id", default=None)
    channel_id: str | None = Field(alias="channel_id", default=None)
    user_openid: str | None = Field(alias="user_openid", default=None)
    group_openid: str | None = Field(alias="group_openid", default=None)
    group_member_openid: str | None = Field(alias="group_member_openid", default=None)
    data: InteractionData | None = Field(alias="data", default=None)
    version: int = Field(alias="version", default=1)
    application_id: str | None = Field(alias="application_id", default=None)

    @property
    def needs_response(self) -> bool:
        """是否属于必须回应的类型(消息按钮、快捷菜单)。"""

        return self.type in (InteractionType.INLINE_KEYBOARD, InteractionType.CALLBACK_COMMAND)

    async def respond(self, code: InteractionCode = InteractionCode.OK) -> None:
        """回应这次互动, 让客户端停止 loading。

        同一个 interaction_id 只能回应一次;只有消息按钮与快捷菜单需要回应。
        """

        api = self.api
        if api is None:
            raise ValueError(
                "respond() needs an event dispatched by Bot; use bot.api.interaction.respond()"
            )
        await api.interaction.respond(self.id, code=int(code))


class UnknownEvent(EventModel):
    """未建模的事件, 保留 t 与原始 d。"""

    t: str = Field(alias="t")
    data: Any = Field(alias="data", default=None)


# t 到事件模型的映射。没登记的事件一律降级成 UnknownEvent, 不抛错
EVENT_MODELS: Final[dict[str, type[EventModel]]] = {
    "READY": ReadyEvent,
    "RESUMED": ResumedEvent,
    "GUILD_CREATE": GuildCreate,
    "GUILD_UPDATE": GuildUpdate,
    "GUILD_DELETE": GuildDelete,
    "CHANNEL_CREATE": ChannelCreate,
    "CHANNEL_UPDATE": ChannelUpdate,
    "CHANNEL_DELETE": ChannelDelete,
    "GROUP_ADD_ROBOT": GroupAddRobot,
    "GROUP_DEL_ROBOT": GroupDelRobot,
    "GROUP_MSG_RECEIVE": GroupMsgReceive,
    "GROUP_MSG_REJECT": GroupMsgReject,
    "GROUP_MEMBER_ADD": GroupMemberAdd,
    "GROUP_MEMBER_REMOVE": GroupMemberRemove,
    "GROUP_JOIN_REQUEST": GroupJoinRequest,
    "FRIEND_ADD": FriendAdd,
    "FRIEND_DEL": FriendDel,
    "C2C_MSG_RECEIVE": C2CMsgReceive,
    "C2C_MSG_REJECT": C2CMsgReject,
    "GROUP_AT_MESSAGE_CREATE": GroupAtMessageCreate,
    "GROUP_MESSAGE_CREATE": GroupMessageCreate,
    "C2C_MESSAGE_CREATE": C2CMessageCreate,
    "AT_MESSAGE_CREATE": ChannelMessageCreate,
    "MESSAGE_CREATE": GuildMessageCreate,
    "DIRECT_MESSAGE_CREATE": DirectMessageCreate,
    "MESSAGE_AUDIT_PASS": MessageAuditPass,
    "MESSAGE_AUDIT_REJECT": MessageAuditReject,
    "INTERACTION_CREATE": InteractionCreate,
}


def parse_event(t: str, data: object) -> EventModel:
    """按 `t` 把 `d` 解析成具体事件模型;认不出的走 UnknownEvent。"""

    model = EVENT_MODELS.get(t)
    if model is None:
        return UnknownEvent(t=t, data=data)
    # 官方在 Resume 结束时会下发 {"t": "RESUMED", "d": ""}, 空串不能直接喂给模型
    return model.model_validate(data if isinstance(data, dict) else {})
