# Copyright (c) 2026-present Half_nothing.

"""网关连接层: 握手、心跳、重连与 Resume, 全部打本地假网关。"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncIterator, Callable

import pytest

import qbotsdk.module.http_client
import qbotsdk.module.token_manager
from qbotsdk.gateway.connection import GatewayConnection
from qbotsdk.gateway.payload import GatewayError, Intents
from qbotsdk.module.http_client import HttpClient
from qbotsdk.options import ClientOptions
from tests.support import TOKEN_PATH, FakeGateway, load_frame

pytestmark = pytest.mark.usefixtures("gateway")

OPTIONS = ClientOptions(backoff_base=0.001, backoff_max=0.01)


@pytest.fixture
async def gateway(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[FakeGateway]:
    gw = FakeGateway()
    await gw.start()
    monkeypatch.setattr(qbotsdk.module.token_manager, "TOKEN_URL", f"{gw.url}{TOKEN_PATH}")
    monkeypatch.setattr(qbotsdk.module.http_client, "BASE_URL", gw.url)
    try:
        yield gw
    finally:
        await gw.stop()


@pytest.fixture
async def client() -> AsyncIterator[HttpClient]:
    http = HttpClient("app", "secret", options=OPTIONS)
    try:
        yield http
    finally:
        await http.close()


async def wait_until(predicate: Callable[[], bool], *, timeout: float = 2.0) -> None:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while loop.time() < deadline:
        if predicate():
            return
        await asyncio.sleep(0.005)
    raise AssertionError("condition was not met in time")


async def run_connection(client: HttpClient) -> tuple[GatewayConnection, asyncio.Task[None]]:
    conn = GatewayConnection(client, options=OPTIONS)
    task = asyncio.create_task(conn.run())
    return conn, task


async def stop_connection(conn: GatewayConnection, task: asyncio.Task[None]) -> None:
    await conn.close()
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task


async def test_identify_after_hello(gateway: FakeGateway, client: HttpClient) -> None:
    conn, task = await run_connection(client)
    try:
        await wait_until(lambda: not conn.events.empty())
        payload = conn.events.get_nowait()
        assert payload.t == "READY"
        assert conn.session.session_id == "xxxxxx"
        assert conn.session.seq == 1

        identify = gateway.frames[0]
        assert identify["op"] == 2
        data = identify["d"]
        assert data["token"] == "QQBot test-token"
        assert data["intents"] == Intents.DEFAULT
        assert data["shard"] == [0, 1]
        assert set(data["properties"]) == {"$os", "$browser", "$device"}
    finally:
        await stop_connection(conn, task)


async def test_heartbeat_carries_latest_seq(gateway: FakeGateway, client: HttpClient) -> None:
    conn, task = await run_connection(client)
    try:
        await wait_until(lambda: sum(1 for f in gateway.frames if f["op"] == 1) >= 2)
        beats = [f for f in gateway.frames if f["op"] == 1]
        # READY 之后 seq 是 1, 心跳必须带它
        assert all(beat["d"] == 1 for beat in beats)
    finally:
        await stop_connection(conn, task)


async def test_missing_ack_reconnects(gateway: FakeGateway, client: HttpClient) -> None:
    gateway.ack_heartbeat = False
    conn, task = await run_connection(client)
    try:
        await wait_until(lambda: gateway.connections >= 2, timeout=3.0)
        beats = [f for f in gateway.frames if f["op"] == 1]
        assert len(beats) >= 2
    finally:
        await stop_connection(conn, task)


async def test_close_timeout_does_not_stall_reconnect(
    gateway: FakeGateway, client: HttpClient
) -> None:
    # 对端握手后就不读帧了, 永远不会回 CLOSE 帧, 关闭握手只能靠超时收场
    gateway.silent = True
    options = ClientOptions(backoff_base=0.001, backoff_max=0.01, timeout_ws_close=0.2)
    conn = GatewayConnection(client, options=options)
    task = asyncio.create_task(conn.run())
    try:
        await wait_until(lambda: gateway.connections >= 2, timeout=3.0)
    finally:
        await stop_connection(conn, task)


async def test_resume_after_expired_session(gateway: FakeGateway, client: HttpClient) -> None:
    gateway.close_after_ready = 4009
    conn, task = await run_connection(client)
    try:
        await wait_until(lambda: any(f["op"] == 6 for f in gateway.frames), timeout=3.0)
        resume = next(f for f in gateway.frames if f["op"] == 6)
        data = resume["d"]
        assert data["session_id"] == "xxxxxx"
        assert data["seq"] == 1
        assert data["token"] == "QQBot test-token"
    finally:
        await stop_connection(conn, task)


async def test_fatal_close_code_stops(gateway: FakeGateway, client: HttpClient) -> None:
    gateway.close_after_ready = 4014
    conn = GatewayConnection(client, options=OPTIONS)
    with pytest.raises(GatewayError):
        await asyncio.wait_for(conn.run(), timeout=3.0)
    assert gateway.connections == 1


async def test_replayed_frames_do_not_rewind_the_sequence(client: HttpClient) -> None:
    conn = GatewayConnection(client, options=OPTIONS)
    conn.session.update(session_id="sid", seq=10)
    frame = load_frame("gateway_group_at_message_create.json")

    await conn._handle(frame.model_copy(update={"s": 3}))  # Resume 补发的旧帧
    assert conn.session.seq == 10

    await conn._handle(frame.model_copy(update={"s": 11}))
    assert conn.session.seq == 11
