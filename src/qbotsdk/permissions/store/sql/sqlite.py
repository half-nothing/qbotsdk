# Copyright (c) 2026-present Half_nothing.

"""SQLite 存储。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlalchemy import URL, Table
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from .backend import SqlBackend
from .base import SqlPermissionStorage


class SqlitePermissionStorage(SqlPermissionStorage):
    """基于 SQLite 的权限存储。"""

    backend = SqlBackend.SQLITE

    def __init__(
        self,
        path: str | Path = "permissions.db",
        *,
        table_prefix: str = "qbotsdk_",
        create_tables: bool = False,
    ) -> None:
        self.path = Path(path).expanduser().resolve()
        url = URL.create(SqlBackend.SQLITE.drivername, database=str(self.path))
        super().__init__(url, table_prefix=table_prefix, create_tables=create_tables)

    @staticmethod
    def _insert_statement(table: Table) -> Any:
        return sqlite_insert(table)

    @staticmethod
    def _conflict_statement(
        statement: Any,
        table: Table,
        key: str,
        updates: dict[str, Any],
    ) -> Any:
        return statement.on_conflict_do_update(index_elements=[table.c[key]], set_=updates)
