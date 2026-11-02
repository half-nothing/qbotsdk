# Copyright (c) 2026-present Half_nothing.

"""权限判定。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .grant import Grant
from .node import Permission

if TYPE_CHECKING:
    from .store.base import PermissionStorage


def account_of(principal: str) -> str | None:
    """从场景主体推出账号级主体, 频道主体没有账号级。"""

    if principal.startswith("c2c:"):
        return f"user:{principal[len('c2c:') :]}"
    if principal.startswith("group:"):
        _, _, openid = principal.partition(":")
        openid = openid.rpartition(":")[2]
        return f"user:{openid}" if openid else None
    return None


def candidates(key: str) -> tuple[str, ...]:
    """server.admin.stop → 自己、server.admin.*、server.*、`*`。"""

    parts = key.split(".")
    if parts[-1] == "*":
        parts = parts[:-1]
    chain = [key]
    for index in range(len(parts) - 1, 0, -1):
        chain.append(".".join(parts[:index]) + ".*")
    if "*" not in chain:
        chain.append("*")
    return tuple(chain)


class PermissionChecker:
    """查询存储并给出判定, 读取规则交给存储实现或缓存层。"""

    __slots__ = ("_store",)

    def __init__(self, store: PermissionStorage) -> None:
        self._store = store

    @property
    def store(self) -> PermissionStorage:
        return self._store

    async def allows(self, principal: str, permission: Permission | str) -> bool:
        key = permission.key if isinstance(permission, Permission) else str(permission)
        if not key:
            raise ValueError("permission must have a key")
        scopes = [principal]
        account = account_of(principal)
        if account is not None and account != principal:
            scopes.append(account)
        for scope in scopes:
            rules = await self._store.rules(scope)
            for candidate in candidates(key):
                if Grant(candidate, allow=False) in rules:
                    return False
                if Grant(candidate) in rules:
                    return True
        return False

    async def rules(self, principal: str) -> frozenset[Grant]:
        return await self._store.rules(principal)
