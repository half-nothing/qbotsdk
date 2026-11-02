# Copyright (c) 2026-present Half_nothing.

"""权限存储实现, Redis 与 SQL 需要可选依赖, 因此惰性导入。"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .base import CachedPermissionStorage, PermissionStorage
from .file import FilePermissionStorage
from .memory import MemoryPermissionStorage

if TYPE_CHECKING:
    from .redis import RedisPermissionStorage
    from .sql import (
        MysqlPermissionStorage,
        PostgresPermissionStorage,
        SqlBackend,
        SqlitePermissionStorage,
        SqlPermissionStorage,
    )

__all__ = [
    "CachedPermissionStorage",
    "FilePermissionStorage",
    "MemoryPermissionStorage",
    "MysqlPermissionStorage",
    "PermissionStorage",
    "PostgresPermissionStorage",
    "RedisPermissionStorage",
    "SqlBackend",
    "SqlPermissionStorage",
    "SqlitePermissionStorage",
]


def __getattr__(name: str) -> Any:
    if name == "RedisPermissionStorage":
        from .redis import RedisPermissionStorage

        return RedisPermissionStorage
    if name == "SqlBackend":
        from .sql import SqlBackend

        return SqlBackend
    if name == "SqlPermissionStorage":
        from .sql import SqlPermissionStorage

        return SqlPermissionStorage
    if name == "SqlitePermissionStorage":
        from .sql import SqlitePermissionStorage

        return SqlitePermissionStorage
    if name == "MysqlPermissionStorage":
        from .sql import MysqlPermissionStorage

        return MysqlPermissionStorage
    if name == "PostgresPermissionStorage":
        from .sql import PostgresPermissionStorage

        return PostgresPermissionStorage
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    return sorted(__all__)
