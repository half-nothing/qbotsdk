# Copyright (c) 2026-present Half_nothing.

"""网关下发的 t 事件模型。"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from enum import IntEnum
from typing import TYPE_CHECKING, Any, Final, Protocol

from async_event_bus import AbstractEvent
from pydantic import ConfigDict, Field, PrivateAttr, field_validator

from .base import QQModel
from .message import Message
from .scene import ARKData, Attachment, MessageElement, MessageScene, split_ext
from .user import C2CUser, GroupUser, GuildUser, MentionUser

if TYPE_CHECKING:
    from .draft import MessageMarkdown
    from .keyboard import Keyboard
    from .media import MediaInfo
    from .message import GroupMessageReceipt, UserMessageReceipt

# 官方限制: 群聊每条消息最多被动回复 5 次, 单聊 4 次, 超出会返回 40034128
GROUP_REPLY_LIMIT = 5
C2C_REPLY_LIMIT = 4

# 群聊 content 里的 @ 标记: `<@member_openid>` 或 `<@all>`, 频道消息里还会出现 `<@!openid>`
_MENTION_TAG = re.compile(r"<@!?([^>]+)>")
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
    """t = READY，鉴权成功后下发。"""

    version: int = Field(alias="version", default=0)
    session_id: str = Field(alias="session_id", default="")
    user: GuildUser = Field(alias="user")
    shard: list[int] = Field(alias="shard", default_factory=list)


class ResumedEvent(EventModel):
    """t = RESUMED，Resume 补发完成后下发。官方 `d` 是空对象。"""


@dataclass(frozen=True, slots=True)
class RenderedMentions:
    """`render_mentions_indexed` 的结果。

    `text` 里的 `@0`、`@1` 按出现顺序对应 `mentions` 的下标, 用 `mentions[0]` 取回成员对象。
    """

    text: str
    mentions: tuple[MentionUser, ...]


class _GroupMessageBase(EventModel):
    """群聊消息事件的公共字段：@ 机器人与全量模式下的载荷一致。"""

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
        <@all> 换成 @全体成员，找不到对应 mention 的标记原样换成 @openid
        strip_me=True 时去掉@机器人自己的那一段
        """

        return self._render(code=False, strip_me=strip_me).text

    def render_mentions_indexed(self, *, strip_me: bool = False) -> RenderedMentions:
        """把 content 里的 @ 标记换成按出现顺序编号的 @0、@1, 给代码定位成员用。

        昵称里带空格也不会影响按空白分词, 用 rendered.mentions[int] 取回成员对象
        <@all> 换成 @all，找不到对应 mention 的标记仍换成 @openid, 且不占编号。
        strip_me=True 时去掉 @ 机器人自己的那一段, 编号随之从 0 重新连续。
        """

        return self._render(code=True, strip_me=strip_me)

    def _render(self, *, code: bool, strip_me: bool) -> RenderedMentions:
        lookup = self.mentions_by_openid
        used: list[MentionUser] = []

        def replace(match: re.Match[str]) -> str:
            key = match.group(1)
            if key == "all":
                return "@all" if code else "@全体成员"
            user = lookup.get(key)
            if user is None:
                return f"@{key}"
            if user.is_you and strip_me:
                return ""
            if not code:
                return f"@{user.username or key}"
            if user not in used:
                used.append(user)
            return f"@{used.index(user)}"

        text = _MENTION_TAG.sub(replace, self.content)
        # 剥掉 @ 机器人 之后可能留下连续空格, 归成一个
        return RenderedMentions(text=_TIDY_SPACES.sub(" ", text).strip(), mentions=tuple(used))


class GroupAtMessageCreate(_GroupMessageBase):
    """t = GROUP_AT_MESSAGE_CREATE，群聊里 @ 机器人。

    没有给机器人打开接收全部消息时, 只有@到机器人的消息才会走这个事件。
    开启全量之后不再下发本事件, 全部改走 GroupMessageCreate。
    content 里 @机器人 的前缀已被平台去掉, 消息里 @ 其他人时, 官方没有承诺 content 里保留对应标记。
    """

    @property
    def mentioned_me(self) -> bool:
        """未开启全量时只有 @ 到机器人本人才会下发本事件, 恒为 True。"""

        return True


class GroupMessageCreate(_GroupMessageBase):
    """t = GROUP_MESSAGE_CREATE，群聊全量消息。

    给机器人打开接收全部消息后, 群里每条消息都会下发, 不限于@机器人, 字段与 GROUP_AT_MESSAGE_CREATE 一致。
    开启全量后包括 @ 机器人在内的消息都走本事件, 不会再下发 GROUP_AT_MESSAGE_CREATE, 因此判断机器人自己是否被 @ 要看 mentions 条目的 `is_you`。
    该事件里 content 会把 @ 成员写成 <@member_openid>、@ 全体写成 <@all>, 被@的成员同时出现在 mentions 里。
    """


class C2CMessageCreate(EventModel):
    """t = C2C_MESSAGE_CREATE，用户单聊机器人。"""

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
    """t = AT_MESSAGE_CREATE，频道里 @ 机器人。

    官方 api-v2 没有这一事件的事件体表格（页面回落到「启动接入」），
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

    官方示例 3（授权事件）只带 `resolved`，没有外层 `type`，所以这里可缺省。
    """

    type: InteractionType | None = Field(alias="type", default=None)
    resolved: InteractionResolved | None = Field(alias="resolved", default=None)


class InteractionCreate(EventModel):
    """t = INTERACTION_CREATE，用户点击消息按钮、快捷菜单等。

    `type=11`（消息按钮）与 `type=12`（快捷菜单）必须调用 `respond()` 回应，
    否则客户端一直 loading 到超时；其余类型可以不回应。
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
        """是否属于必须回应的类型（消息按钮、快捷菜单）。"""

        return self.type in (InteractionType.INLINE_KEYBOARD, InteractionType.CALLBACK_COMMAND)

    async def respond(self, code: InteractionCode = InteractionCode.OK) -> None:
        """回应这次互动，让客户端停止 loading。

        同一个 interaction_id 只能回应一次；只有消息按钮与快捷菜单需要回应。
        """

        api = self.api
        if api is None:
            raise ValueError(
                "respond() needs an event dispatched by Bot; use bot.api.interaction.respond()"
            )
        await api.interaction.respond(self.id, code=int(code))


class UnknownEvent(EventModel):
    """未建模的事件，保留 t 与原始 d。"""

    t: str = Field(alias="t")
    data: Any = Field(alias="data", default=None)


# t 到事件模型的映射。没登记的事件一律降级成 UnknownEvent，不抛错
EVENT_MODELS: Final[dict[str, type[EventModel]]] = {
    "READY": ReadyEvent,
    "RESUMED": ResumedEvent,
    "GROUP_AT_MESSAGE_CREATE": GroupAtMessageCreate,
    "GROUP_MESSAGE_CREATE": GroupMessageCreate,
    "C2C_MESSAGE_CREATE": C2CMessageCreate,
    "AT_MESSAGE_CREATE": ChannelMessageCreate,
    "INTERACTION_CREATE": InteractionCreate,
}


def parse_event(t: str, data: object) -> EventModel:
    """按 `t` 把 `d` 解析成具体事件模型；认不出的走 UnknownEvent。"""

    model = EVENT_MODELS.get(t)
    if model is None:
        return UnknownEvent(t=t, data=data)
    return model.model_validate(data)
