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

__all__ = [
    "ChannelMessageDraft",
    "GroupMessageDraft",
    "GroupMessageType",
    "InputNotify",
    "MessageMarkdown",
    "MessageReference",
    "UserMessageDraft",
    "UserMessageType",
]


class MessageReference(QQModel):
    """引用消息, 频道与群聊共用 {"message_id": ...} 这一形状。"""

    message_id: str = Field(alias="message_id")


class MessageMarkdown(QQModel):
    """Markdown 消息, 频道与群聊共用同一形状。"""

    content: str | None = Field(alias="content", default=None)
    force_verify_image_resource: bool | None = Field(
        alias="force_verify_image_resource", default=None
    )


def _markdown_text(markdown: MessageMarkdown | None) -> str | None:
    """取 Markdown 正文, 没有正文时返回 None。"""

    if markdown is None or not markdown.content:
        return None
    return markdown.content


def _join_text(*parts: str | None) -> str:
    """把若干片段拼成一段可读文本, 空片段跳过。"""

    return "\n".join(part for part in parts if part)


def _lift_keyboard_to_markdown(data: Any) -> Any:
    """把带 keyboard 的纯文本消息升成 Markdown 消息。

    实测: msg_type 不是 2 时平台照样返回成功, 但按钮不会显示,
    所以 SDK 在本地就把文本搬进 markdown, 调用方不用记这条规则。
    """

    if not isinstance(data, dict) or data.get("keyboard") is None:
        return data

    msg_type = data.get("msg_type", 0)
    if msg_type is not None and int(msg_type) not in (0, 2):
        raise ValueError("a keyboard message must be a markdown message (msg_type=2)")

    markdown = data.get("markdown")
    if markdown is None:
        content = data.get("content")
        if not content:
            raise ValueError("a keyboard message needs content or markdown")
        markdown = {"content": content}
    return {**data, "content": None, "markdown": markdown, "msg_type": 2}


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

    def to_text(self) -> str:
        """转成可读文本, 供记录或日志使用。

        正文与 Markdown 取原文, 图片带上地址, embed / ark 这类没有文字的部分
        用 `[embed]` / `[ark]` 占位, 多个片段按行拼接。
        """

        image = f"[image] {self.image}" if self.image is not None else None
        parts = [
            self.content,
            _markdown_text(self.markdown),
            image,
            "[embed]" if self.embed is not None else None,
            "[ark]" if self.ark is not None else None,
        ]
        return _join_text(*parts)

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

    def to_text(self) -> str:
        """转成可读文本: 正文或 Markdown 原文, 富媒体与键盘用占位符表示。"""

        parts = [
            self.content,
            _markdown_text(self.markdown),
            "[media]" if self.media is not None else None,
            "[keyboard]" if self.keyboard is not None else None,
        ]
        return _join_text(*parts)

    @model_validator(mode="before")
    @classmethod
    def _infer_type(cls, data: Any) -> Any:
        data = _lift_keyboard_to_markdown(data)
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

    与群聊的差别只有 msg_type 多了 6(输入中状态)以及 is_wakeup,
    所以不复用 `GroupMessageDraft`: 复用会把两套枚举塞进同一个校验器,
    校验器里得按长度判断是哪种消息, 反而更难读。

    msg_type 留空时按内容推断: media → 7, markdown → 2, input_notify → 6, 否则 0。
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

    def to_text(self) -> str:
        """转成可读文本: 正文或 Markdown 原文, 富媒体、键盘与输入中状态用占位符表示。"""

        parts = [
            self.content,
            _markdown_text(self.markdown),
            "[media]" if self.media is not None else None,
            "[keyboard]" if self.keyboard is not None else None,
            "[input notify]" if self.input_notify is not None else None,
        ]
        return _join_text(*parts)

    @model_validator(mode="before")
    @classmethod
    def _infer_type(cls, data: Any) -> Any:
        data = _lift_keyboard_to_markdown(data)
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
