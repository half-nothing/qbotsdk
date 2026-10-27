# Copyright (c) 2026-present Half_nothing.

"""Redis 存储。"""

from __future__ import annotations

from typing import TYPE_CHECKING
from urllib.parse import quote

from loguru import logger

from .base import SessionData, SessionStorage

if TYPE_CHECKING:
    from redis.asyncio import Redis

_MISSING_HINT = (
    "RedisSessionStorage needs the redis package, install it with `pip install qbotsdk[redis]`"
)

try:
    from redis.asyncio import Redis as _Redis  # noqa: F401
except ImportError as exc:
    raise ImportError(_MISSING_HINT) from exc


def _auth_prefix(username: str | None, password: str | None) -> str:
    """拼 user:password@ 前缀, 两项都没给时返回空串。"""

    if username is None and password is None:
        return ""
    user = quote(username, safe="") if username is not None else ""
    secret = quote(password, safe="") if password is not None else ""
    return f"{user}:{secret}@"


def _check_db(db: int) -> None:
    if db < 0:
        raise ValueError("db must not be negative")


def _check_protocol(protocol: int | None) -> None:
    if protocol is not None and protocol not in (2, 3):
        raise ValueError("protocol must be 2 or 3")


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
    _check_db(db)

    scheme = "rediss" if ssl else "redis"
    return f"{scheme}://{_auth_prefix(username, password)}{host}:{port}/{db}"


def _build_unix_url(
    *,
    unix_socket: str,
    db: int,
    username: str | None,
    password: str | None,
) -> str:
    """拼 unix socket 地址, 形如 unix://:pwd@/var/run/redis.sock?db=2。"""

    if not unix_socket:
        raise ValueError("unix_socket must not be empty")
    _check_db(db)

    # 路径里的斜杠是分隔符, 不能整体转义；只把查询串里的 db 拼上
    return f"unix://{_auth_prefix(username, password)}{unix_socket}?db={db}"


class RedisSessionStorage(SessionStorage):
    """把会话存在一个 Redis key 里。"""

    __slots__ = ("_client", "_key", "_ttl")

    def __init__(
        self,
        client: Redis,
        *,
        key: str = "qbotsdk:session",
        ttl: int | None = None,
    ) -> None:
        """接一个现成的 redis 异步客户端。

        注意这个Redis实例的全限定名是`redis.asyncio.Redis`
        不要把`redis.Redis`实例传进来

        Args:
            client: Redis 实例。
            key:    存会话的 key，同一个 key 的机器人共享会话。
            ttl:    key 的过期秒数，不传则不过期。
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
        """建一个Redis存储，给现成的 URL, 或者给主机、端口、密码、socket 路径这些零件。

        Args:
            url:         完整地址，给了就以它为准，下面的零件参数全部忽略。
            host:        主机名或 IP，`url` 与 `unix_socket` 都没给时生效。
            port:        端口，默认 6379。
            db:          数据库编号，默认 0。
            username:    ACL 用户名，不传用默认用户。
            password:    密码，会做 URL 转义，含 `@`、`/`、`:` 也不用自己处理。
            ssl:         用 `rediss://` 而不是 `redis://`。
            unix_socket: Unix domain socket 路径，给了就忽略 `host`/`port`/`ssl`。
            protocol:    RESP 协议版本，只收 2 或 3，不传用 redis-py 的默认值。
            key:         存会话的 key。
            ttl:         key 的过期秒数，不传则不过期。

        Raises:
            ValueError:
                - db 为负、端口越界
                - host/unix_socket 为空
                - protocol 不是 2 或 3

        Examples:
            RedisSessionStorage.from_url("redis://:pwd@10.0.0.5:6379/2")

            RedisSessionStorage.from_url(host="10.0.0.5", port=6379, password="pwd", db=2)

            RedisSessionStorage.from_url(unix_socket="/var/run/redis/redis.sock", db=2)

            RedisSessionStorage.from_url(host="10.0.0.5", protocol=3)
        """

        from redis.asyncio import Redis

        _check_protocol(protocol)

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
        text = bytes(raw).decode() if isinstance(raw, (bytes, bytearray, memoryview)) else raw

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

    async def close(self) -> None:
        await self._client.aclose()
