# Copyright (c) 2026-present Half_nothing.

"""TokenManager 的生命周期：单飞刷新、刷新窗口、失败回退、硬过期。"""

from __future__ import annotations

import asyncio

import aiohttp
import aiohttp.web
import pytest

import qqbot.module.token_manager
from qqbot.exceptions import APIError
from qqbot.module.token_manager import TokenManager
from tests.support import TOKEN_PATH, MockServer, add_token_route

EXPIRES_IN = 7200


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> dict[str, float]:
    """把 monotonic 换成可推进的假时钟，时间相关断言不真等。"""

    now = {"value": 1000.0}
    monkeypatch.setattr(qqbot.module.token_manager, "monotonic", lambda: now["value"])
    return now


def counting_token_route(server: MockServer, expires_in: int = EXPIRES_IN) -> None:
    """每次调用返回不同的 token，次数就是凭证接口被打了多少次。"""

    state = {"n": 0}

    async def handler(request: aiohttp.web.Request) -> aiohttp.web.StreamResponse:
        state["n"] += 1
        return aiohttp.web.json_response(
            {"access_token": f"token-{state['n']}", "expires_in": expires_in}
        )

    add_token_route(server, handler)


async def server_error_handler(request: aiohttp.web.Request) -> aiohttp.web.StreamResponse:
    return aiohttp.web.json_response({"message": "server error"}, status=500)


def token_call_count(server: MockServer) -> int:
    return len([call for call in server.calls if call.path == TOKEN_PATH])


async def test_concurrent_single_fetch(
    server: MockServer, point_at: None, clock: dict[str, float]
) -> None:
    counting_token_route(server)
    manager = TokenManager("app", "secret")

    async with aiohttp.ClientSession() as session:
        tokens = await asyncio.gather(*[manager.get_token(session) for _ in range(10)])

    assert set(tokens) == {"token-1"}
    assert token_call_count(server) == 1


async def test_refresh_after_window(
    server: MockServer, point_at: None, clock: dict[str, float]
) -> None:
    counting_token_route(server)
    manager = TokenManager("app", "secret")

    async with aiohttp.ClientSession() as session:
        assert await manager.get_token(session) == "token-1"

        # 已过 refresh_at（到期前 60 秒），旧 token 仍在硬有效期内
        clock["value"] += EXPIRES_IN - 30
        assert await manager.get_token(session) == "token-2"

    assert token_call_count(server) == 2


async def test_fallback_after_refresh_failure(
    server: MockServer, point_at: None, clock: dict[str, float]
) -> None:
    counting_token_route(server)
    manager = TokenManager("app", "secret")

    async with aiohttp.ClientSession() as session:
        assert await manager.get_token(session) == "token-1"

        add_token_route(server, server_error_handler)
        clock["value"] += EXPIRES_IN - 30

        # 刷新失败但旧 token 还没到硬过期时间，继续用它
        assert await manager.get_token(session) == "token-1"

    assert token_call_count(server) == 2


async def test_hard_expire_raises(
    server: MockServer, point_at: None, clock: dict[str, float]
) -> None:
    counting_token_route(server)
    manager = TokenManager("app", "secret")

    async with aiohttp.ClientSession() as session:
        assert await manager.get_token(session) == "token-1"

        add_token_route(server, server_error_handler)
        # 连硬有效期都过了，刷新又失败，只能把错误抛给调用方
        clock["value"] += EXPIRES_IN + 1

        with pytest.raises(APIError) as info:
            await manager.get_token(session)

    assert info.value.status == 500


async def test_invalidate_forces_refresh(
    server: MockServer, point_at: None, clock: dict[str, float]
) -> None:
    counting_token_route(server)
    manager = TokenManager("app", "secret")

    async with aiohttp.ClientSession() as session:
        first = await manager.get_token(session)
        second = await manager.get_token(session)
        assert first == second == "token-1"

        manager.invalidate()
        assert await manager.get_token(session) == "token-2"

    assert token_call_count(server) == 2


async def test_short_lived_token_refreshes_at_half_lifetime(
    server: MockServer, point_at: None, clock: dict[str, float]
) -> None:
    # expires_in 比 60 秒的预留窗口还短，退化成半程刷新，不能每次调用都打凭证接口
    counting_token_route(server, expires_in=30)
    manager = TokenManager("app", "secret")

    async with aiohttp.ClientSession() as session:
        assert await manager.get_token(session) == "token-1"

        clock["value"] += 10
        assert await manager.get_token(session) == "token-1"

        clock["value"] += 6
        assert await manager.get_token(session) == "token-2"


async def test_error_body_with_200_raises_api_error(
    server: MockServer, point_at: None, clock: dict[str, float]
) -> None:
    """凭证接口用 HTTP 200 返回 err_code，应转成 APIError，而不是交给 pydantic 校验。"""

    async def handler(request: aiohttp.web.Request) -> aiohttp.web.StreamResponse:
        return aiohttp.web.json_response(
            {"err_code": 11252, "message": "invalid appid or secret", "trace_id": "trace-1"}
        )

    add_token_route(server, handler)
    manager = TokenManager("app", "secret")

    async with aiohttp.ClientSession() as session:
        with pytest.raises(APIError) as info:
            await manager.get_token(session)

    assert info.value.status == 200
    assert info.value.code == 11252
    assert info.value.trace_id == "trace-1"
    assert info.value.path == TOKEN_PATH
    assert "invalid appid or secret" in info.value.message


async def test_malformed_200_body_raises_api_error(
    server: MockServer, point_at: None, clock: dict[str, float]
) -> None:
    """200 但包体不是凭证结构时，同样抛 APIError，不让 ValidationError 泄漏出去。"""

    async def handler(request: aiohttp.web.Request) -> aiohttp.web.StreamResponse:
        return aiohttp.web.json_response({"message": "something went wrong"})

    add_token_route(server, handler)
    manager = TokenManager("app", "secret")

    async with aiohttp.ClientSession() as session:
        with pytest.raises(APIError) as info:
            await manager.get_token(session)

    assert info.value.status == 200
    assert "something went wrong" in info.value.message
    assert info.value.path == TOKEN_PATH
