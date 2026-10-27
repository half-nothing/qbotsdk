# Copyright (c) 2026-present Half_nothing.

"""单聊（C2C）消息接口：msg_type 推断、被动回复 seq、输入中状态、撤回、上传。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import aiohttp.web
import pytest

from qbotsdk.bot import Bot
from qbotsdk.model.draft import MessageMarkdown
from qbotsdk.model.media import FileType, MediaInfo
from qbotsdk.model.message import UserMessageReceipt
from tests.support import MockServer

DATA = Path(__file__).parent / "data"

USER = "user-1"
MESSAGES = f"/v2/users/{USER}/messages"
FILES = f"/v2/users/{USER}/files"


def snapshot(name: str) -> Any:
    return json.loads((DATA / name).read_text(encoding="utf-8"))


def json_route(server: MockServer, method: str, path: str, payload: object) -> None:
    async def handler(request: aiohttp.web.Request) -> aiohttp.web.StreamResponse:
        return aiohttp.web.json_response(payload)

    server.route(method, path, handler)


def call_to(server: MockServer, path: str) -> Any:
    return next(call for call in server.calls if call.path == path)


def body_of(server: MockServer, path: str) -> dict[str, Any]:
    body = call_to(server, path).json
    assert isinstance(body, dict)
    return body


async def test_send_text(bot: Bot, server: MockServer) -> None:
    json_route(server, "POST", MESSAGES, snapshot("group_message_receipt.json"))

    receipt = await bot.api.user_message.send_message(USER, content="hi")

    assert isinstance(receipt, UserMessageReceipt)
    assert receipt.id == "xxxxxx"
    body = body_of(server, MESSAGES)
    assert body["msg_type"] == 0
    assert body["content"] == "hi"


async def test_send_reply_defaults_seq(bot: Bot, server: MockServer) -> None:
    json_route(server, "POST", MESSAGES, snapshot("group_message_receipt.json"))

    await bot.api.user_message.send_message(USER, content="hi", reply_to="msg-9")

    body = body_of(server, MESSAGES)
    assert body["msg_id"] == "msg-9"
    assert body["msg_seq"] == 1


async def test_send_markdown_is_type_2(bot: Bot, server: MockServer) -> None:
    json_route(server, "POST", MESSAGES, snapshot("group_message_receipt.json"))

    await bot.api.user_message.send_message(USER, markdown=MessageMarkdown(content="# 标题"))

    body = body_of(server, MESSAGES)
    assert body["msg_type"] == 2
    assert "content" not in body


async def test_send_media_is_type_7(bot: Bot, server: MockServer) -> None:
    json_route(server, "POST", MESSAGES, snapshot("group_message_receipt.json"))

    await bot.api.user_message.send_message(USER, media=MediaInfo(file_info="FILEINFO"))

    body = body_of(server, MESSAGES)
    assert body["msg_type"] == 7
    assert body["media"] == {"file_info": "FILEINFO"}


async def test_notify_input_is_type_6(bot: Bot, server: MockServer) -> None:
    json_route(server, "POST", MESSAGES, snapshot("group_message_receipt.json"))

    await bot.api.user_message.notify_input(USER, seconds=30)

    body = body_of(server, MESSAGES)
    assert body["msg_type"] == 6
    assert body["input_notify"] == {"input_type": 1, "input_second": 30}


async def test_notify_input_rejects_long_second(bot: Bot, server: MockServer) -> None:
    with pytest.raises(ValueError):
        await bot.api.user_message.notify_input(USER, seconds=61)

    assert server.calls == []


async def test_wakeup_cannot_reply(bot: Bot, server: MockServer) -> None:
    # 互动召回消息不是回复, 与 msg_id 互斥, 本地先拦下
    with pytest.raises(ValueError):
        await bot.api.user_message.send_message(
            USER, content="hi", reply_to="msg-9", is_wakeup=True
        )

    assert server.calls == []


async def test_recall_message(bot: Bot, server: MockServer) -> None:
    async def handler(request: aiohttp.web.Request) -> aiohttp.web.StreamResponse:
        return aiohttp.web.json_response({})

    server.route("DELETE", f"{MESSAGES}/msg-1", handler)

    await bot.api.user_message.recall_message(USER, "msg-1")

    call = call_to(server, f"{MESSAGES}/msg-1")
    assert call.method == "DELETE"


async def test_upload_by_url(bot: Bot, server: MockServer) -> None:
    json_route(server, "POST", FILES, snapshot("group_file.json"))

    uploaded = await bot.api.user_message.upload_file(USER, FileType.IMAGE, url="https://x/a.png")

    assert uploaded.file_info == "xxxxxx"
    body = body_of(server, FILES)
    assert body == {"file_type": 1, "url": "https://x/a.png", "srv_send_msg": False}
