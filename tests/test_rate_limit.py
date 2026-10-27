# Copyright (c) 2026-present Half_nothing.

"""主动消息配额层：令牌桶、开关、被动回复次数上限。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import aiohttp.web
import pytest

from qqbot.bot import Bot
from qqbot.exceptions import APIError, RateLimitExceededError
from qqbot.model.event import C2CMessageCreate, GroupAtMessageCreate
from qqbot.module.rate_limit import RateLimiter, TokenBucket
from qqbot.options import ClientOptions
from tests.support import TOKEN_PATH, MockServer, add_token_route

DATA = Path(__file__).parent / "data"
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


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


def snapshot_receipt() -> Any:
    from qqbot.model.message import GroupMessageReceipt

    return GroupMessageReceipt.model_validate(snapshot("group_message_receipt.json"))


def test_bucket_allows_capacity_then_blocks(clock: FakeClock) -> None:
    bucket = TokenBucket(3.0, clock=clock)

    assert [bucket.take() for _ in range(3)] == [None, None, None]
    wait = bucket.take()

    assert wait is not None
    # 容量 3/分钟 => 每 20 秒回填一个
    assert wait == pytest.approx(20.0)


def test_bucket_refills_over_time(clock: FakeClock) -> None:
    bucket = TokenBucket(1.0, clock=clock)
    assert bucket.take() is None
    assert bucket.take() is not None

    clock.advance(60.0)

    assert bucket.take() is None


def test_limiter_isolates_keys(clock: FakeClock) -> None:
    limiter = RateLimiter({"group": 1.0}, clock=clock)

    limiter.check("group", "a")

    with pytest.raises(RateLimitExceededError):
        limiter.check("group", "a")
    limiter.check("group", "b")


def test_limiter_ignores_unknown_scope(clock: FakeClock) -> None:
    limiter = RateLimiter(clock=clock)

    for _ in range(50):
        limiter.check("unknown", "a")


def test_limiter_rejects_negative_limit() -> None:
    with pytest.raises(ValueError, match="must not be negative"):
        RateLimiter({"group": -1.0})


async def test_send_hits_local_limit(
    server: MockServer, point_at: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    add_token_route(server)
    json_route(server, "POST", GROUP_PATH, snapshot("group_message_receipt.json"))
    options = ClientOptions(rate_limits={"group": 1.0})
    async with Bot(app_id="app", client_secret="secret", options=options) as bot:
        await bot.api.group.send_message(GROUP, content="one")
        with pytest.raises(RateLimitExceededError) as info:
            await bot.api.group.send_message(GROUP, content="two")

    assert info.value.scope == "group"
    assert info.value.key == GROUP
    assert info.value.retry_after > 0
    # 本地拦截之后请求不应该发出去
    assert len([call for call in server.calls if call.path == GROUP_PATH]) == 1


async def test_respect_rate_limits_off_sends_every_time(server: MockServer, point_at: None) -> None:
    add_token_route(server)
    json_route(server, "POST", C2C_PATH, snapshot("group_message_receipt.json"))
    options = ClientOptions(respect_rate_limits=False, rate_limits={"c2c": 1.0})
    async with Bot(app_id="app", client_secret="secret", options=options) as bot:
        for _ in range(3):
            await bot.api.user_message.send_message(USER, content="hi")

    assert len([call for call in server.calls if call.path == C2C_PATH]) == 3


async def test_server_rate_limit_is_not_swallowed(server: MockServer, point_at: None) -> None:
    add_token_route(server)

    async def handler(request: aiohttp.web.Request) -> aiohttp.web.StreamResponse:
        return aiohttp.web.json_response(
            {"err_code": 40034100, "message": "proactive message rate limited"},
            status=400,
        )

    server.route("POST", GROUP_PATH, handler)
    async with Bot(app_id="app", client_secret="secret") as bot:
        with pytest.raises(APIError) as info:
            await bot.api.group.send_message(GROUP, content="hi")

    assert info.value.code == 40034100


async def test_group_event_blocks_sixth_reply() -> None:
    payload = snapshot("gateway_group_at_message_create.json")
    event = GroupAtMessageCreate.model_validate(payload["d"])
    calls: list[dict[str, Any]] = []

    class Sender:
        async def send_message(self, group_openid: str, **kwargs: Any) -> Any:
            calls.append(kwargs)
            return snapshot_receipt()

    class Api:
        group = Sender()

    event.bind(Api())  # type: ignore[arg-type]

    for _ in range(5):
        await event.reply("hi")

    with pytest.raises(ValueError, match="passive reply limit reached"):
        await event.reply("hi")
    assert len(calls) == 5


async def test_c2c_event_blocks_fifth_reply() -> None:
    event = C2CMessageCreate.model_validate(snapshot("c2c_message_create.json"))
    calls: list[dict[str, Any]] = []

    class Sender:
        async def send_message(self, user_openid: str, **kwargs: Any) -> Any:
            calls.append(kwargs)
            return snapshot_receipt()

    class Api:
        user_message = Sender()

    event.bind(Api())  # type: ignore[arg-type]

    for _ in range(4):
        await event.reply("hi")

    with pytest.raises(ValueError, match="passive reply limit reached"):
        await event.reply("hi")
    assert len(calls) == 4


def test_options_reject_negative_rate_limit() -> None:
    with pytest.raises(ValueError, match="must not be negative"):
        ClientOptions(rate_limits={"group": -0.5})


def test_token_path_constant_is_used() -> None:
    assert TOKEN_PATH == "/app/getAppAccessToken"
