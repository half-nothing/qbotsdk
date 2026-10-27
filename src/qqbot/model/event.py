# Copyright (c) 2026-present Half_nothing.

"""网关下发的 `t` 事件模型。"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any, Final, Protocol

from async_event_bus import AbstractEvent
from pydantic import ConfigDict, Field, PrivateAttr

from .base import QQModel
from .scene import ARKData, Attachment, MessageElement, MessageScene
from .user import C2CUser, GroupUser, GuildUser

if TYPE_CHECKING:
    from .draft import MessageMarkdown
    from .keyboard import Keyboard
    from .media import MediaInfo
    from .message import GroupMessageReceipt, UserMessageReceipt

# 官方限制: 群聊每条消息最多被动回复 5 次, 单聊 4 次, 超出会返回 40034128
GROUP_REPLY_LIMIT = 5
C2C_REPLY_LIMIT = 4


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


class ApiProtocol(Protocol):
    """事件需要的接口面, ApiClient 结构上满足它。"""

    @property
    def group(self) -> GroupSender: ...

    @property
    def user_message(self) -> ChatSender: ...


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


class GroupAtMessageCreate(EventModel):
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

    async def reply(
        self,
        content: str,
        *,
        markdown: MessageMarkdown | None = None,
        media: MediaInfo | None = None,
        keyboard: Keyboard | None = None,
        msg_seq: int | None = None,
    ) -> GroupMessageReceipt:
        """回复这条群消息。

        自动带本事件的 id 作为 msg_id
        msg_seq 不传时从 1 起按事件自增, 官方上限是每条消息 5 次
        """

        api = self.api
        if api is None:
            raise ValueError(
                "reply() needs an event dispatched by Bot; use bot.api.group.send_message()"
            )
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
        content: str,
        *,
        markdown: MessageMarkdown | None = None,
        media: MediaInfo | None = None,
        keyboard: Keyboard | None = None,
        msg_seq: int | None = None,
    ) -> UserMessageReceipt:
        """回复这条单聊消息。

        自动带本事件的 id 作为 msg_id, 被动回复窗口 60 分钟、每条消息最多回 4 次。
        msg_seq 不传时从 1 起按事件自增。
        """

        api = self.api
        if api is None:
            raise ValueError(
                "reply() needs an event dispatched by Bot; use bot.api.user_message.send_message()"
            )
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


class UnknownEvent(EventModel):
    """未建模的事件，保留 t 与原始 d。"""

    t: str = Field(alias="t")
    data: Any = Field(alias="data", default=None)


# t 到事件模型的映射。没登记的事件一律降级成 UnknownEvent，不抛错
EVENT_MODELS: Final[dict[str, type[EventModel]]] = {
    "READY": ReadyEvent,
    "RESUMED": ResumedEvent,
    "GROUP_AT_MESSAGE_CREATE": GroupAtMessageCreate,
    "C2C_MESSAGE_CREATE": C2CMessageCreate,
}


def parse_event(t: str, data: object) -> EventModel:
    """按 `t` 把 `d` 解析成具体事件模型；认不出的走 UnknownEvent。"""

    model = EVENT_MODELS.get(t)
    if model is None:
        return UnknownEvent(t=t, data=data)
    return model.model_validate(data)
