# Copyright (c) 2026-present Half_nothing.

"""群聊消息里出现的复合结构：消息场景、附件、消息元素。"""

from __future__ import annotations

from typing import Any

from pydantic import Field, field_validator

from .base import QQModel


class MessageScene(QQModel):
    """`message_scene` 里的场景信息。"""

    source: str = Field(alias="source", default="")
    ext: dict[str, str] = Field(alias="ext", default_factory=dict)

    @field_validator("ext", mode="before")
    @classmethod
    def _split_ext(cls, value: object) -> object:
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


class MessageElement(QQModel):
    """`msg_elements` 的单个元素。"""

    message_type: int = Field(alias="message_type", default=0)
    content: dict[str, Any] = Field(alias="content", default_factory=dict)
