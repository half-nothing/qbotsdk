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

"""Redis 存储。"""

from __future__ import annotations

from typing import TYPE_CHECKING, override
from urllib.parse import quote

from loguru import logger

from .base import SessionData, SessionStorage

if TYPE_CHECKING:
    from redis.asyncio import Redis

_MISSING_HINT = (
    "RedisSessionStorage needs the redis package, install it with `pip install qbotsdk[redis]`"
)

try:
    from redis.asyncio import Redis
except ImportError as exc:
    raise ImportError(_MISSING_HINT) from exc

__all__ = ["RedisSessionStorage"]


def _auth_prefix(username: str | None, password: str | None) -> str:
    """拼认证前缀, {username}:{password}@, 两项都没给时返回空串。"""

    if username is None and password is None:
        return ""
    user = quote(username, safe="") if username is not None else ""
    secret = quote(password, safe="") if password is not None else ""
    return f"{user}:{secret}@"


def _build_url(
    *,
    host: str,
    port: int,
    db: int,
    username: str | None,
    password: str | None,
    ssl: bool,
) -> str:
    """把主机、端口、账号密码拼成 redis 地址。"""

    if not host:
        raise ValueError("host must not be empty")
    if not 0 < port < 65536:
        raise ValueError("port must be between 1 and 65535")
    if db < 0:
        raise ValueError("db must not be negative")

    scheme = "rediss" if ssl else "redis"
    return f"{scheme}://{_auth_prefix(username, password)}{host}:{port}/{db}"


def _build_unix_url(
    *,
    unix_socket: str,
    db: int,
    username: str | None,
    password: str | None,
) -> str:
    """拼 unix socket 地址。"""

    if not unix_socket:
        raise ValueError("unix_socket must not be empty")
    if db < 0:
        raise ValueError("db must not be negative")

    # 路径里的斜杠是分隔符, 不能整体转义
    # db只能通过查询参数指定
    return f"unix://{_auth_prefix(username, password)}{unix_socket}?db={db}"


class RedisSessionStorage(SessionStorage):
    """把会话存在Redis里。"""

    __slots__ = ("_client", "_key", "_ttl")

    def __init__(
        self,
        client: Redis,
        *,
        key: str = "qbotsdk:session",
        ttl: int | None = None,
    ) -> None:
        """接一个现成的 redis 异步客户端。

        注意这个Redis实例的全限定名是`redis.asyncio.Redis`,
        不要把`redis.Redis`实例传进来

        :param client: Redis 实例。
        :param key:    存会话的 key, 同一个 key 的机器人共享会话。
        :param ttl:    key 的过期秒数, 不传则不过期。
        """

        self._client = client
        self._key = key
        self._ttl = ttl

    @property
    def client(self) -> Redis:
        """底层的 redis 异步客户端。"""

        return self._client

    @classmethod
    def from_url(
        cls,
        url: str | None = None,
        *,
        host: str = "localhost",
        port: int = 6379,
        db: int = 0,
        username: str | None = None,
        password: str | None = None,
        ssl: bool = False,
        unix_socket: str | None = None,
        protocol: int | None = None,
        key: str = "qbotsdk:session",
        ttl: int | None = None,
    ) -> RedisSessionStorage:
        """建一个Redis存储, 传入现成的 URL, 或者给主机、端口、密码、socket 路径这些零件。

        :param url:         完整地址。
        :param host:        主机名或IP。
        :param port:        redis端口号。
        :param db:          数据库编号。
        :param username:    ACL用户名。
        :param password:    访问密码。
        :param ssl:         加密连接redis。
        :param unix_socket: Unix socket 路径。
        :param protocol:    RESP协议版本。
        :param key:         存会话的 key。
        :param ttl:         key 的过期秒数, 不传则不过期。

        :raise ValueError:  db 为负、端口越界、host/unix_socket 为空、protocol 不是 2 或 3

        Examples:
            RedisSessionStorage.from_url("redis://:pwd@10.0.0.5:6379/2")

            RedisSessionStorage.from_url(host="10.0.0.5", port=6379, password="pwd", db=2)

            RedisSessionStorage.from_url(unix_socket="/var/run/redis/redis.sock", db=2)

            RedisSessionStorage.from_url(host="10.0.0.5", protocol=3)
        """
        if protocol is not None and protocol not in (2, 3):
            raise ValueError("protocol must be 2 or 3")

        if url is not None:
            target = url
        elif unix_socket is not None:
            target = _build_unix_url(
                unix_socket=unix_socket,
                db=db,
                username=username,
                password=password,
            )
        else:
            target = _build_url(
                host=host,
                port=port,
                db=db,
                username=username,
                password=password,
                ssl=ssl,
            )

        if protocol is None:
            client = Redis.from_url(target, decode_responses=True)
        else:
            client = Redis.from_url(target, decode_responses=True, protocol=protocol)
        return cls(client, key=key, ttl=ttl)

    async def load(self) -> SessionData | None:
        raw = await self._client.get(self._key)
        if raw is None:
            return None

        # 调用方可能自己传了没开 decode_responses 的客户端
        text = raw.decode() if isinstance(raw, (bytes, bytearray, memoryview)) else raw

        try:
            return SessionData.model_validate_json(text)
        except ValueError:
            logger.warning("Ignoring unreadable session in redis key {}", self._key)
            return None

    async def save(self, data: SessionData) -> None:
        payload = data.model_dump_json(by_alias=True)
        if self._ttl is None:
            await self._client.set(self._key, payload)
        else:
            await self._client.set(self._key, payload, ex=self._ttl)

    async def clear(self) -> None:
        await self._client.delete(self._key)

    @override
    async def close(self) -> None:
        await self._client.aclose()
