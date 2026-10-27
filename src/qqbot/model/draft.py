# Copyright (c) 2026-present Half_nothing.

"""发送消息的请求体模型。

字段来自官方请求体表格:

- 频道: https://bot.q.qq.com/wiki/develop/api-v2/server-inter/channel/message/send.html
- 群聊: https://bot.q.qq.com/wiki/develop/api-v2/autogen/api/v2_groups_group_openid_messages.post.html
- Markdown: https://bot.q.qq.com/wiki/develop/api-v2/server-inter/message/type/markdown.html
"""

from __future__ import annotations

from enum import IntEnum
from typing import Any

from pydantic import Field, model_validator

from .base import QQModel
from .keyboard import Keyboard
from .media import MediaInfo


class MessageReference(QQModel):
    """引用消息, 频道与群聊共用 {"message_id": ...} 这一形状。"""

    message_id: str = Field(alias="message_id")


class MessageMarkdown(QQModel):
    """Markdown 消息, 频道与群聊共用同一形状。"""

    content: str | None = Field(alias="content", default=None)
    force_verify_image_resource: bool | None = Field(
        alias="force_verify_image_resource", default=None
    )


class GroupMessageType(IntEnum):
    """群聊消息类型, 对应 msg_type。"""

    TEXT = 0  # 文本
    MARKDOWN = 2  # Markdown
    MEDIA = 7  # 富媒体


class UserMessageType(IntEnum):
    """单聊消息类型, 对应 msg_type。比群聊多一个输入中状态。"""

    TEXT = 0  # 文本
    MARKDOWN = 2  # Markdown
    INPUT_NOTIFY = 6  # 输入中状态
    MEDIA = 7  # 富媒体


class InputNotify(QQModel):
    """单聊的「输入中」状态, 最长 60 秒。"""

    input_type: int = Field(alias="input_type", default=1)
    input_second: int = Field(alias="input_second", default=60)

    @model_validator(mode="after")
    def _check_second(self) -> InputNotify:
        if not 1 <= self.input_second <= 60:
            raise ValueError("input_second must be between 1 and 60")
        return self


class ChannelMessageDraft(QQModel):
    """子频道消息请求体。"""

    content: str | None = Field(alias="content", default=None)
    embed: dict[str, Any] | None = Field(alias="embed", default=None)
    ark: dict[str, Any] | None = Field(alias="ark", default=None)
    image: str | None = Field(alias="image", default=None)
    msg_id: str | None = Field(alias="msg_id", default=None)
    event_id: str | None = Field(alias="event_id", default=None)
    markdown: MessageMarkdown | None = Field(alias="markdown", default=None)
    message_reference: MessageReference | None = Field(alias="message_reference", default=None)

    @model_validator(mode="after")
    def _check_content(self) -> ChannelMessageDraft:
        """content / embed / ark / image / markdown 至少要有一样, 否则平台无法下发"""
        has_content = any(
            (
                self.content,
                self.embed,
                self.ark,
                self.image,
                self.markdown,
            )
        )
        if not has_content:
            raise ValueError(
                "a channel message needs at least one of content/embed/ark/image/markdown"
            )
        return self


class GroupMessageDraft(QQModel):
    """群聊消息请求体。

    msg_type 留空时按内容推断, 有media用 7, 有 markdown 用 2, 否则 0。
    推断在本地完成, 调用方不必手填, 平台侧类型与内容不匹配会返回 22006。
    """

    msg_type: GroupMessageType | None = Field(alias="msg_type", default=None)
    content: str | None = Field(alias="content", default=None)
    markdown: MessageMarkdown | None = Field(alias="markdown", default=None)
    keyboard: Keyboard | None = Field(alias="keyboard", default=None)
    media: MediaInfo | None = Field(alias="media", default=None)
    message_reference: MessageReference | None = Field(alias="message_reference", default=None)
    msg_id: str | None = Field(alias="msg_id", default=None)
    event_id: str | None = Field(alias="event_id", default=None)
    msg_seq: int | None = Field(alias="msg_seq", default=None)

    @model_validator(mode="before")
    @classmethod
    def _infer_type(cls, data: Any) -> Any:
        if not isinstance(data, dict) or data.get("msg_type") is not None:
            return data
        if data.get("media") is not None:
            inferred = GroupMessageType.MEDIA
        elif data.get("markdown") is not None:
            inferred = GroupMessageType.MARKDOWN
        else:
            inferred = GroupMessageType.TEXT
        return {**data, "msg_type": inferred}

    @model_validator(mode="after")
    def _check_type(self) -> GroupMessageDraft:
        if self.msg_type is GroupMessageType.TEXT:
            if not self.content:
                raise ValueError("a text message needs content")
            if self.markdown is not None or self.media is not None:
                raise ValueError("a text message must not carry markdown or media")
        elif self.msg_type is GroupMessageType.MARKDOWN:
            if self.markdown is None:
                raise ValueError("a markdown message needs markdown")
            if self.content is not None or self.media is not None:
                raise ValueError("a markdown message must not carry content or media")
        elif self.media is None:
            raise ValueError("a media message needs media.file_info")
        return self


class UserMessageDraft(QQModel):
    """单聊消息请求体。

    与群聊的差别只有 msg_type 多了 6（输入中状态）以及 is_wakeup，
    所以不复用 `GroupMessageDraft`：复用会把两套枚举塞进同一个校验器，
    校验器里得按长度判断是哪种消息，反而更难读。

    msg_type 留空时按内容推断：media → 7，markdown → 2，input_notify → 6，否则 0。
    """

    msg_type: UserMessageType | None = Field(alias="msg_type", default=None)
    content: str | None = Field(alias="content", default=None)
    markdown: MessageMarkdown | None = Field(alias="markdown", default=None)
    keyboard: Keyboard | None = Field(alias="keyboard", default=None)
    media: MediaInfo | None = Field(alias="media", default=None)
    message_reference: MessageReference | None = Field(alias="message_reference", default=None)
    input_notify: InputNotify | None = Field(alias="input_notify", default=None)
    msg_id: str | None = Field(alias="msg_id", default=None)
    event_id: str | None = Field(alias="event_id", default=None)
    msg_seq: int | None = Field(alias="msg_seq", default=None)
    is_wakeup: bool | None = Field(alias="is_wakeup", default=None)

    @model_validator(mode="before")
    @classmethod
    def _infer_type(cls, data: Any) -> Any:
        if not isinstance(data, dict) or data.get("msg_type") is not None:
            return data
        if data.get("media") is not None:
            inferred = UserMessageType.MEDIA
        elif data.get("markdown") is not None:
            inferred = UserMessageType.MARKDOWN
        elif data.get("input_notify") is not None:
            inferred = UserMessageType.INPUT_NOTIFY
        else:
            inferred = UserMessageType.TEXT
        return {**data, "msg_type": inferred}

    @model_validator(mode="after")
    def _check_type(self) -> UserMessageDraft:
        if self.is_wakeup and (self.msg_id is not None or self.event_id is not None):
            # 召回消息不是回复, 与 msg_id / event_id 互斥
            raise ValueError("is_wakeup cannot be combined with msg_id or event_id")

        if self.msg_type is UserMessageType.TEXT:
            if not self.content:
                raise ValueError("a text message needs content")
            if self.markdown is not None or self.media is not None:
                raise ValueError("a text message must not carry markdown or media")
            if self.input_notify is not None:
                raise ValueError("a text message must not carry input_notify")
        elif self.msg_type is UserMessageType.MARKDOWN:
            if self.markdown is None:
                raise ValueError("a markdown message needs markdown")
            if self.content is not None or self.media is not None:
                raise ValueError("a markdown message must not carry content or media")
        elif self.msg_type is UserMessageType.INPUT_NOTIFY:
            if self.input_notify is None:
                raise ValueError("an input_notify message needs input_notify")
            if self.content is not None or self.markdown is not None or self.media is not None:
                raise ValueError("an input_notify message must not carry content")
        elif self.media is None:
            raise ValueError("a media message needs media.file_info")
        return self
