# Copyright (c) 2026-present Half_nothing.

"""子频道域接口。"""

from __future__ import annotations

from pathlib import Path

from aiohttp import FormData

from qbotsdk.model.channel import Channel
from qbotsdk.model.draft import ChannelMessageDraft, MessageMarkdown, MessageReference
from qbotsdk.model.message import Message
from qbotsdk.module.http_client import HTTPClient

from ._parse import expect_object

# 官方支持 multipart 直传时就这几种图片类型, 其余按二进制流发
_CONTENT_TYPES: dict[str, str] = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
}


def _content_type(file_name: str) -> str:
    return _CONTENT_TYPES.get(Path(file_name).suffix.lower(), "application/octet-stream")


class ChannelResource:
    def __init__(self, http: HTTPClient) -> None:
        self._http = http

    async def get(self, channel_id: str) -> Channel:
        """子频道详情。"""

        path = f"/channels/{channel_id}"
        return Channel.model_validate(expect_object(await self._http.get(path), path))

    async def send_message(
        self,
        channel_id: str,
        *,
        content: str | None = None,
        markdown: MessageMarkdown | None = None,
        image: str | None = None,
        file_image: bytes | None = None,
        file_name: str = "image.png",
        reply_to: str | None = None,
        event_id: str | None = None,
    ) -> Message:
        """发子频道消息。

        每个子频道主动与被动合计每秒最多5条
        主动消息每个子频道每天 20 条、每天最多 2 个子频道
        超限返回 `40034100` 等错误码

        Args:
            channel_id: 频道标识
            content: 纯文本内容
            markdown: markdown格式的内容
            image: 传URL由平台转存, 与file_image参数互斥
            file_image: 传字节走multipart, 与image参数互斥
            file_name: 文件名
            reply_to: 被动回复的msg_id, 有效期5分钟
            event_id: 消息事件ID
        """

        if image is not None and file_image is not None:
            raise ValueError("image and file_image are mutually exclusive")

        path = f"/channels/{channel_id}/messages"
        reference = MessageReference(message_id=reply_to) if reply_to is not None else None

        if file_image is not None:
            # Markdown 消息不带 content, 同传时以 markdown 为准
            text = None if markdown is not None else content
            file_bytes: bytes = file_image

            def build_form() -> FormData:
                form = FormData()
                if text is not None:
                    form.add_field("content", text)
                if image is not None:
                    form.add_field("image", image)
                if event_id is not None:
                    form.add_field("event_id", event_id)
                if markdown is not None:
                    form.add_field("markdown", _as_form_json(markdown))
                if reference is not None:
                    form.add_field("message_reference", _as_form_json(reference))
                form.add_field(
                    "file_image",
                    file_bytes,
                    filename=file_name,
                    content_type=_content_type(file_name),
                )
                return form

            data = await self._http.post_form(path, form=build_form)
        else:
            draft = ChannelMessageDraft(
                content=None if markdown is not None else content,
                markdown=markdown,
                image=image,
                event_id=event_id,
                message_reference=reference,
            )
            data = await self._http.post(
                path,
                json=draft.model_dump(by_alias=True, exclude_none=True, mode="json"),
            )

        return Message.model_validate(expect_object(data, path))

    async def recall_message(
        self,
        channel_id: str,
        message_id: str,
        *,
        hide_tip: bool = False,
    ) -> None:
        """撤回消息, 发送后 2 分钟内有效。hidetip 是 query, 不是包体。"""

        path = f"/channels/{channel_id}/messages/{message_id}"
        await self._http.request(
            "DELETE",
            path,
            params={"hidetip": "true" if hide_tip else "false"},
        )


def _as_form_json(model: MessageMarkdown | MessageReference) -> str:
    """multipart 里的嵌套对象要序列化成字符串字段。"""

    return model.model_dump_json(by_alias=True, exclude_none=True, ensure_ascii=False)
