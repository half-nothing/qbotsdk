# Copyright (c) 2026-present Half_nothing.

"""频道消息接口：JSON 与 multipart 两种包体、撤回、以及消息域占位。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import aiohttp.web
import pytest

from qqbot.bot import Bot
from qqbot.model.draft import MessageMarkdown
from qqbot.model.message import Message
from tests.support import MockServer

DATA = Path(__file__).parent / "data"

CHANNEL_ID = "10001"
MESSAGES = f"/channels/{CHANNEL_ID}/messages"


def snapshot(name: str) -> Any:
    return json.loads((DATA / name).read_text(encoding="utf-8"))


def json_route(server: MockServer, method: str, path: str, payload: object) -> None:
    async def handler(request: aiohttp.web.Request) -> aiohttp.web.StreamResponse:
        return aiohttp.web.json_response(payload)

    server.route(method, path, handler)


def call_to(server: MockServer, path: str) -> Any:
    return next(call for call in server.calls if call.path == path)


async def test_channel_send_text(bot: Bot, server: MockServer) -> None:
    json_route(server, "POST", MESSAGES, snapshot("channel_message.json"))

    message = await bot.api.channel.send_message(CHANNEL_ID, content="hello")

    assert isinstance(message, Message)
    assert message.content == "<@!1234>hello world"
    assert message.author.bot is True
    assert call_to(server, MESSAGES).json == {"content": "hello"}


async def test_channel_send_requires_content(bot: Bot, server: MockServer) -> None:
    with pytest.raises(ValueError):
        await bot.api.channel.send_message(CHANNEL_ID)

    # 包体不合格时不该产生任何请求
    assert server.calls == []


async def test_channel_send_markdown_excludes_content(bot: Bot, server: MockServer) -> None:
    json_route(server, "POST", MESSAGES, snapshot("channel_message.json"))

    await bot.api.channel.send_message(
        CHANNEL_ID,
        content="纯文本",
        markdown=MessageMarkdown(content="# 标题"),
    )

    body = call_to(server, MESSAGES).json
    assert "content" not in body
    assert body["markdown"] == {"content": "# 标题"}


async def test_channel_send_multipart_file_image(bot: Bot, server: MockServer) -> None:
    json_route(server, "POST", MESSAGES, snapshot("channel_message.json"))

    message = await bot.api.channel.send_message(
        CHANNEL_ID,
        content="带图",
        file_image=b"\x89PNG\r\n",
        file_name="a.png",
    )

    assert isinstance(message, Message)
    call = call_to(server, MESSAGES)
    assert call.headers["Content-Type"].startswith("multipart/form-data")
    assert b'name="content"' in call.body
    assert b'name="file_image"; filename="a.png"' in call.body
    assert b"image/png" in call.body


async def test_channel_send_rejects_image_and_file(bot: Bot, server: MockServer) -> None:
    with pytest.raises(ValueError):
        await bot.api.channel.send_message(
            CHANNEL_ID,
            image="https://example.com/a.png",
            file_image=b"\x89PNG",
        )

    assert server.calls == []


async def test_channel_recall_uses_query_flag(bot: Bot, server: MockServer) -> None:
    async def handler(request: aiohttp.web.Request) -> aiohttp.web.StreamResponse:
        return aiohttp.web.Response(status=200)

    server.route("DELETE", f"{MESSAGES}/msg-1", handler)

    await bot.api.channel.recall_message(CHANNEL_ID, "msg-1", hide_tip=True)

    assert call_to(server, f"{MESSAGES}/msg-1").query == {"hidetip": "true"}


async def test_message_reply_placeholder(bot: Bot) -> None:
    with pytest.raises(NotImplementedError):
        await bot.api.message.reply("msg-1", "hi")
