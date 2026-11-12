# Copyright (c) 2026-present Half_nothing.

"""单聊(C2C)消息接口: msg_type 推断、被动回复 seq、输入中状态、撤回、上传。"""

from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path
from typing import Any

import aiohttp.web
import pytest

from qbotsdk.api._upload import DIRECT_UPLOAD_LIMIT
from qbotsdk.bot import Bot
from qbotsdk.model.draft import MessageMarkdown
from qbotsdk.model.keyboard import (
    Button,
    ButtonAction,
    ButtonActionType,
    ButtonPermission,
    ButtonPermissionType,
    ButtonRenderData,
    Keyboard,
    KeyboardContent,
    KeyboardRow,
)
from qbotsdk.model.media import FileType, MediaInfo
from qbotsdk.model.message import UserMessageReceipt
from qbotsdk.module import SendRecord
from qbotsdk.options import ClientOptions
from tests.support import MockServer, add_token_route

DATA = Path(__file__).parents[1] / "data"

USER = "user-1"
MESSAGES = f"/v2/users/{USER}/messages"
FILES = f"/v2/users/{USER}/files"
PREPARE = f"/v2/users/{USER}/upload_prepare"
FINISH = f"/v2/users/{USER}/upload_part_finish"


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


def calls_to(server: MockServer, path: str) -> int:
    return len([call for call in server.calls if call.path == path])


def payload(call: Any) -> dict[str, Any]:
    body = call.json
    assert isinstance(body, dict)
    return body


def prepare_route(server: MockServer, *, block_size: int, part_count: int) -> None:
    async def handler(request: aiohttp.web.Request) -> aiohttp.web.StreamResponse:
        return aiohttp.web.json_response(
            {
                "upload_id": "up-1",
                "block_size": str(block_size),
                "parts": [
                    {
                        "index": index,
                        "presigned_url": f"{server.url}/cos/part-{index}",
                        "block_size": str(block_size),
                    }
                    for index in range(part_count)
                ],
                "upload_config": {"concurrency": 1, "retry_timeout": 5, "retry_delay": 0},
            }
        )

    server.route("POST", PREPARE, handler)


def put_routes(server: MockServer, part_count: int) -> None:
    async def ok(request: aiohttp.web.Request) -> aiohttp.web.StreamResponse:
        return aiohttp.web.Response(status=200)

    for index in range(part_count):
        server.route("PUT", f"/cos/part-{index}", ok)


def finish_route(server: MockServer) -> None:
    async def ok(request: aiohttp.web.Request) -> aiohttp.web.StreamResponse:
        return aiohttp.web.json_response({})

    server.route("POST", FINISH, ok)


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


def keyboard() -> Keyboard:
    return Keyboard(
        content=KeyboardContent(
            rows=[
                KeyboardRow(
                    buttons=[
                        Button(
                            id="btn-1",
                            render_data=ButtonRenderData(label="点我", visited_label="点过了"),
                            action=ButtonAction(
                                type=ButtonActionType.CALLBACK,
                                data="btn-1",
                                permission=ButtonPermission(type=ButtonPermissionType.EVERYONE),
                            ),
                        )
                    ]
                )
            ]
        )
    )


async def test_send_keyboard_lifts_text_to_markdown(bot: Bot, server: MockServer) -> None:
    # 平台只在 Markdown 消息上渲染按钮, 文本会在本地被搬进 markdown
    json_route(server, "POST", MESSAGES, snapshot("group_message_receipt.json"))

    await bot.api.user_message.send_message(USER, content="hi", keyboard=keyboard())

    body = body_of(server, MESSAGES)
    assert body["msg_type"] == 2
    assert body["markdown"] == {"content": "hi"}
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


async def test_upload_small_file_is_base64(bot: Bot, server: MockServer) -> None:
    json_route(server, "POST", FILES, snapshot("group_file.json"))

    await bot.api.user_message.upload_file(USER, FileType.FILE, file=b"hello", file_name="a.txt")

    body = body_of(server, FILES)
    assert body["file_type"] == 4
    assert body["file_name"] == "a.txt"
    assert base64.b64decode(body["file_data"]) == b"hello"
    assert calls_to(server, PREPARE) == 0


async def test_upload_needs_exactly_one_source(bot: Bot, server: MockServer) -> None:
    with pytest.raises(ValueError):
        await bot.api.user_message.upload_file(USER, FileType.FILE)
    with pytest.raises(ValueError):
        await bot.api.user_message.upload_file(USER, FileType.FILE, url="https://x", file=b"a")

    assert server.calls == []


async def test_upload_large_file_streams_parts(bot: Bot, server: MockServer) -> None:
    data = b"a" * DIRECT_UPLOAD_LIMIT + b"b"
    json_route(server, "POST", FILES, snapshot("group_file.json"))
    prepare_route(server, block_size=DIRECT_UPLOAD_LIMIT, part_count=2)
    put_routes(server, 2)
    finish_route(server)

    seen: list[tuple[int, int]] = []
    uploaded = await bot.api.user_message.upload_file(
        USER,
        FileType.FILE,
        file=data,
        file_name="a.bin",
        progress=lambda done, total: seen.append((done, total)),
    )

    assert uploaded.file_info == "xxxxxx"
    prepare = body_of(server, PREPARE)
    assert prepare["file_size"] == str(len(data))
    assert prepare["md5"] == hashlib.md5(data, usedforsecurity=False).hexdigest()
    assert prepare["sha1"] == hashlib.sha1(data, usedforsecurity=False).hexdigest()

    parts = sorted(
        (call for call in server.calls if call.method == "PUT"), key=lambda call: call.path
    )
    assert [call.body for call in parts] == [data[:DIRECT_UPLOAD_LIMIT], b"b"]
    assert all("Authorization" not in call.headers for call in parts)

    finishes = [payload(call) for call in server.calls if call.path == FINISH]
    finishes.sort(key=lambda body: body["part_index"])
    assert [body["block_size"] for body in finishes] == [DIRECT_UPLOAD_LIMIT, 1]

    assert body_of(server, FILES) == {
        "file_type": 4,
        "file_name": "a.bin",
        "upload_id": "up-1",
        "srv_send_msg": False,
    }
    assert sorted(seen) == [(len(data) - 1, len(data)), (len(data), len(data))]


async def test_upload_reports_send_record(server: MockServer, point_at: None) -> None:
    add_token_route(server)
    json_route(server, "POST", FILES, {"file_uuid": "u", "file_info": "i", "ttl": 60, "id": "m1"})

    class Hook:
        def __init__(self) -> None:
            self.records: list[SendRecord] = []

        async def on_sent(self, record: SendRecord) -> None:
            self.records.append(record)

    hook = Hook()
    async with Bot(app_id="app", app_secret="secret", options=ClientOptions(send_hook=hook)) as bot:
        await bot.api.user_message.upload_file(
            USER, FileType.IMAGE, file=b"png", file_name="a.png", srv_send_msg=True
        )

    (record,) = hook.records
    assert record.scope == "c2c"
    assert record.target == USER
    assert record.path == FILES
    assert record.proactive is True
    assert record.message is None
    assert record.message_id == "m1"
    assert record.error is None
