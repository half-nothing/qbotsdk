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

"""进程内存储, 零依赖, 进程重启即丢。"""

from __future__ import annotations

from time import monotonic
from typing import TYPE_CHECKING

from qbotsdk.permissions import Grant, PendingGrant, Role

from .base import PermissionStorage

if TYPE_CHECKING:
    from collections.abc import Callable

__all__ = ["MemoryPermissionStorage"]


class MemoryPermissionStorage(PermissionStorage):
    """内存实现, 适合单进程与测试。"""

    __slots__ = ("_assigned", "_clock", "_grants", "_pending", "_roles")

    def __init__(self, *, clock: Callable[[], float] = monotonic) -> None:
        self._clock = clock
        self._grants: dict[str, dict[str, Grant]] = {}
        self._assigned: dict[str, set[str]] = {}
        self._roles: dict[str, Role] = {}
        self._pending: dict[str, tuple[PendingGrant, float]] = {}

    async def grants(self, principal: str) -> frozenset[Grant]:
        return frozenset(self._grants.get(principal, {}).values())

    async def grant(self, principal: str, grant: Grant) -> None:
        self._grants.setdefault(principal, {})[grant.permission] = grant

    async def revoke(self, principal: str, permission: str) -> bool:
        bucket = self._grants.get(principal)
        if bucket is None or permission not in bucket:
            return False
        del bucket[permission]
        if not bucket:
            del self._grants[principal]
        return True

    async def roles(self, principal: str) -> frozenset[str]:
        return frozenset(self._assigned.get(principal, ()))

    async def assign(self, principal: str, role: str) -> None:
        self._assigned.setdefault(principal, set()).add(role)

    async def unassign(self, principal: str, role: str) -> None:
        bucket = self._assigned.get(principal)
        if bucket is not None:
            bucket.discard(role)
            if not bucket:
                del self._assigned[principal]

    async def role(self, name: str) -> Role | None:
        return self._roles.get(name)

    async def save_role(self, role: Role) -> None:
        self._roles[role.name] = role

    async def delete_role(self, name: str) -> bool:
        return self._roles.pop(name, None) is not None

    async def all_roles(self) -> tuple[Role, ...]:
        return tuple(self._roles[name] for name in sorted(self._roles))

    async def save_pending(self, code: str, pending: PendingGrant, *, ttl: float) -> None:
        if ttl <= 0:
            raise ValueError("ttl must be positive")
        self._pending[code] = (pending, self._clock() + ttl)

    async def pop_pending(self, code: str) -> PendingGrant | None:
        entry = self._pending.pop(code, None)
        if entry is None:
            return None
        pending, expires_at = entry
        if expires_at <= self._clock():
            return None
        return pending
