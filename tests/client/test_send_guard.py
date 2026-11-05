# Copyright (c) 2026-present Half_nothing.

"""主动消息发送切面：before_send 放行/拒绝、after_send 反馈、默认实现与注入。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import aiohttp.web
import pytest

from qbotsdk.bot import Bot
from qbotsdk.exceptions import APIError, QQBotError, RateLimitExceededError
from qbotsdk.module.send_guard import LocalRateLimitGuard, SendContext, SendVerdict
from qbotsdk.options import ClientOptions
from tests.support import MockServer, add_token_route

DATA = Path(__file__).parents[1] / "data"
USER = "user-1"
GROUP = "group-1"
C2C_PATH = f"/v2/users/{USER}/messages"
GROUP_PATH = f"/v2/groups/{GROUP}/messages"


def snapshot(name: str) -> Any:
    return json.loads((DATA / name).read_text(encoding="utf-8"))


def json_route(server: MockServer, method: str, path: str, payload: object) -> None:
    async def handler(request: aiohttp.web.Request) -> aiohttp.web.StreamResponse:
        return aiohttp.web.json_response(payload)

    server.route(method, path, handler)


class RecordingGuard:
    """记录每次判定与回调, 便于断言切面拿到的上下文。"""

    def __init__(
        self, verdict: SendVerdict | None = None, *, after_error: Exception | None = None
    ) -> None:
        self.verdict = verdict
        self.after_error = after_error
        self.before: list[SendContext] = []
        self.after: list[QQBotError | None] = []

    async def before_send(self, context: SendContext) -> SendVerdict | None:
        self.before.append(context)
        return self.verdict

    async def after_send(self, context: SendContext, error: QQBotError | None) -> None:
        self.after.append(error)
        if self.after_error is not None:
            raise self.after_error


async def test_guard_marks_passive_replies(server: MockServer, point_at: None) -> None:
    add_token_route(server)
    json_route(server, "POST", GROUP_PATH, snapshot("group_message_receipt.json"))
    guard = RecordingGuard()
    options = ClientOptions(send_guard=guard)
    async with Bot(app_id="app", app_secret="secret", options=options) as bot:
        await bot.api.group.send_message(GROUP, content="active")
        await bot.api.group.send_message(GROUP, content="reply", reply_to="msg-1")
        await bot.api.group.send_message(GROUP, content="event", event_id="event-1")

    assert [context.active for context in guard.before] == [True, False, False]
    assert all(context.scope == "group" and context.target == GROUP for context in guard.before)
    assert guard.after == [None, None, None]


async def test_denied_send_raises_without_request(server: MockServer, point_at: None) -> None:
    add_token_route(server)
    json_route(server, "POST", GROUP_PATH, snapshot("group_message_receipt.json"))
    guard = RecordingGuard(
        SendVerdict.deny(retry_after=120.0, reason="active message quota reached", limit=20.0)
    )
    options = ClientOptions(send_guard=guard)
    async with Bot(app_id="app", app_secret="secret", options=options) as bot:
        with pytest.raises(RateLimitExceededError) as info:
            await bot.api.group.send_message(GROUP, content="blocked")

    assert info.value.scope == "group"
    assert info.value.key == GROUP
    assert info.value.retry_after == 120.0
    assert info.value.limit == 20.0
    assert info.value.reason == "active message quota reached"
    assert [call for call in server.calls if call.path == GROUP_PATH] == []
    # 被拦截的发送不该触发 after_send
    assert guard.after == []


async def test_after_send_receives_api_error(server: MockServer, point_at: None) -> None:
    add_token_route(server)

    async def handler(request: aiohttp.web.Request) -> aiohttp.web.StreamResponse:
        return aiohttp.web.json_response(
            {"err_code": 40034100, "message": "proactive message rate limited"}, status=400
        )

    server.route("POST", GROUP_PATH, handler)
    guard = RecordingGuard()
    options = ClientOptions(send_guard=guard)
    async with Bot(app_id="app", app_secret="secret", options=options) as bot:
        with pytest.raises(APIError):
            await bot.api.group.send_message(GROUP, content="hi")

    assert len(guard.after) == 1
    error = guard.after[0]
    assert isinstance(error, APIError)
    assert error.code == 40034100


async def test_after_send_failure_does_not_break_send(server: MockServer, point_at: None) -> None:
    add_token_route(server)
    json_route(server, "POST", C2C_PATH, snapshot("group_message_receipt.json"))
    guard = RecordingGuard(after_error=RuntimeError("storage is down"))
    options = ClientOptions(send_guard=guard)
    async with Bot(app_id="app", app_secret="secret", options=options) as bot:
        sent = await bot.api.user_message.send_message(USER, content="hi")

    assert sent is not None
    assert len(guard.after) == 1


async def test_default_guard_is_local_rate_limit(server: MockServer, point_at: None) -> None:
    add_token_route(server)
    async with Bot(app_id="app", app_secret="secret") as bot:
        guard = bot.api.send_guard

    assert isinstance(guard, LocalRateLimitGuard)
    assert guard.limiter.remaining("group", GROUP) == pytest.approx(20.0)


async def test_respect_rate_limits_off_disables_default_guard(
    server: MockServer, point_at: None
) -> None:
    add_token_route(server)
    options = ClientOptions(respect_rate_limits=False)
    async with Bot(app_id="app", app_secret="secret", options=options) as bot:
        assert bot.api.send_guard is None


async def test_injected_guard_wins_when_local_limit_is_off(
    server: MockServer, point_at: None
) -> None:
    add_token_route(server)
    json_route(server, "POST", C2C_PATH, snapshot("group_message_receipt.json"))
    guard = RecordingGuard()
    options = ClientOptions(respect_rate_limits=False, send_guard=guard)
    async with Bot(app_id="app", app_secret="secret", options=options) as bot:
        await bot.api.user_message.send_message(USER, content="hi")

    assert [context.scope for context in guard.before] == ["c2c"]
    assert guard.after == [None]
