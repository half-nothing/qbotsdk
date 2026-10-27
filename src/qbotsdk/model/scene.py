# Copyright (c) 2026-present Half_nothing.

"""消息事件里的复合结构：消息场景、附件、卡片数据、消息元素。

字段来源：

- 群@机器人消息: https://bot.qq.com/wiki/develop/api-v2/autogen/event/group_at_message_create.html
- 单聊消息事件: https://bot.qq.com/wiki/develop/api-v2/autogen/event/c2c_message_create.html
"""

from __future__ import annotations

from typing import Any

from pydantic import Field, field_validator

from .base import QQModel


def split_ext(value: object) -> object:
    """把官方 ext 的 ["k=v", ...] 切成字典；不是列表就原样返回。"""

    if not isinstance(value, list):
        return value
    pairs: dict[str, str] = {}
    for item in value:
        if not isinstance(item, str):
            continue
        key, sep, val = item.partition("=")
        if sep and key:
            pairs[key] = val
    return pairs


class MessageScene(QQModel):
    """message_scene 里的场景信息。"""

    source: str = Field(alias="source", default="")
    ext: dict[str, str] = Field(alias="ext", default_factory=dict)

    @field_validator("ext", mode="before")
    @classmethod
    def _split_ext(cls, value: object) -> object:
        return split_ext(value)


class Attachment(QQModel):
    """消息附件。语音消息额外带 `voice_wav_url` 与 `asr_refer_text`。"""

    url: str = Field(alias="url")
    filename: str = Field(alias="filename")
    size: int = Field(alias="size")
    content_type: str = Field(alias="content_type")
    width: int | None = Field(alias="width", default=None)
    height: int | None = Field(alias="height", default=None)
    voice_wav_url: str | None = Field(alias="voice_wav_url", default=None)
    asr_refer_text: str | None = Field(alias="asr_refer_text", default=None)


class ARKData(QQModel):
    """结构化卡片消息（message_type=3）的数据。"""

    prompt: str = Field(alias="prompt", default="")
    ark_type: str = Field(alias="ark_type", default="")
    ark_name: str = Field(alias="ark_name", default="")
    # 键名不固定，按原样透传
    fields: dict[str, Any] = Field(alias="fields", default_factory=dict)


class ElementAuthor(QQModel):
    """消息元素里的作者。

    官方在元素层不保证 id
    群聊元素给 member_openid
    单聊元素只给 user_openid
    因此这里全部可缺省，用 openid 取场景对应的那个。
    """

    id: str | None = Field(alias="id", default=None)
    username: str | None = Field(alias="username", default=None)
    user_openid: str | None = Field(alias="user_openid", default=None)
    member_openid: str | None = Field(alias="member_openid", default=None)

    @property
    def openid(self) -> str | None:
        return self.user_openid or self.member_openid


class MessageElement(QQModel):
    """msg_elements 的单个元素，官方是递归结构。"""

    msg_idx: str = Field(alias="msg_idx", default="")
    author: ElementAuthor | None = Field(alias="author", default=None)
    message_type: int = Field(alias="message_type", default=0)
    content: str = Field(alias="content", default="")
    attachments: list[Attachment] = Field(alias="attachments", default_factory=list)
    ark_data: ARKData | None = Field(alias="ark_data", default=None)
    msg_elements: list[MessageElement] = Field(alias="msg_elements", default_factory=list)
