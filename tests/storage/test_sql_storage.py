# Copyright (c) 2026-present Half_nothing.

"""通用 SQL 存储底座的测试。"""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from qbotsdk.storage import SqlBackend, SqlStorage
from qbotsdk.storage.sql import resolve_drivername


def test_sql_backend_defaults() -> None:
    assert SqlBackend.SQLITE.drivername == "sqlite+aiosqlite"
    assert SqlBackend.MYSQL.drivername == "mysql+asyncmy"
    assert SqlBackend.POSTGRES.drivername == "postgresql+asyncpg"
    assert SqlBackend.MYSQL.driver == "asyncmy"


def test_resolve_drivername() -> None:
    assert resolve_drivername(None, ("mysql",), "mysql+asyncmy") == "mysql+asyncmy"
    assert resolve_drivername("aiomysql", ("mysql",), "mysql+asyncmy") == "mysql+aiomysql"
    assert (
        resolve_drivername("postgresql+psycopg", ("postgresql",), "postgresql+asyncpg")
        == "postgresql+psycopg"
    )
    with pytest.raises(ValueError, match="does not match"):
        resolve_drivername("postgresql+psycopg", ("mysql",), "mysql+asyncmy")


async def test_sql_storage_from_url() -> None:
    store = SqlStorage.from_url("sqlite+aiosqlite://")
    assert store.url == "sqlite+aiosqlite://"
    await store.close()


def test_sql_storage_rejects_sync_url() -> None:
    with pytest.raises(ValueError, match="async driver"):
        SqlStorage.from_url("sqlite://")


async def test_sql_storage_from_engine_does_not_own_engine() -> None:
    engine = create_async_engine("sqlite+aiosqlite://")
    store = SqlStorage.from_engine(engine)
    await store.close()
    async with engine.connect() as connection:
        await connection.execute(text("SELECT 1"))
    await engine.dispose()


def test_permissions_store_keeps_sql_backend_export() -> None:
    from qbotsdk.permissions.store import SqlBackend as ExportedSqlBackend

    assert ExportedSqlBackend is SqlBackend
