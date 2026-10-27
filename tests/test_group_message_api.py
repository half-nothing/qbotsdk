# Copyright (c) 2026-present Half_nothing.

"""群消息接口：msg_type 推断、msg_seq 去重语义、键盘嵌套形状、撤回。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import aiohttp.web
import pytest

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
from qbotsdk.model.media import MediaInfo
from qbotsdk.model.message import GroupMessageReceipt
from tests.support import MockServer

DATA = Path(__file__).parent / "data"

GROUP = "group-1"
MESSAGES = f"/v2/groups/{GROUP}/messages"


def snapshot(name: str) -> Any:
    return json.loads((DATA / name).read_text(encoding="utf-8"))


def json_route(server: MockServer, method: str, path: str, payload: object) -> None:
    async def handler(request: aiohttp.web.Request) -> aiohttp.web.StreamResponse:
        return aiohttp.web.json_response(payload)

    server.route(method, path, handler)


def call_to(server: MockServer, path: str) -> Any:
    return next(call for call in server.calls if call.path == path)


def payload(call: Any) -> dict[str, Any]:
    assert isinstance(call.json, dict)
    return call.json


def _keyboard() -> Keyboard:
    return Keyboard(
        content=KeyboardContent(
            rows=[
                KeyboardRow(
                    buttons=[
                        Button(
                            id="btn-1",
                            render_data=ButtonRenderData(label="点我", visited_label="已点"),
                            action=ButtonAction(
                                type=ButtonActionType.CALLBACK,
                                data="ping",
                                permission=ButtonPermission(type=ButtonPermissionType.EVERYONE),
                            ),
                        )
                    ]
                )
            ]
        )
    )


async def test_group_send_infers_msg_type(bot: Bot, server: MockServer) -> None:
    json_route(server, "POST", MESSAGES, snapshot("group_message_receipt.json"))

    await bot.api.group.send_message(GROUP, content="hi")
    await bot.api.group.send_message(GROUP, markdown=MessageMarkdown(content="# 标题"))
    await bot.api.group.send_message(GROUP, media=MediaInfo(file_info="FILEINFO"))

    bodies = [payload(call) for call in server.calls if call.path == MESSAGES]
    assert [body["msg_type"] for body in bodies] == [0, 2, 7]
    # markdown 消息不带 content, 富媒体消息只带 media
    assert "content" not in bodies[1]
    assert bodies[2]["media"] == {"file_info": "FILEINFO"}


async def test_group_send_reply_defaults_seq(bot: Bot, server: MockServer) -> None:
    receipt = snapshot("group_message_receipt.json")
    json_route(server, "POST", MESSAGES, receipt)

    message = await bot.api.group.send_message(GROUP, content="hi", reply_to="msg-9")

    assert isinstance(message, GroupMessageReceipt)
    assert message.id == "xxxxxx"
    body = call_to(server, MESSAGES).json
    assert body["msg_id"] == "msg-9"
    assert body["msg_seq"] == 1


async def test_group_send_explicit_seq(bot: Bot, server: MockServer) -> None:
    json_route(server, "POST", MESSAGES, snapshot("group_message_receipt.json"))

    await bot.api.group.send_message(GROUP, content="hi", reply_to="msg-9", msg_seq=3)

    assert call_to(server, MESSAGES).json["msg_seq"] == 3


async def test_group_send_without_reply_has_no_seq(bot: Bot, server: MockServer) -> None:
    json_route(server, "POST", MESSAGES, snapshot("group_message_receipt.json"))

    await bot.api.group.send_message(GROUP, content="hi")

    body = call_to(server, MESSAGES).json
    assert "msg_id" not in body
    assert "msg_seq" not in body


async def test_group_send_keyboard_payload(bot: Bot, server: MockServer) -> None:
    json_route(server, "POST", MESSAGES, snapshot("group_message_receipt.json"))

    await bot.api.group.send_message(GROUP, content="hi", keyboard=_keyboard())

    keyboard = call_to(server, MESSAGES).json["keyboard"]
    button = keyboard["content"]["rows"][0]["buttons"][0]
    assert button["id"] == "btn-1"
    assert button["render_data"]["label"] == "点我"
    assert button["action"]["type"] == 1
    assert button["action"]["permission"] == {"type": 2}
    # unsupport_tips 是必填项, 模型给了默认值
    assert button["action"]["unsupport_tips"] == "此操作暂不支持"


async def test_group_recall_returns_none(bot: Bot, server: MockServer) -> None:
    async def handler(request: aiohttp.web.Request) -> aiohttp.web.StreamResponse:
        return aiohttp.web.json_response({})

    server.route("DELETE", f"{MESSAGES}/msg-1", handler)

    await bot.api.group.recall_message(GROUP, "msg-1")

    assert call_to(server, f"{MESSAGES}/msg-1").method == "DELETE"


async def test_group_send_rejects_mismatched_type(bot: Bot, server: MockServer) -> None:
    # markdown 消息带 content 会被判为类型与内容不匹配, 本地先拦下
    with pytest.raises(ValueError):
        await bot.api.group.send_message(
            GROUP,
            content="hi",
            markdown=MessageMarkdown(content="# 标题"),
        )

    assert server.calls == []
