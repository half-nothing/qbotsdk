# Copyright (c) 2026-present Half_nothing.

"""PostgreSQL 存储。"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import URL, Table
from sqlalchemy.dialects.postgresql import insert as postgresql_insert

from .backend import SqlBackend
from .base import SqlPermissionStorage

if TYPE_CHECKING:
    from collections.abc import Mapping


class PostgresPermissionStorage(SqlPermissionStorage):
    """基于 PostgreSQL 的权限存储。"""

    backend = SqlBackend.POSTGRES

    def __init__(
        self,
        *,
        database: str,
        user: str = "postgres",
        password: str | None = None,
        host: str = "localhost",
        port: int = 5432,
        options: Mapping[str, str] | None = None,
        table_prefix: str = "qbotsdk_",
        create_tables: bool = False,
    ) -> None:
        url = URL.create(
            SqlBackend.POSTGRES.drivername,
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
        return postgresql_insert(table)

    @staticmethod
    def _conflict_statement(
        statement: Any,
        table: Table,
        key: str,
        updates: dict[str, Any],
    ) -> Any:
        return statement.on_conflict_do_update(index_elements=[table.c[key]], set_=updates)
