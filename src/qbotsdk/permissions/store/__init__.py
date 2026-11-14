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
from .schema import PermissionSchema as PermissionSchema
from .wire import GrantField as GrantField
from .wire import GrantList as GrantList
from .wire import NameList as NameList
from .wire import PendingRecord as PendingRecord
from .wire import RoleRecord as RoleRecord

if TYPE_CHECKING:
    from qbotsdk.storage.sql import SqlBackend as SqlBackend

    from .mysql import MysqlPermissionStorage as MysqlPermissionStorage
    from .postgres import PostgresPermissionStorage as PostgresPermissionStorage
    from .redis import RedisPermissionStorage as RedisPermissionStorage
    from .schema import PermissionSchema as PermissionSchema
    from .sql_base import SqlPermissionStorage as SqlPermissionStorage
    from .sqlite import SqlitePermissionStorage as SqlitePermissionStorage

__all__ = [
    "CachedPermissionStorage",
    "FilePermissionStorage",
    "GrantField",
    "GrantList",
    "MemoryPermissionStorage",
    "MysqlPermissionStorage",
    "NameList",
    "PendingRecord",
    "PermissionSchema",
    "PermissionStorage",
    "PostgresPermissionStorage",
    "RedisPermissionStorage",
    "RoleRecord",
    "SqlBackend",
    "SqlPermissionStorage",
    "SqlitePermissionStorage",
]


def __getattr__(name: str) -> Any:
    if name == "RedisPermissionStorage":
        from .redis import RedisPermissionStorage

        return RedisPermissionStorage
    if name == "SqlBackend":
        from qbotsdk.storage.sql import SqlBackend

        return SqlBackend
    if name == "SqlPermissionStorage":
        from .sql_base import SqlPermissionStorage

        return SqlPermissionStorage
    if name == "SqlitePermissionStorage":
        from .sqlite import SqlitePermissionStorage

        return SqlitePermissionStorage
    if name == "MysqlPermissionStorage":
        from .mysql import MysqlPermissionStorage

        return MysqlPermissionStorage
    if name == "PostgresPermissionStorage":
        from .postgres import PostgresPermissionStorage

        return PostgresPermissionStorage
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    return sorted(__all__)
