# Copyright (c) 2026-present Half_nothing.

"""会话存储：内存、文件两种实现的读写与合并策略。"""

from __future__ import annotations

import json
import subprocess
import sys
from collections.abc import AsyncIterator, Callable
from pathlib import Path

import pytest

import qbotsdk.module.http_client
import qbotsdk.module.token_manager
from qbotsdk.adapter import WebSocketAdapter
from qbotsdk.bot import Bot
from qbotsdk.gateway.connection import GatewayConnection
from qbotsdk.model.event import ReadyEvent
from qbotsdk.options import ClientOptions
from qbotsdk.storage import (
    FileSessionStorage,
    MemorySessionStorage,
    SessionData,
)
from tests.support import TOKEN_PATH, FakeGateway

OPTIONS = ClientOptions(backoff_base=0.001, backoff_max=0.01)


async def wait_until(predicate: Callable[[], bool], *, timeout: float = 2.0) -> None:
    import asyncio

    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while loop.time() < deadline:
        if predicate():
            return
        await asyncio.sleep(0.01)
    raise AssertionError("condition was not met in time")


def _fake_http() -> qbotsdk.module.http_client.HTTPClient:
    return qbotsdk.module.http_client.HTTPClient("app", "secret", options=OPTIONS)


class FakeClock:
    """可手动推进的单调时钟。"""

    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def test_storage_package_does_not_import_redis() -> None:
    code = (
        "import sys\nimport qbotsdk.storage  # noqa: F401\nprint('redis.asyncio' in sys.modules)\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        check=True,
    )

    assert result.stdout.strip() == "False"


def test_redis_storage_is_missing_without_extra() -> None:
    code = (
        "import sys\n"
        "sys.modules['redis'] = None\n"
        "sys.modules['redis.asyncio'] = None\n"
        "try:\n"
        "    from qbotsdk.storage import RedisSessionStorage\n"
        "except ImportError as exc:\n"
        "    print('missing', 'qbotsdk[redis]' in str(exc))\n"
        "else:\n"
        "    print('found', RedisSessionStorage.__name__)\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        check=True,
    )

    assert result.stdout.strip() == "missing True"


async def test_memory_storage_roundtrip() -> None:
    storage = MemorySessionStorage()
    assert await storage.load() is None

    await storage.save(SessionData(session_id="session-1", seq=3))
    data = await storage.load()

    assert data is not None
    assert data.session_id == "session-1"
    assert data.seq == 3

    await storage.clear()
    assert await storage.load() is None


async def test_file_storage_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / "session.json"
    await FileSessionStorage(path).save(SessionData(session_id="session-1", seq=42))

    data = await FileSessionStorage(path).load()

    assert data is not None
    assert data.session_id == "session-1"
    assert data.seq == 42
    assert not (tmp_path / "session.json.tmp").exists()


async def test_file_storage_ignores_broken_file(tmp_path: Path) -> None:
    path = tmp_path / "session.json"
    path.write_text("not json", encoding="utf-8")

    assert await FileSessionStorage(path).load() is None


async def test_file_storage_coalesces_seq_updates(tmp_path: Path) -> None:
    path = tmp_path / "session.json"
    clock = FakeClock()
    storage = FileSessionStorage(path, flush_interval=60.0, clock=clock)

    await storage.save(SessionData(session_id="session-1", seq=1))
    assert json.loads(path.read_text(encoding="utf-8"))["seq"] == 1

    await storage.save(SessionData(session_id="session-1", seq=2))
    await storage.save(SessionData(session_id="session-1", seq=3))
    assert json.loads(path.read_text(encoding="utf-8"))["seq"] == 1

    clock.now = 60.0
    await storage.save(SessionData(session_id="session-1", seq=4))
    assert json.loads(path.read_text(encoding="utf-8"))["seq"] == 4
    await storage.close()


async def test_file_storage_flushes_without_new_saves(tmp_path: Path) -> None:
    path = tmp_path / "session.json"
    storage = FileSessionStorage(path, flush_interval=0.02, clock=FakeClock())

    await storage.save(SessionData(session_id="session-1", seq=1))
    await storage.save(SessionData(session_id="session-1", seq=2))
    assert json.loads(path.read_text(encoding="utf-8"))["seq"] == 1

    # 事件停了, 没有新的 save 也要把待写的值补上
    await wait_until(lambda: json.loads(path.read_text(encoding="utf-8"))["seq"] == 2)

    await storage.close()


async def test_file_storage_close_flushes_pending(tmp_path: Path) -> None:
    path = tmp_path / "session.json"
    clock = FakeClock()
    storage = FileSessionStorage(path, flush_interval=60.0, clock=clock)
    await storage.save(SessionData(session_id="session-1", seq=1))

    await storage.save(SessionData(session_id="session-1", seq=2))
    assert json.loads(path.read_text(encoding="utf-8"))["seq"] == 1

    await storage.close()
    assert json.loads(path.read_text(encoding="utf-8"))["seq"] == 2


async def test_file_storage_write_failure_is_not_fatal(tmp_path: Path) -> None:
    path = tmp_path / "blocked" / "session.json"
    path.parent.mkdir()
    path.mkdir()

    await FileSessionStorage(path).save(SessionData(session_id="session-1", seq=1))


async def test_connection_restores_session(tmp_path: Path) -> None:
    path = tmp_path / "session.json"
    await FileSessionStorage(path).save(SessionData(session_id="session-1", seq=9))

    connection = GatewayConnection(
        _fake_http(),
        options=OPTIONS,
        session_storage=FileSessionStorage(path),
    )
    await connection._restore_session()

    assert connection.session.can_resume
    assert connection.session.session_id == "session-1"
    assert connection.session.seq == 9


async def test_connection_drops_invalid_session(tmp_path: Path) -> None:
    path = tmp_path / "session.json"
    await FileSessionStorage(path).save(SessionData(session_id="session-1", seq=9))

    connection = GatewayConnection(
        _fake_http(),
        options=OPTIONS,
        session_storage=FileSessionStorage(path),
    )
    await connection._drop_session()

    assert not connection.session.can_resume
    assert not path.exists()


@pytest.fixture
async def fake_gateway(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[FakeGateway]:
    gw = FakeGateway()
    await gw.start()
    monkeypatch.setattr(qbotsdk.module.token_manager, "TOKEN_URL", f"{gw.url}{TOKEN_PATH}")
    monkeypatch.setattr(qbotsdk.module.http_client, "BASE_URL", gw.url)
    try:
        yield gw
    finally:
        await gw.stop()


async def test_ready_is_persisted(fake_gateway: FakeGateway, tmp_path: Path) -> None:
    import asyncio

    path = tmp_path / "session.json"
    http = _fake_http()
    connection = GatewayConnection(
        http,
        options=OPTIONS,
        session_storage=FileSessionStorage(path),
    )
    task = asyncio.create_task(connection.run())
    try:
        await wait_until(lambda: path.exists() and "xxxxxx" in path.read_text(encoding="utf-8"))
    finally:
        await connection.close()
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        await http.close()

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["session_id"] == "xxxxxx"


async def test_saved_session_is_resumed(fake_gateway: FakeGateway, tmp_path: Path) -> None:
    import asyncio

    path = tmp_path / "session.json"
    path.write_text(
        json.dumps({"session_id": "previous-session", "seq": 11}),
        encoding="utf-8",
    )
    http = _fake_http()
    connection = GatewayConnection(
        http,
        options=OPTIONS,
        session_storage=FileSessionStorage(path),
    )
    task = asyncio.create_task(connection.run())
    try:
        await wait_until(lambda: any(frame["op"] == 6 for frame in fake_gateway.frames))
    finally:
        await connection.close()
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        await http.close()

    resume = next(frame for frame in fake_gateway.frames if frame["op"] == 6)
    assert resume["d"]["session_id"] == "previous-session"
    assert resume["d"]["seq"] == 11
    assert not any(frame["op"] == 2 for frame in fake_gateway.frames)


async def test_adapter_stores_session_in_memory(fake_gateway: FakeGateway) -> None:
    storage = MemorySessionStorage()
    seen: list[str] = []
    bot = Bot(
        "app",
        "secret",
        options=OPTIONS,
        adapter=WebSocketAdapter(session_storage=storage),
    )

    @bot.on(ReadyEvent)
    async def handler(ctx: object) -> None:
        seen.append("ready")

    try:
        await bot.start()
        await wait_until(lambda: seen == ["ready"])
        data = await storage.load()
        assert data is not None
        assert data.session_id == "xxxxxx"
    finally:
        await bot.close()
