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

"""Redis 存储, 多实例共享权限, 依赖qbotsdk[redis]。

授予、角色与授权码都以 pydantic 记录为单位整段读写, 不手工拼接分隔符。
"""

from __future__ import annotations

from typing import cast, override

from loguru import logger
from pydantic import ValidationError

from qbotsdk.module import build_redis_unix_url, build_redis_url
from qbotsdk.permissions import Grant, PendingGrant, Role

from .base import PermissionStorage
from .wire import GrantList, PendingRecord, RoleRecord

try:  # pragma: no cover
    from redis.asyncio import Redis
except ImportError as exc:  # pragma: no cover
    raise ImportError(
        "RedisPermissionStorage requires the redis package; "
        "install it with `pip install qbotsdk[redis]`"
    ) from exc

__all__ = ["RedisPermissionStorage"]


class RedisPermissionStorage(PermissionStorage):
    """授予与角色存 Redis, 授权码带 TTL。"""

    __slots__ = ("_client", "_key")

    def __init__(
        self,
        client: Redis,
        *,
        key: str = "qbotsdk:permissions",
    ) -> None:
        """接一个现成的 redis 异步客户端。

        注意这个Redis实例的全限定名是`redis.asyncio.Redis`,
        不要把`redis.Redis`实例传进来

        :param client: Redis 实例。
        :param key:    权限数据的 key 前缀, 同一个前缀的机器人共享权限。
        """

        self._client = client
        self._key = key

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
        key: str = "qbotsdk:permissions",
    ) -> RedisPermissionStorage:
        """建一个Redis权限存储, 传入现成的 URL, 或者给主机、端口、密码、socket 路径这些零件。

        :param url:         完整地址。
        :param host:        主机名或IP。
        :param port:        redis端口号。
        :param db:          数据库编号。
        :param username:    ACL用户名。
        :param password:    访问密码。
        :param ssl:         加密连接redis。
        :param unix_socket: Unix socket 路径。
        :param protocol:    RESP协议版本。
        :param key:         权限数据的 key 前缀。

        :raise ValueError:  db 为负、端口越界、host/unix_socket 为空、protocol 不是 2 或 3

        Examples:
            RedisPermissionStorage.from_url("redis://:pwd@10.0.0.5:6379/2")

            RedisPermissionStorage.from_url(host="10.0.0.5", port=6379, password="pwd", db=2)

            RedisPermissionStorage.from_url(unix_socket="/var/run/redis/redis.sock", db=2)

            RedisPermissionStorage.from_url(host="10.0.0.5", protocol=3)
        """
        if protocol is not None and protocol not in (2, 3):
            raise ValueError("protocol must be 2 or 3")

        if url is not None:
            target = url
        elif unix_socket is not None:
            target = build_redis_unix_url(
                unix_socket=unix_socket,
                db=db,
                username=username,
                password=password,
            )
        else:
            target = build_redis_url(
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
        return cls(client, key=key)

    def _grants_key(self, principal: str) -> str:
        return f"{self._key}:grants:{principal}"

    def _assigned_key(self, principal: str) -> str:
        return f"{self._key}:assigned:{principal}"

    def _roles_key(self) -> str:
        return f"{self._key}:roles"

    def _pending_key(self, code: str) -> str:
        return f"{self._key}:pending:{code}"

    async def grants(self, principal: str) -> frozenset[Grant]:
        raw = await self._client.get(self._grants_key(principal))
        if not raw:
            return frozenset()
        try:
            return frozenset(GrantList.model_validate_json(self._text(raw)).root)
        except ValidationError:
            logger.warning("permission grants for {!r} are not valid, ignoring", principal)
            return frozenset()

    async def grant(self, principal: str, grant: Grant) -> None:
        current = {item.permission: item for item in await self.grants(principal)}
        current[grant.permission] = grant
        await self._store_grants(principal, current)

    async def revoke(self, principal: str, permission: str) -> bool:
        current = {item.permission: item for item in await self.grants(principal)}
        if permission not in current:
            return False
        del current[permission]
        await self._store_grants(principal, current)
        return True

    async def _store_grants(self, principal: str, grants: dict[str, Grant]) -> None:
        key = self._grants_key(principal)
        if not grants:
            await self._client.delete(key)
            return
        payload = GrantList(
            tuple(grants[name] for name in sorted(grants)),
        ).model_dump_json()
        await self._client.set(key, payload)

    async def roles(self, principal: str) -> frozenset[str]:
        names = await self._client.smembers(self._assigned_key(principal))
        return frozenset(self._text(name) for name in names)

    async def assign(self, principal: str, role: str) -> None:
        await self._client.sadd(self._assigned_key(principal), role)

    async def unassign(self, principal: str, role: str) -> None:
        await self._client.srem(self._assigned_key(principal), role)

    async def role(self, name: str) -> Role | None:
        raw = await self._client.hget(self._roles_key(), name)
        if raw is None:
            return None
        return self._decode_role(name, self._text(raw))

    async def save_role(self, role: Role) -> None:
        payload = RoleRecord.of(role).model_dump_json()
        await self._client.hset(self._roles_key(), role.name, payload)

    async def delete_role(self, name: str) -> bool:
        return bool(await self._client.hdel(self._roles_key(), name))

    async def all_roles(self) -> tuple[Role, ...]:
        raw = await self._client.hgetall(self._roles_key())
        roles = []
        for name in sorted(raw):
            role = self._decode_role(self._text(name), self._text(raw[name]))
            if role is not None:
                roles.append(role)
        return tuple(roles)

    async def save_pending(self, code: str, pending: PendingGrant, *, ttl: float) -> None:
        if ttl <= 0:
            raise ValueError("ttl must be positive")
        payload = PendingRecord.of(pending).model_dump_json()
        await self._client.set(self._pending_key(code), payload, ex=max(1, int(ttl)))

    async def pop_pending(self, code: str) -> PendingGrant | None:
        key = self._pending_key(code)
        pipeline = self._client.pipeline()
        await pipeline.get(key)
        await pipeline.delete(key)
        values = await pipeline.execute()
        raw = values[0]
        if raw is None:
            return None
        try:
            return PendingRecord.model_validate_json(self._text(raw)).to_pending()
        except ValidationError:
            logger.warning("pending grant {!r} is not valid, ignoring", code)
            return None

    @override
    async def close(self) -> None:
        await self._client.aclose()

    @staticmethod
    def _text(value: object) -> str:
        """把外部客户端可能返回的字节串归一成文本。"""

        if isinstance(value, (bytes, bytearray, memoryview)):
            return bytes(value).decode()
        return cast("str", value)

    @staticmethod
    def _decode_role(name: str, raw: str) -> Role | None:
        try:
            return RoleRecord.model_validate_json(raw).to_role()
        except ValidationError:
            logger.warning("role {!r} is not valid, ignoring", name)
            return None
