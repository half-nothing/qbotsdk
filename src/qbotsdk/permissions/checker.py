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

"""权限判定。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .grant import Grant
from .node import Permission

if TYPE_CHECKING:
    from .store import PermissionStorage

__all__ = ["PermissionChecker", "account_of", "candidates"]


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
    """构建某个权限键的可匹配的权限列表"""

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
    """查询存储并给出判定。"""

    __slots__ = ("_store",)

    def __init__(self, store: PermissionStorage) -> None:
        self._store = store

    @property
    def store(self) -> PermissionStorage:
        return self._store

    async def allows(self, principal: str, permission: Permission | str) -> bool:
        key = permission.key if isinstance(permission, Permission) else permission
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
