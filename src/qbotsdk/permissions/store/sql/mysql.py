# Copyright (c) 2026-present Half_nothing.

"""MySQL 存储。"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import URL, Table
from sqlalchemy.dialects.mysql import insert as mysql_insert

from .backend import SqlBackend
from .base import SqlPermissionStorage

if TYPE_CHECKING:
    from collections.abc import Mapping


class MysqlPermissionStorage(SqlPermissionStorage):
    """基于 MySQL / MariaDB 的权限存储。"""

    backend = SqlBackend.MYSQL

    def __init__(
        self,
        *,
        database: str,
        user: str = "root",
        password: str | None = None,
        host: str = "localhost",
        port: int = 3306,
        options: Mapping[str, str] | None = None,
        table_prefix: str = "qbotsdk_",
        create_tables: bool = False,
    ) -> None:
        url = URL.create(
            SqlBackend.MYSQL.drivername,
            username=user,
            password=password,
            host=host,
            port=port,
            database=database,
            query=dict(options or {}),
        )
        super().__init__(url, table_prefix=table_prefix, create_tables=create_tables)

    @staticmethod
    def _insert_statement(table: Table) -> Any:
        return mysql_insert(table)

    @staticmethod
    def _conflict_statement(
        statement: Any,
        table: Table,
        key: str,
        updates: dict[str, Any],
    ) -> Any:
        return statement.on_duplicate_key_update(**updates)
