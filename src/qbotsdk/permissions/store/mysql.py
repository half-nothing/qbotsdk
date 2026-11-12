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

"""MySQL 存储。"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, override

from sqlalchemy import URL, Table
from sqlalchemy.dialects.mysql import insert as mysql_insert

from .sql_backend import SqlBackend
from .sql_base import SqlPermissionStorage

if TYPE_CHECKING:
    from collections.abc import Mapping

__all__ = ["MysqlPermissionStorage"]


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

    @override
    @staticmethod
    def _insert_statement(table: Table) -> Any:
        return mysql_insert(table)

    @override
    @staticmethod
    def _conflict_statement(
        statement: Any,
        table: Table,
        key: str,
        updates: dict[str, Any],
    ) -> Any:
        return statement.on_duplicate_key_update(**updates)
