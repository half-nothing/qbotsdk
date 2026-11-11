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

"""权限存储实现, Redis 与 SQL 需要可选依赖, 因此惰性导入。"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .base import CachedPermissionStorage as CachedPermissionStorage
from .base import PermissionStorage as PermissionStorage
from .file import FilePermissionStorage as FilePermissionStorage
from .memory import MemoryPermissionStorage as MemoryPermissionStorage

if TYPE_CHECKING:
    from .redis import RedisPermissionStorage as RedisPermissionStorage
    from .sql import MysqlPermissionStorage as MysqlPermissionStorage
    from .sql import PostgresPermissionStorage as PostgresPermissionStorage
    from .sql import SqlBackend as SqlBackend
    from .sql import SqlitePermissionStorage as SqlitePermissionStorage
    from .sql import SqlPermissionStorage as SqlPermissionStorage

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
