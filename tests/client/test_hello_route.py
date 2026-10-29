# Copyright (c) 2026-present Half_nothing.

from __future__ import annotations

import aiohttp
import aiohttp.web
import pytest

from qbotsdk.bot import Bot
from tests.support import MockServer


@pytest.mark.filterwarnings("ignore::DeprecationWarning")
async def test_get_me_injects_authorization_header(bot: Bot, server: MockServer) -> None:
    async def me_handler(request: aiohttp.web.Request) -> aiohttp.web.StreamResponse:
        return aiohttp.web.json_response(
            {
                "id": "123",
                "username": "tester",
                "avatar": "https://example.com/a.png",
                "bot": True,
            }
        )

    server.route("GET", "/users/@me", me_handler)

    me = await bot.get_me()

    assert me.id == "123"
    assert me.username == "tester"
    assert me.bot is True
    me_call = next(call for call in server.calls if call.path == "/users/@me")
    assert me_call.headers["Authorization"] == "QQBot test-token"
