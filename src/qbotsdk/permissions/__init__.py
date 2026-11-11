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

"""权限声明、判定与存储。

Redis 与 SQL 实现需要安装可选依赖。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .builtin import PermissionCommands as PermissionCommands
from .builtin import install_permission_commands as install_permission_commands
from .checker import PermissionChecker as PermissionChecker
from .checker import account_of as account_of
from .checker import candidates as candidates
from .grant import Grant as Grant
from .grant import PendingGrant as PendingGrant
from .grant import Role as Role
from .grant import Scope as Scope
from .node import Permission as Permission
from .node import PermissionGroup as PermissionGroup
from .node import PermissionRegistry as PermissionRegistry
from .node import permission_registry as permission_registry
from .node import validate_key as validate_key
from .store import CachedPermissionStorage as CachedPermissionStorage
from .store import FilePermissionStorage as FilePermissionStorage
from .store import MemoryPermissionStorage as MemoryPermissionStorage
from .store import PermissionStorage as PermissionStorage

if TYPE_CHECKING:
    from .store import MysqlPermissionStorage as MysqlPermissionStorage
    from .store import PostgresPermissionStorage as PostgresPermissionStorage
    from .store import RedisPermissionStorage as RedisPermissionStorage
    from .store import SqlBackend as SqlBackend
    from .store import SqlitePermissionStorage as SqlitePermissionStorage
    from .store import SqlPermissionStorage as SqlPermissionStorage

__all__ = [
    "CachedPermissionStorage",
    "FilePermissionStorage",
    "Grant",
    "MemoryPermissionStorage",
    "MysqlPermissionStorage",
    "PendingGrant",
    "Permission",
    "PermissionChecker",
    "PermissionCommands",
    "PermissionGroup",
    "PermissionRegistry",
    "PermissionStorage",
    "PostgresPermissionStorage",
    "RedisPermissionStorage",
    "Role",
    "Scope",
    "SqlBackend",
    "SqlPermissionStorage",
    "SqlitePermissionStorage",
    "account_of",
    "candidates",
    "install_permission_commands",
    "permission_registry",
    "validate_key",
]


def __getattr__(name: str) -> Any:
    if name == "MysqlPermissionStorage":
        from .store import MysqlPermissionStorage

        return MysqlPermissionStorage
    if name == "PostgresPermissionStorage":
        from .store import PostgresPermissionStorage

        return PostgresPermissionStorage
    if name == "RedisPermissionStorage":
        from .store import RedisPermissionStorage

        return RedisPermissionStorage
    if name == "SqlBackend":
        from .store import SqlBackend

        return SqlBackend
    if name == "SqlPermissionStorage":
        from .store import SqlPermissionStorage

        return SqlPermissionStorage
    if name == "SqlitePermissionStorage":
        from .store import SqlitePermissionStorage

        return SqlitePermissionStorage
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    return sorted(__all__)
