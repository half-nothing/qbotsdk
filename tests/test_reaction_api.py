# Copyright (c) 2026-present Half_nothing.

"""表情表态接口。

`/channels/{channel_id}/messages/{message_id}/reactions/{type}/{id}` 的
路径参数与返回 `true` 取自官方 Python SDK 的接口页, 官方 api-v2 侧没有
单独的 reactions 接口页, 只有对象表(emoji/model.html, reaction/model.html)。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import aiohttp.web
import pytest

from qqbot.bot import Bot
from qqbot.model.reaction import EmojiType, ReactionTargetType, ReactionUsers
from tests.support import MockServer

CHANNEL = "channel-1"
MESSAGE = "message-1"
REACTIONS = f"/channels/{CHANNEL}/messages/{MESSAGE}/reactions"
DATA = Path(__file__).with_name("data")


def json_route(server: MockServer, method: str, path: str, payload: object) -> None:
    async def handler(request: aiohttp.web.Request) -> aiohttp.web.StreamResponse:
        return aiohttp.web.json_response(payload)

    server.route(method, path, handler)


def calls_to(server: MockServer, path: str) -> list[Any]:
    return [call for call in server.calls if call.path == path]


def snapshot() -> dict[str, Any]:
    payload: dict[str, Any] = json.loads((DATA / "reaction_users.json").read_text("utf-8"))
    return payload


async def test_add_reaction_uses_put(bot: Bot, server: MockServer) -> None:
    json_route(server, "PUT", f"{REACTIONS}/{EmojiType.SYSTEM}/4", True)

    await bot.api.reaction.add(CHANNEL, MESSAGE, EmojiType.SYSTEM, "4")

    [call] = calls_to(server, f"{REACTIONS}/1/4")
    assert call.method == "PUT"


async def test_remove_reaction_uses_delete(bot: Bot, server: MockServer) -> None:
    json_route(server, "DELETE", f"{REACTIONS}/{EmojiType.EMOJI}/9728", True)

    await bot.api.reaction.remove(CHANNEL, MESSAGE, EmojiType.EMOJI, "9728")

    [call] = calls_to(server, f"{REACTIONS}/2/9728")
    assert call.method == "DELETE"


async def test_users_sends_query_and_parses_page(bot: Bot, server: MockServer) -> None:
    json_route(server, "GET", f"{REACTIONS}/{EmojiType.SYSTEM}", {"users": [], "is_end": True})

    page = await bot.api.reaction.users(CHANNEL, MESSAGE, EmojiType.SYSTEM, emoji_id="4", limit=50)

    [call] = calls_to(server, f"{REACTIONS}/1")
    assert call.query == {"emoji_id": "4", "cookie": "", "limit": "50"}
    assert isinstance(page, ReactionUsers)
    assert page.users == []
    assert page.is_end is True


async def test_users_parses_snapshot(bot: Bot, server: MockServer) -> None:
    json_route(server, "GET", f"{REACTIONS}/{EmojiType.SYSTEM}", snapshot())

    page = await bot.api.reaction.users(CHANNEL, MESSAGE, EmojiType.SYSTEM)

    assert [user.username for user in page.users] == ["Alice", "Bob"]
    assert page.cookie == "page-2"
    assert page.is_end is False


@pytest.mark.parametrize("limit", [0, 101])
async def test_users_rejects_bad_limit(bot: Bot, limit: int) -> None:
    with pytest.raises(ValueError, match="limit must be between 1 and 100"):
        await bot.api.reaction.users(CHANNEL, MESSAGE, EmojiType.SYSTEM, limit=limit)


async def test_iter_users_walks_cookies(bot: Bot, server: MockServer) -> None:
    first = snapshot()
    second: dict[str, Any] = {
        "users": [{"id": "144115218677521114", "username": "Carol", "bot": False}],
        "cookie": "",
        "is_end": True,
    }
    path = f"{REACTIONS}/{EmojiType.SYSTEM}"

    async def dispatch(request: aiohttp.web.Request) -> aiohttp.web.StreamResponse:
        payload = first if not request.query.get("cookie") else second
        return aiohttp.web.json_response(payload)

    server.route("GET", path, dispatch)

    users = [user.username async for user in bot.api.reaction.iter_users(CHANNEL, MESSAGE, 1)]

    assert users == ["Alice", "Bob", "Carol"]
    assert [call.query["cookie"] for call in calls_to(server, path)] == ["", "page-2"]


def test_target_type_values() -> None:
    assert [member.value for member in ReactionTargetType] == [0, 1, 2, 3]
