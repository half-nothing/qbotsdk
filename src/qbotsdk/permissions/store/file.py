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

"""单文件 JSON 存储。"""

from __future__ import annotations

from asyncio import Lock, to_thread
from contextlib import suppress
from os import fdopen, fsync, replace, unlink
from pathlib import Path
from tempfile import mkstemp
from time import monotonic
from typing import TYPE_CHECKING

from loguru import logger
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from qbotsdk.permissions import Grant, PendingGrant, Role

from .base import PermissionStorage
from .wire import GrantField

if TYPE_CHECKING:
    from collections.abc import Callable

__all__ = ["FilePermissionStorage"]

_VERSION = 1


class _RoleData(BaseModel):
    """文件里的角色条目。"""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    grants: tuple[GrantField, ...] = ()
    parents: tuple[str, ...] = ()


class _FileData(BaseModel):
    """存储文件的结构。"""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    version: int = _VERSION
    grants: dict[str, tuple[GrantField, ...]] = Field(default_factory=dict)
    roles: dict[str, _RoleData] = Field(default_factory=dict)
    assigned: dict[str, tuple[str, ...]] = Field(default_factory=dict)


class FilePermissionStorage(PermissionStorage):
    """把授予与角色写进一个 JSON 文件。"""

    __slots__ = (
        "_assigned",
        "_clock",
        "_grants",
        "_loaded",
        "_lock",
        "_path",
        "_pending",
        "_roles",
    )

    def __init__(self, path: str | Path, *, clock: Callable[[], float] = monotonic) -> None:
        if not str(path):
            raise ValueError("path must not be empty")
        self._path = Path(path)
        self._clock = clock
        self._lock = Lock()
        self._loaded = False
        self._grants: dict[str, dict[str, Grant]] = {}
        self._assigned: dict[str, set[str]] = {}
        self._roles: dict[str, Role] = {}
        self._pending: dict[str, tuple[PendingGrant, float]] = {}

    def _read(self) -> _FileData:
        try:
            text = self._path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return _FileData()
        try:
            return _FileData.model_validate_json(text)
        except ValidationError:
            logger.warning("permission file {!r} is not valid, starting empty", str(self._path))
            return _FileData()

    def _write(self, data: _FileData) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        text = data.model_dump_json(ensure_ascii=False, exclude_none=False)
        handle, temp = mkstemp(dir=str(self._path.parent), suffix=".tmp")
        try:
            with fdopen(handle, "w", encoding="utf-8") as file:
                file.write(text)
                file.flush()
                fsync(file.fileno())
            replace(temp, self._path)
        except BaseException:
            with suppress(OSError):
                unlink(temp)
            raise

    async def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        async with self._lock:
            if self._loaded:
                return
            data = await to_thread(self._read)
            self._grants = {
                principal: {grant.permission: grant for grant in grants}
                for principal, grants in data.grants.items()
            }
            self._roles = {
                name: Role(name, grants=tuple(entry.grants), parents=tuple(entry.parents))
                for name, entry in data.roles.items()
            }
            self._assigned = {principal: set(names) for principal, names in data.assigned.items()}
            self._loaded = True

    async def _flush(self) -> None:
        data = _FileData(
            version=_VERSION,
            grants={
                principal: tuple(grants.values())
                for principal, grants in sorted(self._grants.items())
            },
            roles={
                name: _RoleData(grants=tuple(role.grants), parents=tuple(role.parents))
                for name, role in sorted(self._roles.items())
            },
            assigned={
                principal: tuple(sorted(names))
                for principal, names in sorted(self._assigned.items())
            },
        )
        await to_thread(self._write, data)

    async def _mutate(self) -> None:
        async with self._lock:
            await self._ensure_loaded()
            await self._flush()

    async def grants(self, principal: str) -> frozenset[Grant]:
        await self._ensure_loaded()
        return frozenset(self._grants.get(principal, {}).values())

    async def grant(self, principal: str, grant: Grant) -> None:
        await self._ensure_loaded()
        self._grants.setdefault(principal, {})[grant.permission] = grant
        await self._mutate()

    async def revoke(self, principal: str, permission: str) -> bool:
        await self._ensure_loaded()
        bucket = self._grants.get(principal)
        if bucket is None or permission not in bucket:
            return False
        del bucket[permission]
        if not bucket:
            del self._grants[principal]
        await self._mutate()
        return True

    async def roles(self, principal: str) -> frozenset[str]:
        await self._ensure_loaded()
        return frozenset(self._assigned.get(principal, ()))

    async def assign(self, principal: str, role: str) -> None:
        await self._ensure_loaded()
        self._assigned.setdefault(principal, set()).add(role)
        await self._mutate()

    async def unassign(self, principal: str, role: str) -> None:
        await self._ensure_loaded()
        bucket = self._assigned.get(principal)
        if bucket is None or role not in bucket:
            return
        bucket.discard(role)
        if not bucket:
            del self._assigned[principal]
        await self._mutate()

    async def role(self, name: str) -> Role | None:
        await self._ensure_loaded()
        return self._roles.get(name)

    async def save_role(self, role: Role) -> None:
        await self._ensure_loaded()
        self._roles[role.name] = role
        await self._mutate()

    async def delete_role(self, name: str) -> bool:
        await self._ensure_loaded()
        if name not in self._roles:
            return False
        del self._roles[name]
        await self._mutate()
        return True

    async def all_roles(self) -> tuple[Role, ...]:
        await self._ensure_loaded()
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
        return pending if expires_at > self._clock() else None
