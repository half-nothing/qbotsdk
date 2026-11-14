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

"""SQLite 存储。"""

from __future__ import annotations

from pathlib import Path
from typing import Any, override

from sqlalchemy import URL, Table
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from qbotsdk.storage.sql import SqlBackend

from .sql_base import SqlPermissionStorage

__all__ = ["SqlitePermissionStorage"]


class SqlitePermissionStorage(SqlPermissionStorage):
    """基于 SQLite 的权限存储。"""

    backend = SqlBackend.SQLITE
    dialect_names = ("sqlite",)

    def __init__(
        self,
        path: str | Path = "permissions.db",
        *,
        table_prefix: str = "qbotsdk_",
        create_tables: bool = False,
    ) -> None:
        resolved = Path(path).expanduser().resolve()
        url = URL.create(SqlBackend.SQLITE.drivername, database=str(resolved))
        super().__init__(url, table_prefix=table_prefix, create_tables=create_tables)

    @property
    def path(self) -> Path:
        """SQLite 数据库文件路径。"""

        return Path(self._url.database or "")

    @override
    @staticmethod
    def _insert_statement(table: Table) -> Any:
        return sqlite_insert(table)

    @override
    @staticmethod
    def _conflict_statement(
        statement: Any,
        table: Table,
        key: str,
        updates: dict[str, Any],
    ) -> Any:
        return statement.on_conflict_do_update(index_elements=[table.c[key]], set_=updates)
