# Copyright (c) 2026-present Half_nothing.

"""权限存储四种实现的共同行为测试。"""

from __future__ import annotations

import sqlite3
from collections.abc import AsyncIterator
from json import loads
from pathlib import Path

import pytest
from sqlalchemy.dialects import mysql as mysql_dialect
from sqlalchemy.dialects import postgresql as postgresql_dialect
from sqlalchemy.dialects import sqlite as sqlite_dialect
from sqlalchemy.schema import CreateTable

from qbotsdk.permissions import Grant, PendingGrant, Role
from qbotsdk.permissions.store import (
    CachedPermissionStorage,
    FilePermissionStorage,
    GrantList,
    MemoryPermissionStorage,
    MysqlPermissionStorage,
    PendingRecord,
    PermissionSchema,
    PermissionStorage,
    PostgresPermissionStorage,
    RoleRecord,
    SqlBackend,
    SqlitePermissionStorage,
)


class FakeClock:
    def __init__(self) -> None:
        self.now = 100.0

    def __call__(self) -> float:
        return self.now


def make_memory() -> tuple[PermissionStorage, FakeClock]:
    clock = FakeClock()
    return MemoryPermissionStorage(clock=clock), clock


def make_file(tmp_path: Path) -> tuple[PermissionStorage, FakeClock]:
    clock = FakeClock()
    return FilePermissionStorage(tmp_path / "permissions.json", clock=clock), clock


async def make_sql(tmp_path: Path) -> AsyncIterator[PermissionStorage]:
    store = SqlitePermissionStorage(tmp_path / "permissions.db", create_tables=True)
    try:
        yield store
    finally:
        await store.close()


async def test_grants_can_be_added_overwritten_and_revoked() -> None:
    store = MemoryPermissionStorage()

    await store.grant("group:g1:m1", Grant("a.b"))
    await store.grant("group:g1:m1", Grant("a.b", allow=False))
    await store.grant("group:g1:m1", Grant("c.d"))

    assert await store.grants("group:g1:m1") == frozenset({Grant("a.b", allow=False), Grant("c.d")})
    assert await store.revoke("group:g1:m1", "a.b") is True
    assert await store.revoke("group:g1:m1", "a.b") is False
    assert await store.grants("group:g1:m1") == frozenset({Grant("c.d")})


async def test_roles_round_trip_and_sort() -> None:
    store = MemoryPermissionStorage()

    await store.save_role(Role("b", grants=(Grant("b.b"),), parents=("a",)))
    await store.save_role(Role("a"))

    assert [role.name for role in await store.all_roles()] == ["a", "b"]
    assert await store.role("b") == Role("b", grants=(Grant("b.b"),), parents=("a",))
    assert await store.delete_role("b") is True
    assert await store.delete_role("b") is False
    assert await store.role("b") is None


async def test_assignment_tracks_roles() -> None:
    store = MemoryPermissionStorage()

    await store.assign("group:g1:m1", "admin")
    await store.assign("group:g1:m1", "viewer")

    assert await store.roles("group:g1:m1") == frozenset({"admin", "viewer"})

    await store.unassign("group:g1:m1", "admin")

    assert await store.roles("group:g1:m1") == frozenset({"viewer"})


async def test_rules_merge_grants_and_inherited_roles() -> None:
    store = MemoryPermissionStorage()
    await store.grant("group:g1:m1", Grant("direct.only"))
    await store.save_role(Role("base", grants=(Grant("base.only"),)))
    await store.save_role(Role("top", grants=(Grant("top.only"),), parents=("base",)))
    await store.assign("group:g1:m1", "top")

    rules = await store.rules("group:g1:m1")

    assert rules == frozenset({Grant("direct.only"), Grant("base.only"), Grant("top.only")})


async def test_pending_grants_expire() -> None:
    store, clock = make_memory()
    pending = PendingGrant("demo.stop", group_openid="g1")

    await store.save_pending("ABCD-1234", pending, ttl=10)
    clock.now += 5
    assert await store.pop_pending("ABCD-1234") == pending

    await store.save_pending("WXYZ-6789", pending, ttl=10)
    clock.now += 20
    assert await store.pop_pending("WXYZ-6789") is None


async def test_pending_code_is_single_use() -> None:
    store, _ = make_memory()
    pending = PendingGrant("demo.stop", scope="global")

    await store.save_pending("CODE", pending, ttl=10)

    assert await store.pop_pending("CODE") == pending
    assert await store.pop_pending("CODE") is None


async def test_save_pending_rejects_non_positive_ttl() -> None:
    store, _ = make_memory()

    with pytest.raises(ValueError, match="ttl must be positive"):
        await store.save_pending("CODE", PendingGrant("demo.stop", group_openid="g"), ttl=0)


async def test_cache_invalidates_on_writes() -> None:
    inner = MemoryPermissionStorage()
    cached = CachedPermissionStorage(inner, ttl=60.0)

    assert await cached.rules("group:g1:m1") == frozenset()

    await cached.grant("group:g1:m1", Grant("demo.stop"))

    assert await cached.rules("group:g1:m1") == frozenset({Grant("demo.stop")})


async def test_file_store_survives_reload(tmp_path: Path) -> None:
    path = tmp_path / "permissions.json"
    first = FilePermissionStorage(path)
    await first.grant("group:g1:m1", Grant("demo.stop"))
    await first.save_role(Role("admin", grants=(Grant("demo.*"),)))
    await first.assign("group:g1:m1", "admin")

    second = FilePermissionStorage(path)

    assert await second.grants("group:g1:m1") == frozenset({Grant("demo.stop")})
    assert await second.role("admin") == Role("admin", grants=(Grant("demo.*"),))
    assert await second.roles("group:g1:m1") == frozenset({"admin"})


async def test_file_store_tolerates_broken_json(tmp_path: Path) -> None:
    path = tmp_path / "permissions.json"
    path.write_text("not json", encoding="utf-8")

    store = FilePermissionStorage(path)

    assert await store.grants("group:g1:m1") == frozenset()


async def test_sql_store_round_trip(tmp_path: Path) -> None:
    async for store in make_sql(tmp_path):
        await store.grant("group:g1:m1", Grant("demo.stop"))
        await store.grant("group:g1:m1", Grant("demo.start", allow=False))
        await store.save_role(Role("admin", grants=(Grant("demo.*"),), parents=("base",)))
        await store.assign("group:g1:m1", "admin")

        assert await store.grants("group:g1:m1") == frozenset(
            {Grant("demo.stop"), Grant("demo.start", allow=False)}
        )
        assert await store.roles("group:g1:m1") == frozenset({"admin"})
        assert await store.role("admin") == Role(
            "admin", grants=(Grant("demo.*"),), parents=("base",)
        )
        assert [role.name for role in await store.all_roles()] == ["admin"]


async def test_sql_store_pending_is_single_use(tmp_path: Path) -> None:
    async for store in make_sql(tmp_path):
        pending = PendingGrant("demo.stop", group_openid="g1")
        await store.save_pending("ABCD-1234", pending, ttl=60)

        assert await store.pop_pending("ABCD-1234") == pending
        assert await store.pop_pending("ABCD-1234") is None


def test_wire_records_round_trip_through_json() -> None:
    grants = GrantList((Grant("demo.stop"), Grant("demo.start", allow=False)))
    assert GrantList.model_validate_json(grants.model_dump_json()).root == (
        Grant("demo.stop"),
        Grant("demo.start", allow=False),
    )

    role = RoleRecord.of(Role("admin", grants=(Grant("demo.*"),), parents=("base",)))
    assert RoleRecord.model_validate_json(role.model_dump_json()).to_role() == Role(
        "admin", grants=(Grant("demo.*"),), parents=("base",)
    )

    pending = PendingRecord.of(PendingGrant("demo.stop", group_openid="g1"))
    assert PendingRecord.model_validate_json(pending.model_dump_json()).to_pending() == (
        PendingGrant("demo.stop", group_openid="g1")
    )


async def test_sql_columns_store_json_records(tmp_path: Path) -> None:
    path = tmp_path / "permissions.db"
    store = SqlitePermissionStorage(path, create_tables=True)
    try:
        await store.grant("group:g1:m1", Grant("demo.stop"))
        await store.grant("group:g1:m1", Grant("demo.start", allow=False))
        await store.assign("group:g1:m1", "admin")
        await store.save_role(Role("admin", grants=(Grant("demo.*"),), parents=("base",)))
    finally:
        await store.close()

    with sqlite3.connect(path) as connection:
        grants = connection.execute(
            "select permissions, roles from qbotsdk_permission_grants"
        ).fetchone()
        role = connection.execute(
            "select parents, permissions from qbotsdk_permission_roles"
        ).fetchone()

    assert grants is not None and role is not None
    assert loads(grants[0]) == ["-demo.start", "demo.stop"]
    assert loads(grants[1]) == ["admin"]
    assert loads(role[0]) == ["base"]
    assert loads(role[1]) == ["demo.*"]


async def test_sqlite_storage_takes_a_path(tmp_path: Path) -> None:
    store = SqlitePermissionStorage(tmp_path / "permissions.db")

    try:
        assert store.path == (tmp_path / "permissions.db").resolve()
        assert store.url.startswith("sqlite+aiosqlite:///")
        assert store.url.endswith("permissions.db")
    finally:
        await store.close()


async def test_mysql_storage_builds_its_own_url() -> None:
    store = MysqlPermissionStorage(
        host="db.internal",
        port=3307,
        user="qbot",
        password="p@ss word",
        database="qbot",
        options={"charset": "utf8mb4"},
    )

    try:
        assert store.url == "mysql+asyncmy://qbot:***@db.internal:3307/qbot?charset=utf8mb4"
        assert "p%40ss" not in store.url
    finally:
        await store.close()


async def test_postgres_storage_builds_its_own_url() -> None:
    store = PostgresPermissionStorage(host="pg.internal", database="qbot", user="qbot")

    try:
        assert store.url == "postgresql+asyncpg://qbot@pg.internal:5432/qbot"
    finally:
        await store.close()


def test_backend_enum_carries_the_drivername() -> None:
    assert SqlBackend.SQLITE.drivername == "sqlite+aiosqlite"
    assert SqlBackend.MYSQL.drivername == "mysql+asyncmy"
    assert SqlBackend.POSTGRES.drivername == "postgresql+asyncpg"
    assert SqlBackend.MYSQL.driver == "asyncmy"


async def test_missing_driver_raises_an_install_hint(monkeypatch: pytest.MonkeyPatch) -> None:
    def _boom(*args: object, **kwargs: object) -> None:
        raise ModuleNotFoundError("No module named 'asyncmy'")

    monkeypatch.setattr("qbotsdk.permissions.store.sql_base.create_async_engine", _boom)
    store = MysqlPermissionStorage(database="qbot")

    with pytest.raises(ImportError, match=r"pip install qbotsdk\[mysql\]"):
        await store.grants("group:g1:m1")


def test_schema_compiles_for_every_backend() -> None:
    schema = PermissionSchema()

    for dialect in (
        sqlite_dialect.dialect(),
        mysql_dialect.dialect(),
        postgresql_dialect.dialect(),  # type: ignore[no-untyped-call]
    ):
        ddl = str(CreateTable(schema.grants).compile(dialect=dialect))
        assert "principal" in ddl
        assert "permissions" in ddl


def test_sql_backends_build_their_own_upsert() -> None:
    schema = PermissionSchema()
    values = {"principal": "p", "permissions": "[]", "roles": "[]"}
    updates = {"permissions": "[]"}

    sqlite_statement = SqlitePermissionStorage._insert_statement(schema.grants).values(**values)
    sqlite_compiled = str(
        SqlitePermissionStorage._conflict_statement(
            sqlite_statement, schema.grants, "principal", updates
        ).compile(dialect=sqlite_dialect.dialect())
    )
    assert "ON CONFLICT" in sqlite_compiled.upper()
    assert "DO UPDATE" in sqlite_compiled.upper()

    mysql_statement = MysqlPermissionStorage._insert_statement(schema.grants).values(**values)
    mysql_compiled = str(
        MysqlPermissionStorage._conflict_statement(
            mysql_statement, schema.grants, "principal", updates
        ).compile(dialect=mysql_dialect.dialect())
    )
    assert "ON DUPLICATE KEY UPDATE" in mysql_compiled.upper()

    postgres_statement = PostgresPermissionStorage._insert_statement(schema.grants).values(**values)
    postgres_dialect = postgresql_dialect.dialect()  # type: ignore[no-untyped-call]
    postgres_compiled = str(
        PostgresPermissionStorage._conflict_statement(
            postgres_statement, schema.grants, "principal", updates
        ).compile(dialect=postgres_dialect)
    )
    assert "ON CONFLICT" in postgres_compiled.upper()
