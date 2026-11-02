# Copyright (c) 2026-present Half_nothing.

"""权限声明、判定与存储。

Redis 与 SQL 实现需要可选依赖, 首次访问时才导入。
"""

from __future__ import annotations

from typing import Any

from .builtin import PermissionCommands, install_permission_commands
from .checker import PermissionChecker, account_of, candidates
from .grant import Grant, PendingGrant, Role, Scope
from .node import (
    Permission,
    PermissionGroup,
    PermissionRegistry,
    permission_registry,
    validate_key,
)
from .store import (
    CachedPermissionStorage,
    FilePermissionStorage,
    MemoryPermissionStorage,
    PermissionStorage,
)

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

_EXTERNAL_NAMES = {
    "MysqlPermissionStorage",
    "PostgresPermissionStorage",
    "RedisPermissionStorage",
    "SqlBackend",
    "SqlPermissionStorage",
    "SqlitePermissionStorage",
}


def __getattr__(name: str) -> Any:
    if name in _EXTERNAL_NAMES:
        from . import store

        return getattr(store, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
