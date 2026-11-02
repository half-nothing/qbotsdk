# Copyright (c) 2026-present Half_nothing.

"""Redis 存储, 多实例共享权限, 依赖qbotsdk[redis]。

授予、角色与授权码都以 pydantic 记录为单位整段读写, 不手工拼接分隔符。
"""

from __future__ import annotations

from loguru import logger
from pydantic import ValidationError

from qbotsdk.permissions.grant import Grant, PendingGrant, Role

from .base import PermissionStorage
from .wire import GrantList, PendingRecord, RoleRecord

try:  # pragma: no cover
    from redis.asyncio import Redis
except ImportError as exc:  # pragma: no cover
    raise ImportError(
        "RedisPermissionStorage requires the redis package; "
        "install it with `pip install qbotsdk[redis]`"
    ) from exc


def _build_url(
    *,
    host: str,
    port: int,
    db: int,
    username: str | None,
    password: str | None,
    ssl: bool,
    unix_socket: str | None,
    protocol: int | None,
) -> str:
    scheme = "rediss" if ssl else "redis"
    query = f"?protocol={protocol}" if protocol is not None else ""
    if unix_socket:
        return f"{scheme}+unix://{unix_socket}{query}"
    auth = ""
    if username and password:
        auth = f"{username}:{password}@"
    elif password:
        auth = f":{password}@"
    return f"{scheme}://{auth}{host}:{port}/{db}{query}"


class RedisPermissionStorage(PermissionStorage):
    """授予与角色存 Redis, 授权码带 TTL。"""

    __slots__ = ("_client", "_key")

    def __init__(
        self,
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
    ) -> None:
        if not url:
            url = _build_url(
                host=host,
                port=port,
                db=db,
                username=username,
                password=password,
                ssl=ssl,
                unix_socket=unix_socket,
                protocol=protocol,
            )
        self._client: Redis = Redis.from_url(url, decode_responses=True)
        self._key = key

    def _grants_key(self, principal: str) -> str:
        return f"{self._key}:grants:{principal}"

    def _assigned_key(self, principal: str) -> str:
        return f"{self._key}:assigned:{principal}"

    def _roles_key(self) -> str:
        return f"{self._key}:roles"

    def _pending_key(self, code: str) -> str:
        return f"{self._key}:pending:{code}"

    async def grants(self, principal: str) -> frozenset[Grant]:
        raw: str | None = await self._client.get(self._grants_key(principal))  # type: ignore[assignment]
        if not raw:
            return frozenset()
        try:
            return frozenset(GrantList.model_validate_json(raw).root)
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
        names: set[str] = await self._client.smembers(self._assigned_key(principal))  # type: ignore[assignment]
        return frozenset(names)

    async def assign(self, principal: str, role: str) -> None:
        await self._client.sadd(self._assigned_key(principal), role)

    async def unassign(self, principal: str, role: str) -> None:
        await self._client.srem(self._assigned_key(principal), role)

    async def role(self, name: str) -> Role | None:
        raw: str | None = await self._client.hget(self._roles_key(), name)  # type: ignore[assignment]
        if raw is None:
            return None
        return self._decode_role(name, raw)

    async def save_role(self, role: Role) -> None:
        payload = RoleRecord.of(role).model_dump_json()
        await self._client.hset(self._roles_key(), role.name, payload)

    async def delete_role(self, name: str) -> bool:
        return bool(await self._client.hdel(self._roles_key(), name))

    async def all_roles(self) -> tuple[Role, ...]:
        raw: dict[str, str] = await self._client.hgetall(self._roles_key())  # type: ignore[assignment]
        roles = []
        for name in sorted(raw):
            role = self._decode_role(name, raw[name])
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
            return PendingRecord.model_validate_json(raw).to_pending()
        except ValidationError:
            logger.warning("pending grant {!r} is not valid, ignoring", code)
            return None

    async def close(self) -> None:
        await self._client.aclose()

    @staticmethod
    def _decode_role(name: str, raw: str) -> Role | None:
        try:
            return RoleRecord.model_validate_json(raw).to_role()
        except ValidationError:
            logger.warning("role {!r} is not valid, ignoring", name)
            return None
