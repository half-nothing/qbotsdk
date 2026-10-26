# Copyright (c) 2026-present Half_nothing.

from __future__ import annotations

import aiohttp
import aiohttp.web

from qqbot.bot import Bot
from qqbot.module.token_manager import TokenManager
from tests.support import MockServer, add_token_route


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


async def test_token_manager_caches_and_refreshes(
    server: MockServer,
    point_at: None,
) -> None:
    token_calls = {"n": 0}

    async def counting_handler(
        request: aiohttp.web.Request,
    ) -> aiohttp.web.StreamResponse:
        token_calls["n"] += 1
        return aiohttp.web.json_response(
            {"access_token": f"token-{token_calls['n']}", "expires_in": 7200}
        )

    add_token_route(server, counting_handler)
    manager = TokenManager(app_id="app", client_secret="secret")

    async with aiohttp.ClientSession() as session:
        first = await manager.get_token(session)
        second = await manager.get_token(session)
        assert first == second == "token-1"

        manager.invalidate()
        refreshed = await manager.get_token(session)
        assert refreshed == "token-2"

    assert token_calls["n"] == 2
