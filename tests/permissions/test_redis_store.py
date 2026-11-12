# Copyright (c) 2026-present Half_nothing.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Redis 权限存储的地址拼装与客户端构造(不连真实 Redis)。"""

from __future__ import annotations

import pytest

from qbotsdk.permissions import Grant, Role
from qbotsdk.permissions.store.redis import RedisPermissionStorage


def _connection_kwargs(storage: RedisPermissionStorage) -> dict[str, object]:
    pool = storage.client.connection_pool
    return dict(pool.connection_kwargs)


def test_from_url_builds_client_from_parts() -> None:
    storage = RedisPermissionStorage.from_url(host="10.0.0.5", port=6380, password="pwd", db=2)
    kwargs = _connection_kwargs(storage)

    assert kwargs["host"] == "10.0.0.5"
    assert kwargs["port"] == 6380
    assert kwargs["db"] == 2
    assert kwargs["password"] == "pwd"


def test_from_url_prefers_explicit_url() -> None:
    storage = RedisPermissionStorage.from_url("redis://example.com:6390/4", host="ignored", port=1)
    kwargs = _connection_kwargs(storage)

    assert kwargs["host"] == "example.com"
    assert kwargs["port"] == 6390
    assert kwargs["db"] == 4


def test_from_url_builds_unix_socket_target() -> None:
    storage = RedisPermissionStorage.from_url(unix_socket="/var/run/redis/redis.sock", db=2)
    kwargs = _connection_kwargs(storage)

    assert kwargs["path"] == "/var/run/redis/redis.sock"
    assert kwargs["db"] == 2


def test_from_url_unix_socket_with_password() -> None:
    storage = RedisPermissionStorage.from_url(unix_socket="/tmp/redis.sock", password="p@ss")
    kwargs = _connection_kwargs(storage)

    assert kwargs["path"] == "/tmp/redis.sock"
    assert kwargs["password"] == "p@ss"


@pytest.mark.parametrize("protocol", [2, 3])
def test_from_url_passes_protocol(protocol: int) -> None:
    storage = RedisPermissionStorage.from_url("redis://localhost:6379/0", protocol=protocol)

    assert _connection_kwargs(storage)["protocol"] == protocol


def test_from_url_rejects_unknown_protocol() -> None:
    with pytest.raises(ValueError, match="protocol must be 2 or 3"):
        RedisPermissionStorage.from_url("redis://localhost:6379/0", protocol=4)


def test_from_url_rejects_empty_unix_socket() -> None:
    with pytest.raises(ValueError, match="unix_socket must not be empty"):
        RedisPermissionStorage.from_url(unix_socket="")


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"host": ""}, "host must not be empty"),
        ({"port": 0}, "port must be between 1 and 65535"),
        ({"db": -1}, "db must not be negative"),
    ],
)
def test_from_url_rejects_bad_parts(kwargs: dict[str, object], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        RedisPermissionStorage.from_url(**kwargs)  # type: ignore[arg-type]


def test_key_defaults_to_permissions() -> None:
    storage = RedisPermissionStorage.from_url("redis://localhost:6379/0")

    assert storage._key == "qbotsdk:permissions"


def test_from_url_keeps_custom_key() -> None:
    storage = RedisPermissionStorage.from_url("redis://localhost:6379/0", key="custom")

    assert storage._key == "custom"


class _StubClient:
    """模拟一个没开 decode_responses 的外部客户端。"""

    async def get(self, key: str) -> bytes:
        return b'["read"]'

    async def smembers(self, key: str) -> set[bytes]:
        return {b"admin"}

    async def hget(self, key: str, name: str) -> bytes:
        return b'{"name": "admin", "grants": ["read"], "parents": []}'

    async def hgetall(self, key: str) -> dict[bytes, bytes]:
        return {b"admin": b'{"name": "admin", "grants": ["read"], "parents": []}'}

    async def aclose(self) -> None:
        return None


async def test_external_client_returning_bytes_is_decoded() -> None:
    storage = RedisPermissionStorage(_StubClient())  # type: ignore[arg-type]

    assert await storage.grants("user-1") == frozenset({Grant("read")})
    assert await storage.roles("user-1") == frozenset({"admin"})
    assert await storage.role("admin") == Role("admin", grants=(Grant("read"),))
    assert await storage.all_roles() == (Role("admin", grants=(Grant("read"),)),)
