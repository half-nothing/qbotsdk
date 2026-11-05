# Copyright (c) 2026-present Half_nothing.

"""发送结果切面：群聊、单聊、频道三条通道各回调一次。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import aiohttp.web
import pytest

from qbotsdk.bot import Bot
from qbotsdk.exceptions import APIError, RateLimitExceededError
from qbotsdk.model.draft import (
    ChannelMessageDraft,
    GroupMessageDraft,
    MessageMarkdown,
)
from qbotsdk.module.send_hook import SendRecord
from qbotsdk.options import ClientOptions
from tests.support import MockServer, add_token_route

DATA = Path(__file__).parents[1] / "data"
GROUP = "group-1"
USER = "user-1"
CHANNEL = "channel-1"
GROUP_PATH = f"/v2/groups/{GROUP}/messages"
C2C_PATH = f"/v2/users/{USER}/messages"
CHANNEL_PATH = f"/channels/{CHANNEL}/messages"


def snapshot(name: str) -> Any:
    return json.loads((DATA / name).read_text(encoding="utf-8"))


def json_route(server: MockServer, method: str, path: str, payload: object) -> None:
    async def handler(request: aiohttp.web.Request) -> aiohttp.web.StreamResponse:
        return aiohttp.web.json_response(payload)

    server.route(method, path, handler)


class RecordingHook:
    def __init__(self) -> None:
        self.records: list[SendRecord] = []

    async def on_sent(self, record: SendRecord) -> None:
        self.records.append(record)


async def test_group_send_reports_successful_record(server: MockServer, point_at: None) -> None:
    add_token_route(server)
    json_route(server, "POST", GROUP_PATH, snapshot("group_message_receipt.json"))
    hook = RecordingHook()
    options = ClientOptions(send_hook=hook)

    async with Bot(app_id="app", app_secret="secret", options=options) as bot:
        await bot.api.group.send_message(GROUP, content="hello")

    (record,) = hook.records
    assert record.scope == "group"
    assert record.target == GROUP
    assert record.path == GROUP_PATH
    assert record.proactive is True
    assert record.message is not None
    assert record.message.to_text() == "hello"
    assert record.message_id == "xxxxxx"
    assert record.error is None


async def test_passive_reply_is_not_marked_proactive(server: MockServer, point_at: None) -> None:
    add_token_route(server)
    json_route(server, "POST", GROUP_PATH, snapshot("group_message_receipt.json"))
    hook = RecordingHook()

    async with Bot(app_id="app", app_secret="secret", options=ClientOptions(send_hook=hook)) as bot:
        await bot.api.group.send_message(GROUP, content="hi", reply_to="msg-1")

    (record,) = hook.records
    assert record.proactive is False
    assert record.message_id == "xxxxxx"


async def test_local_rejection_is_reported(server: MockServer, point_at: None) -> None:
    add_token_route(server)
    json_route(server, "POST", GROUP_PATH, snapshot("group_message_receipt.json"))
    hook = RecordingHook()
    options = ClientOptions(send_hook=hook, rate_limits={"group": 1.0})

    async with Bot(app_id="app", app_secret="secret", options=options) as bot:
        await bot.api.group.send_message(GROUP, content="one")
        with pytest.raises(RateLimitExceededError):
            await bot.api.group.send_message(GROUP, content="two")

    assert len(hook.records) == 2
    failed = hook.records[1]
    assert failed.message_id is None
    assert isinstance(failed.error, RateLimitExceededError)
    assert failed.proactive is True


async def test_api_failure_is_reported_and_reraised(server: MockServer, point_at: None) -> None:
    add_token_route(server)

    async def handler(request: aiohttp.web.Request) -> aiohttp.web.StreamResponse:
        return aiohttp.web.json_response(
            {"err_code": 40034100, "message": "proactive message rate limited"},
            status=400,
        )

    server.route("POST", GROUP_PATH, handler)
    hook = RecordingHook()

    async with Bot(app_id="app", app_secret="secret", options=ClientOptions(send_hook=hook)) as bot:
        with pytest.raises(APIError):
            await bot.api.group.send_message(GROUP, content="hi")

    (record,) = hook.records
    assert isinstance(record.error, APIError)
    assert record.error.code == 40034100
    assert record.message_id is None


async def test_c2c_and_channel_are_covered(server: MockServer, point_at: None) -> None:
    add_token_route(server)
    json_route(server, "POST", C2C_PATH, snapshot("group_message_receipt.json"))
    json_route(server, "POST", CHANNEL_PATH, snapshot("channel_message.json"))
    hook = RecordingHook()

    async with Bot(app_id="app", app_secret="secret", options=ClientOptions(send_hook=hook)) as bot:
        await bot.api.user_message.send_message(USER, content="hi")
        await bot.api.channel.send_message(CHANNEL, content="hello")

    c2c, channel = hook.records
    assert (c2c.scope, c2c.target) == ("c2c", USER)
    assert (channel.scope, channel.target) == ("channel", CHANNEL)
    assert channel.message_id == "xxxxxx"
    assert channel.error is None


async def test_rich_message_content_is_recorded(server: MockServer, point_at: None) -> None:
    add_token_route(server)
    json_route(server, "POST", GROUP_PATH, snapshot("group_message_receipt.json"))
    json_route(server, "POST", CHANNEL_PATH, snapshot("channel_message.json"))
    hook = RecordingHook()
    markdown = MessageMarkdown(content="# title")

    async with Bot(app_id="app", app_secret="secret", options=ClientOptions(send_hook=hook)) as bot:
        await bot.api.group.send_message(GROUP, markdown=markdown)
        await bot.api.channel.send_message(
            CHANNEL, markdown=markdown, image="https://example.com/a.png"
        )

    group, channel = hook.records
    # Markdown 消息没有纯文本正文, 可读文本取 Markdown 原文
    assert isinstance(group.message, GroupMessageDraft)
    assert group.message.markdown is not None
    assert group.message.markdown.content == "# title"
    assert group.message.to_text() == "# title"

    assert isinstance(channel.message, ChannelMessageDraft)
    assert channel.message.image == "https://example.com/a.png"
    assert channel.message.markdown is not None
    assert channel.message.markdown.content == "# title"
    assert channel.message.to_text() == "# title\n[image] https://example.com/a.png"


async def test_hook_failure_does_not_break_send(server: MockServer, point_at: None) -> None:
    add_token_route(server)
    json_route(server, "POST", GROUP_PATH, snapshot("group_message_receipt.json"))

    class BrokenHook:
        async def on_sent(self, record: SendRecord) -> None:
            raise RuntimeError("boom")

    options = ClientOptions(send_hook=BrokenHook())
    async with Bot(app_id="app", app_secret="secret", options=options) as bot:
        receipt = await bot.api.group.send_message(GROUP, content="hi")

    assert receipt.id == "xxxxxx"
