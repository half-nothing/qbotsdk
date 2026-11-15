# Copyright (c) 2026-present Half_nothing.

"""通用 SQL 存储底座的测试。"""

from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.engine import URL
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from qbotsdk.permissions.store import MysqlPermissionStorage, PostgresPermissionStorage
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


def test_permissions_store_does_not_reexport_sql_backend() -> None:
    import qbotsdk.permissions.store as store_module

    assert "SqlBackend" not in store_module.__all__
    assert not hasattr(store_module, "SqlBackend")


async def test_connection_applies_pool_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    from qbotsdk.storage import sql as sql_module

    captured: list[dict[str, Any]] = []
    original = sql_module.create_async_engine

    def spy(url: str | URL, **kwargs: Any) -> AsyncEngine:
        captured.append(kwargs)
        return original(url, **kwargs)

    monkeypatch.setattr(sql_module, "create_async_engine", spy)

    default_store = SqlStorage.from_url("sqlite+aiosqlite://")
    default_store._connection()
    await default_store.close()

    recycled = SqlStorage.from_url("sqlite+aiosqlite://", pool_recycle=1800)
    recycled._connection()
    await recycled.close()

    assert captured[0]["pool_pre_ping"] is True
    assert captured[0]["pool_recycle"] == -1
    assert captured[1]["pool_pre_ping"] is True
    assert captured[1]["pool_recycle"] == 1800


async def test_pool_recycle_flows_through_subclass_from_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from qbotsdk.permissions.store import SqlitePermissionStorage
    from qbotsdk.storage import sql as sql_module

    captured: list[dict[str, Any]] = []
    original = sql_module.create_async_engine

    def spy(url: str | URL, **kwargs: Any) -> AsyncEngine:
        captured.append(kwargs)
        return original(url, **kwargs)

    monkeypatch.setattr(sql_module, "create_async_engine", spy)

    store = SqlitePermissionStorage.from_url("sqlite+aiosqlite://", pool_recycle=900)
    store._connection()
    await store.close()

    assert captured[0]["pool_recycle"] == 900


def test_pool_recycle_reaches_dialect_constructors() -> None:
    # 这里不建引擎: 断言参数被构造函数收下并传到基类, 不需要装 MySQL/PostgreSQL 驱动
    assert MysqlPermissionStorage(database="qbot", pool_recycle=600)._pool_recycle == 600
    assert PostgresPermissionStorage(database="qbot")._pool_recycle == -1
