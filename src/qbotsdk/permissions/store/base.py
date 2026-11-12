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

"""权限存储抽象与缓存装饰器。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from time import monotonic
from typing import TYPE_CHECKING, override

from qbotsdk.permissions import Grant, PendingGrant, Role

if TYPE_CHECKING:
    from collections.abc import Callable

__all__ = ["CachedPermissionStorage", "PermissionStorage"]


class PermissionStorage(ABC):
    """授予与角色的存储接口, 全异步, `close()` 默认空实现。

    权限读多写少, 写入集中在管理命令;实现要能容忍并发调用。
    """

    @abstractmethod
    async def grants(self, principal: str) -> frozenset[Grant]:
        """某个主体的直接授予。"""

    @abstractmethod
    async def grant(self, principal: str, grant: Grant) -> None:
        """写入一条授予, 同一权限覆盖旧值。"""

    @abstractmethod
    async def revoke(self, principal: str, permission: str) -> bool:
        """删掉一条授予, 返回是否真的删到了。"""

    @abstractmethod
    async def roles(self, principal: str) -> frozenset[str]:
        """某个主体被分配的角色名。"""

    @abstractmethod
    async def assign(self, principal: str, role: str) -> None:
        """给主体分配角色。"""

    @abstractmethod
    async def unassign(self, principal: str, role: str) -> None:
        """收回主体的角色。"""

    @abstractmethod
    async def role(self, name: str) -> Role | None:
        """按名字取角色定义。"""

    @abstractmethod
    async def save_role(self, role: Role) -> None:
        """写入或覆盖角色定义。"""

    @abstractmethod
    async def delete_role(self, name: str) -> bool:
        """删除角色定义, 返回是否真的删到了。"""

    @abstractmethod
    async def all_roles(self) -> tuple[Role, ...]:
        """全部角色定义, 按名字排序。"""

    @abstractmethod
    async def save_pending(self, code: str, pending: PendingGrant, *, ttl: float) -> None:
        """存一个一次性授权码, `ttl` 秒后失效。"""

    @abstractmethod
    async def pop_pending(self, code: str) -> PendingGrant | None:
        """原子取走授权码, 过期、不存在或已被领走都返回 None。"""

    async def rules(self, principal: str) -> frozenset[Grant]:
        """直接授予 U 角色及其父角色的授予, 环用 visited 集合终止。"""

        rules = set(await self.grants(principal))
        visited: set[str] = set()
        pending = list(await self.roles(principal))
        while pending:
            name = pending.pop()
            if name in visited:
                continue
            visited.add(name)
            role = await self.role(name)
            if role is None:
                continue
            rules.update(role.grants)
            pending.extend(role.parents)
        return frozenset(rules)

    async def close(self) -> None:  # noqa: B027
        """释放资源, 退出前调用;默认什么都不做。"""
        pass


class CachedPermissionStorage(PermissionStorage):
    """给任意实现加一层判定结果缓存, 写入时按主体失效。

    多实例部署时 TTL 就是权限变更的一致窗口。
    """

    __slots__ = ("_clock", "_rules", "_store", "_ttl")

    def __init__(
        self,
        store: PermissionStorage,
        *,
        ttl: float = 30.0,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        if ttl < 0:
            raise ValueError("ttl must not be negative")
        self._store = store
        self._ttl = ttl
        self._clock = clock
        self._rules: dict[str, tuple[float, frozenset[Grant]]] = {}

    @property
    def store(self) -> PermissionStorage:
        """被装饰的存储。"""

        return self._store

    @override
    async def rules(self, principal: str) -> frozenset[Grant]:
        cached = self._rules.get(principal)
        now = self._clock()
        if cached is not None and now - cached[0] < self._ttl:
            return cached[1]
        rules = await self._store.rules(principal)
        self._rules[principal] = (now, rules)
        return rules

    async def grants(self, principal: str) -> frozenset[Grant]:
        return await self._store.grants(principal)

    async def grant(self, principal: str, grant: Grant) -> None:
        await self._store.grant(principal, grant)
        self._rules.pop(principal, None)

    async def revoke(self, principal: str, permission: str) -> bool:
        removed = await self._store.revoke(principal, permission)
        self._rules.pop(principal, None)
        return removed

    async def roles(self, principal: str) -> frozenset[str]:
        return await self._store.roles(principal)

    async def assign(self, principal: str, role: str) -> None:
        await self._store.assign(principal, role)
        self._rules.pop(principal, None)

    async def unassign(self, principal: str, role: str) -> None:
        await self._store.unassign(principal, role)
        self._rules.pop(principal, None)

    async def role(self, name: str) -> Role | None:
        return await self._store.role(name)

    async def save_role(self, role: Role) -> None:
        await self._store.save_role(role)
        self._rules.clear()

    async def delete_role(self, name: str) -> bool:
        removed = await self._store.delete_role(name)
        self._rules.clear()
        return removed

    async def all_roles(self) -> tuple[Role, ...]:
        return await self._store.all_roles()

    async def save_pending(self, code: str, pending: PendingGrant, *, ttl: float) -> None:
        await self._store.save_pending(code, pending, ttl=ttl)

    async def pop_pending(self, code: str) -> PendingGrant | None:
        return await self._store.pop_pending(code)

    @override
    async def close(self) -> None:
        self._rules.clear()
        await self._store.close()
