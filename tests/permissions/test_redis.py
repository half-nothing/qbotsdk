# Copyright (c) 2026-present Half_nothing.

"""Redis 会话存储的地址拼装与客户端构造（不连真实 Redis）。"""

from __future__ import annotations

import pytest

from qbotsdk.storage import SessionData
from qbotsdk.storage.redis import RedisSessionStorage, _build_url


def _connection_kwargs(storage: RedisSessionStorage) -> dict[str, object]:
    pool = storage.client.connection_pool
    return dict(pool.connection_kwargs)


def test_build_url_without_auth() -> None:
    assert _build_url(
        host="10.0.0.5", port=6379, db=0, username=None, password=None, ssl=False
    ) == ("redis://10.0.0.5:6379/0")


def test_build_url_with_password_only() -> None:
    url = _build_url(
        host="localhost", port=6380, db=3, username=None, password="p@ss/word", ssl=False
    )

    assert url == "redis://:p%40ss%2Fword@localhost:6380/3"


def test_build_url_with_user_and_ssl() -> None:
    url = _build_url(
        host="redis.example.com",
        port=6379,
        db=1,
        username="bot",
        password="secret",
        ssl=True,
    )

    assert url == "rediss://bot:secret@redis.example.com:6379/1"


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"host": ""}, "host must not be empty"),
        ({"port": 0}, "port must be between 1 and 65535"),
        ({"port": 70000}, "port must be between 1 and 65535"),
        ({"db": -1}, "db must not be negative"),
    ],
)
def test_build_url_rejects_bad_parts(kwargs: dict[str, object], message: str) -> None:
    parts: dict[str, object] = {
        "host": "localhost",
        "port": 6379,
        "db": 0,
        "username": None,
        "password": None,
        "ssl": False,
    }
    parts.update(kwargs)

    with pytest.raises(ValueError, match=message):
        _build_url(**parts)  # type: ignore[arg-type]


def test_from_url_builds_client_from_parts() -> None:
    storage = RedisSessionStorage.from_url(host="10.0.0.5", port=6380, password="pwd", db=2)
    kwargs = _connection_kwargs(storage)

    assert kwargs["host"] == "10.0.0.5"
    assert kwargs["port"] == 6380
    assert kwargs["db"] == 2
    assert kwargs["password"] == "pwd"


def test_from_url_prefers_explicit_url() -> None:
    storage = RedisSessionStorage.from_url("redis://example.com:6390/4", host="ignored", port=1)
    kwargs = _connection_kwargs(storage)

    assert kwargs["host"] == "example.com"
    assert kwargs["port"] == 6390
    assert kwargs["db"] == 4


def test_from_url_keeps_key_and_ttl() -> None:
    storage = RedisSessionStorage.from_url("redis://localhost:6379/0", key="custom", ttl=60)

    assert storage._key == "custom"
    assert storage._ttl == 60


def test_from_url_builds_unix_socket_target() -> None:
    storage = RedisSessionStorage.from_url(unix_socket="/var/run/redis/redis.sock", db=2)
    kwargs = _connection_kwargs(storage)

    assert kwargs["path"] == "/var/run/redis/redis.sock"
    assert kwargs["db"] == 2


def test_from_url_unix_socket_with_password() -> None:
    storage = RedisSessionStorage.from_url(unix_socket="/tmp/redis.sock", password="p@ss")
    kwargs = _connection_kwargs(storage)

    assert kwargs["path"] == "/tmp/redis.sock"
    assert kwargs["password"] == "p@ss"


@pytest.mark.parametrize("protocol", [2, 3])
def test_from_url_passes_protocol(protocol: int) -> None:
    storage = RedisSessionStorage.from_url("redis://localhost:6379/0", protocol=protocol)

    assert _connection_kwargs(storage)["protocol"] == protocol


def test_from_url_rejects_unknown_protocol() -> None:
    with pytest.raises(ValueError, match="protocol must be 2 or 3"):
        RedisSessionStorage.from_url("redis://localhost:6379/0", protocol=4)


def test_from_url_rejects_empty_unix_socket() -> None:
    with pytest.raises(ValueError, match="unix_socket must not be empty"):
        RedisSessionStorage.from_url(unix_socket="")


class _StubClient:
    """模拟一个没开 decode_responses 的外部客户端。"""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str, int | None]] = []
        self.closed = False

    async def get(self, key: str) -> bytes:
        self.calls.append(("get", key, None))
        return b'{"session_id": "session-1", "seq": 7}'

    async def set(self, key: str, value: str, *, ex: int | None = None) -> None:
        self.calls.append(("set", key, ex))

    async def delete(self, key: str) -> None:
        self.calls.append(("delete", key, None))

    async def aclose(self) -> None:
        self.closed = True


async def test_external_client_returning_bytes_is_decoded() -> None:
    client = _StubClient()
    storage = RedisSessionStorage(client)  # type: ignore[arg-type]

    data = await storage.load()

    assert data is not None
    assert data.session_id == "session-1"
    assert data.seq == 7


async def test_external_client_roundtrip_uses_ttl_and_close() -> None:
    client = _StubClient()
    storage = RedisSessionStorage(client, key="custom", ttl=30)  # type: ignore[arg-type]

    await storage.save(SessionData(session_id="session-1", seq=1))
    await storage.clear()
    await storage.close()

    assert ("set", "custom", 30) in client.calls
    assert ("delete", "custom", None) in client.calls
    assert client.closed
