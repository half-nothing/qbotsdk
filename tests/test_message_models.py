# Copyright (c) 2026-present Half_nothing.

"""消息模型测试。"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from qbotsdk.model import (
    ChannelMessageDraft,
    GroupMessageDraft,
    GroupMessageReceipt,
    GroupMessageType,
    Message,
    MessageMarkdown,
    MessageReference,
    QQModel,
    UploadedFile,
)

DATA = Path(__file__).parent / "data"


def load_object(name: str) -> dict[str, object]:
    payload: object = json.loads((DATA / name).read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def missing_fields(payload: dict[str, object], model: type[QQModel]) -> set[str]:
    """返回示例里出现、模型里没有的字段名。"""
    return {key for key in payload if key not in model.model_fields}


def test_channel_message_snapshot() -> None:
    payload = load_object("channel_message.json")
    message = Message.model_validate(payload)

    assert message.content == "<@!1234>hello world"
    assert message.author.username == "abc"
    assert message.author.bot is True
    assert message.timestamp == datetime.fromisoformat("2021-05-13T14:45:45+08:00")
    assert message.embeds == [{}]
    assert message.type == 0
    assert missing_fields(payload, Message) == set()


def test_group_message_receipt_snapshot() -> None:
    payload = load_object("group_message_receipt.json")
    receipt = GroupMessageReceipt.model_validate(payload)

    assert receipt.id == "xxxxxx"
    assert receipt.timestamp.tzinfo is not None
    assert receipt.ext_info is not None
    assert receipt.ext_info.ref_idx == "REFIDX_xxxxxx"
    assert missing_fields(payload, GroupMessageReceipt) == set()


def test_uploaded_file_snapshot() -> None:
    payload = load_object("group_file.json")
    uploaded = UploadedFile.model_validate(payload)

    assert uploaded.file_info == "xxxxxx"
    assert uploaded.ttl == 3600
    # 这两个字段只在特定上传方式下返回
    assert uploaded.id is None
    assert uploaded.raw_url is None


def test_channel_draft_requires_content() -> None:
    with pytest.raises(ValidationError, match="at least one of"):
        ChannelMessageDraft()


def test_channel_draft_dumps_api_names() -> None:
    draft = ChannelMessageDraft(
        markdown=MessageMarkdown(content="# 标题"),
        msg_id="m1",
        message_reference=MessageReference(message_id="m0"),
    )
    payload = draft.model_dump(by_alias=True, exclude_none=True)

    assert payload == {
        "markdown": {"content": "# 标题"},
        "msg_id": "m1",
        "message_reference": {"message_id": "m0"},
    }


def test_group_draft_infers_type() -> None:
    assert GroupMessageDraft(content="hi").msg_type is GroupMessageType.TEXT
    assert (
        GroupMessageDraft(markdown=MessageMarkdown(content="# hi")).msg_type
        is GroupMessageType.MARKDOWN
    )

    media_draft = GroupMessageDraft.model_validate({"media": {"file_info": "f1"}})
    assert media_draft.msg_type is GroupMessageType.MEDIA
    assert media_draft.model_dump(by_alias=True, exclude_none=True) == {
        "msg_type": 7,
        "media": {"file_info": "f1"},
    }


def test_group_draft_rejects_mismatched_type() -> None:
    with pytest.raises(ValidationError, match="must not carry markdown or media"):
        GroupMessageDraft(
            msg_type=GroupMessageType.TEXT,
            content="hi",
            markdown=MessageMarkdown(content="# hi"),
        )

    # 有 markdown 没写 msg_type 时按 markdown 推断, 再被 content 撞掉
    with pytest.raises(ValidationError, match="must not carry content or media"):
        GroupMessageDraft(content="hi", markdown=MessageMarkdown(content="# hi"))

    with pytest.raises(ValidationError, match="needs media"):
        GroupMessageDraft(msg_type=GroupMessageType.MEDIA)


def test_markdown_drops_deprecated_template_fields() -> None:
    markdown = MessageMarkdown.model_validate(
        {
            "content": "## 每日签到",
            # 这两个模板字段官方已标【已废弃】, 传了也不该进模型
            "template_id": 1,
            "custom_template_id": "tpl",
            "params": [{"key": "title", "values": ["标题"]}],
            "force_verify_image_resource": True,
        }
    )

    assert markdown.content == "## 每日签到"
    assert markdown.force_verify_image_resource is True
    assert markdown.model_dump(by_alias=True, exclude_none=True) == {
        "content": "## 每日签到",
        "force_verify_image_resource": True,
    }
