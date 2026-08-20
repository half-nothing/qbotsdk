import asyncio
import socket
from collections.abc import AsyncIterator, Callable, Coroutine
from contextlib import asynccontextmanager
from typing import Any

import aiohttp
import aiohttp.web

import qqbot.module.http_client
import qqbot.module.token_manager
from qqbot.bot import Bot
from qqbot.module.token_manager import TokenManager


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        _, port = s.getsockname()
        return int(port)


@asynccontextmanager
async def _server(
    routes: list[
        tuple[
            str,
            str,
            Callable[[aiohttp.web.Request], Coroutine[Any, Any, aiohttp.web.Response]],
        ]
    ],
) -> AsyncIterator[str]:
    app = aiohttp.web.Application()
    for method, path, handler in routes:
        app.router.add_route(method, path, handler)
    runner = aiohttp.web.AppRunner(app)
    await runner.setup()
    site = aiohttp.web.TCPSite(runner, "127.0.0.1", _free_port())
    await site.start()
    port = site._server.sockets[0].getsockname()[1]  # type: ignore[union-attr]
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        await runner.cleanup()


def test_get_me_injects_authorization_header(monkeypatch: Any) -> None:
    seen: list[str] = []

    async def token_handler(request: aiohttp.web.Request) -> aiohttp.web.Response:
        body = await request.json()
        assert body == {"appId": "app", "clientSecret": "secret"}
        return aiohttp.web.json_response(
            {"access_token": "test-token", "expires_in": 7200}
        )

    async def me_handler(request: aiohttp.web.Request) -> aiohttp.web.Response:
        seen.append(request.headers.get("Authorization", ""))
        return aiohttp.web.json_response(
            {
                "id": "123",
                "username": "tester",
                "avatar": "https://example.com/a.png",
                "bot": True,
            }
        )

    async def inner() -> None:
        async with _server(
            [
                ("POST", "/app/getAppAccessToken", token_handler),
                ("GET", "/users/@me", me_handler),
            ]
        ) as base:
            monkeypatch.setattr(
                qqbot.module.token_manager,
                "TOKEN_URL",
                f"{base}/app/getAppAccessToken",
            )
            monkeypatch.setattr(qqbot.module.http_client, "BASE_URL", base)
            async with Bot(app_id="app", client_secret="secret") as bot:
                me = await bot.get_me()
                assert me.id == "123"
                assert me.username == "tester"
                assert me.bot is True

    asyncio.run(inner())
    assert seen == ["QQBot test-token"]


def test_token_manager_caches_and_refreshes(monkeypatch: Any) -> None:
    token_calls = {"n": 0}

    async def token_handler(request: aiohttp.web.Request) -> aiohttp.web.Response:
        token_calls["n"] += 1
        return aiohttp.web.json_response(
            {"access_token": f"token-{token_calls['n']}", "expires_in": 7200}
        )

    async def inner() -> None:
        async with _server([("POST", "/app/getAppAccessToken", token_handler)]) as base:
            monkeypatch.setattr(
                qqbot.module.token_manager,
                "TOKEN_URL",
                f"{base}/app/getAppAccessToken",
            )
            manager = TokenManager(app_id="app", client_secret="secret")
            async with aiohttp.ClientSession() as session:
                first = await manager.get_token(session)
                second = await manager.get_token(session)
                assert first == second == "token-1"
                manager._expire_at = 0.0
                refreshed = await manager.get_token(session)
                assert refreshed == "token-2"

    asyncio.run(inner())
    assert token_calls["n"] == 2
