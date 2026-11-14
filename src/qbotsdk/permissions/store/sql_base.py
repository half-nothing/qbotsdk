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

"""SQL存储的公共部分, 连接、表、读写流程。"""

from __future__ import annotations

from time import time
from typing import TYPE_CHECKING, Any, ClassVar, Self, cast, override

from loguru import logger
from pydantic import ValidationError

from qbotsdk.permissions import Grant, PendingGrant, Role, Scope
from qbotsdk.storage.sql import SqlBackend, SqlStorage

from .base import PermissionStorage
from .schema import PermissionSchema
from .wire import GrantList, NameList, PendingRecord

try:  # pragma: no cover
    from sqlalchemy import delete, make_url, select
    from sqlalchemy.engine import URL
    from sqlalchemy.ext.asyncio import AsyncEngine
except ImportError as exc:  # pragma: no cover
    raise ImportError(
        "SQL permission storage requires SQLAlchemy; "
        "install it with `pip install qbotsdk[sqlite]` "
        "(or `qbotsdk[mysql]` / `qbotsdk[postgres]`)"
    ) from exc

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping

    from sqlalchemy import Table

__all__ = ["SqlPermissionStorage"]


def _encode_grants(grants: Iterable[Grant]) -> str:
    return GrantList(
        tuple(sorted(grants, key=lambda item: item.permission)),
    ).model_dump_json()


def _decode_grants(text: object) -> dict[str, Grant]:
    raw = str(text or "")
    if not raw:
        return {}
    try:
        return GrantList.model_validate_json(raw).as_map()
    except ValidationError:
        logger.warning("stored grants are not valid, starting empty")
        return {}


def _encode_names(names: Iterable[str]) -> str:
    return NameList(tuple(sorted(names))).model_dump_json()


def _decode_names(text: object) -> tuple[str, ...]:
    raw = str(text or "")
    if not raw:
        return ()
    try:
        return NameList.model_validate_json(raw).root
    except ValidationError:
        logger.warning("stored names are not valid, starting empty")
        return ()


class SqlPermissionStorage(SqlStorage, PermissionStorage):
    """权限的关系库存储基类, 表与读写流程在这里, 连接层复用 `SqlStorage`。"""

    backend: ClassVar[SqlBackend] = SqlBackend.SQLITE
    dialect_names: ClassVar[tuple[str, ...]] = ("sqlite",)

    def __init__(
        self,
        url: URL | str,
        *,
        table_prefix: str = "qbotsdk_",
        create_tables: bool = False,
        connect_args: Mapping[str, Any] | None = None,
        engine: AsyncEngine | None = None,
    ) -> None:
        super().__init__(url, connect_args=connect_args, engine=engine)
        self._schema = PermissionSchema(table_prefix)
        self._create_tables = create_tables

    @classmethod
    @override
    def from_url(
        cls,
        url: str | URL,
        *,
        table_prefix: str = "qbotsdk_",
        create_tables: bool = False,
        connect_args: Mapping[str, Any] | None = None,
    ) -> Self:
        """用完整连接串构造存储, 驱动名写在 URL 里。

        异步驱动可以换成任意 SQLAlchemy 支持的名字, 例如 `mysql+aiomysql`
        或 `postgresql+psycopg`。

        :param url:          完整连接串, `str` 或 `sqlalchemy.engine.URL`。
        :param table_prefix: 表名前缀, 同一个库里的多套权限靠它隔离。
        :param create_tables: 首次使用时自动建表。
        :param connect_args: 直接交给驱动的连接参数, 放不进 URL 查询串的对象走这里。

        :raise ValueError: URL 没写异步驱动, 或方言与存储类不匹配。
        """

        parsed = make_url(url)
        cls._check_url(parsed)
        return cls._adopt(
            parsed,
            table_prefix=table_prefix,
            create_tables=create_tables,
            connect_args=connect_args,
        )

    @classmethod
    @override
    def from_engine(
        cls,
        engine: AsyncEngine,
        *,
        table_prefix: str = "qbotsdk_",
        create_tables: bool = False,
    ) -> Self:
        """复用调用方已有的异步引擎, 存储不负责关闭它。

        :param engine:        `sqlalchemy.ext.asyncio.AsyncEngine`。
        :param table_prefix:  表名前缀。
        :param create_tables: 首次使用时自动建表。

        :raise TypeError:  传入的不是 `AsyncEngine`。
        :raise ValueError: 引擎的方言与存储类不匹配。
        """

        if not isinstance(engine, AsyncEngine):
            raise TypeError("engine must be an AsyncEngine")
        cls._check_url(engine.url)
        return cls._adopt(
            engine.url,
            engine=engine,
            table_prefix=table_prefix,
            create_tables=create_tables,
        )

    @classmethod
    @override
    def _adopt(
        cls,
        url: URL,
        *,
        engine: AsyncEngine | None = None,
        table_prefix: str = "qbotsdk_",
        create_tables: bool = False,
        connect_args: Mapping[str, Any] | None = None,
    ) -> Self:
        """按已经解析好的 URL 建实例, 绕开子类构造函数的连接参数。"""

        store = cls.__new__(cls)
        SqlPermissionStorage.__init__(
            store,
            url,
            table_prefix=table_prefix,
            create_tables=create_tables,
            connect_args=connect_args,
            engine=engine,
        )
        return store

    async def grants(self, principal: str) -> frozenset[Grant]:
        await self._ensure_tables()
        raw = await self._read_column(self._schema.grants, "permissions", "principal", principal)
        return frozenset(_decode_grants(raw).values())

    async def grant(self, principal: str, grant: Grant) -> None:
        await self._ensure_tables()
        current = {item.permission: item for item in await self.grants(principal)}
        current[grant.permission] = grant
        await self._write_row(
            principal,
            grants=current.values(),
            roles=await self._read_assigned(principal),
        )

    async def revoke(self, principal: str, permission: str) -> bool:
        await self._ensure_tables()
        current = {item.permission: item for item in await self.grants(principal)}
        if permission not in current:
            return False
        del current[permission]
        await self._write_row(
            principal,
            grants=current.values(),
            roles=await self._read_assigned(principal),
        )
        return True

    async def roles(self, principal: str) -> frozenset[str]:
        await self._ensure_tables()
        return frozenset(await self._read_assigned(principal))

    async def assign(self, principal: str, role: str) -> None:
        await self._ensure_tables()
        assigned = await self._read_assigned(principal)
        assigned.add(role)
        await self._write_row(
            principal,
            grants=await self.grants(principal),
            roles=assigned,
        )

    async def unassign(self, principal: str, role: str) -> None:
        await self._ensure_tables()
        assigned = await self._read_assigned(principal)
        if role not in assigned:
            return
        assigned.discard(role)
        await self._write_row(
            principal,
            grants=await self.grants(principal),
            roles=assigned,
        )

    async def role(self, name: str) -> Role | None:
        await self._ensure_tables()
        async with self._connection().connect() as connection:
            row = (
                await connection.execute(
                    select(
                        self._schema.roles.c.name,
                        self._schema.roles.c.parents,
                        self._schema.roles.c.permissions,
                    ).where(self._schema.roles.c.name == name)
                )
            ).first()
        return None if row is None else self._to_role(row)

    async def save_role(self, role: Role) -> None:
        await self._ensure_tables()
        await self._upsert(
            self._schema.roles,
            {
                "name": role.name,
                "parents": _encode_names(role.parents),
                "permissions": _encode_grants(role.grants),
            },
            key="name",
        )

    async def delete_role(self, name: str) -> bool:
        await self._ensure_tables()
        async with self._connection().begin() as connection:
            result = await connection.execute(
                delete(self._schema.roles).where(self._schema.roles.c.name == name)
            )
        return bool(result.rowcount)

    async def all_roles(self) -> tuple[Role, ...]:
        await self._ensure_tables()
        async with self._connection().connect() as connection:
            rows = (
                await connection.execute(
                    select(
                        self._schema.roles.c.name,
                        self._schema.roles.c.parents,
                        self._schema.roles.c.permissions,
                    ).order_by(self._schema.roles.c.name)
                )
            ).all()
        return tuple(self._to_role(row) for row in rows)

    async def save_pending(self, code: str, pending: PendingGrant, *, ttl: float) -> None:
        await self._ensure_tables()
        if ttl <= 0:
            raise ValueError("ttl must be positive")
        record = PendingRecord.of(pending)
        async with self._connection().begin() as connection:
            await connection.execute(
                delete(self._schema.pending).where(self._schema.pending.c.code == code)
            )
            await connection.execute(
                self._insert_statement(self._schema.pending).values(
                    code=code,
                    permission=record.permission,
                    scope=record.scope,
                    group_openid=record.group_openid,
                    expires_at=time() + ttl,
                )
            )

    async def pop_pending(self, code: str) -> PendingGrant | None:
        await self._ensure_tables()
        async with self._connection().begin() as connection:
            row = (
                await connection.execute(
                    select(
                        self._schema.pending.c.permission,
                        self._schema.pending.c.scope,
                        self._schema.pending.c.group_openid,
                        self._schema.pending.c.expires_at,
                    ).where(self._schema.pending.c.code == code)
                )
            ).first()
            if row is None:
                return None
            await connection.execute(
                delete(self._schema.pending).where(self._schema.pending.c.code == code)
            )
        if float(row[3]) <= time():
            return None
        try:
            record = PendingRecord(
                permission=str(row[0]),
                scope=cast("Scope", str(row[1])),
                group_openid=row[2],
            )
        except ValidationError:
            logger.warning("pending grant {!r} is not valid, ignoring", code)
            return None
        return record.to_pending()

    @staticmethod
    def _insert_statement(table: Table) -> Any:
        raise NotImplementedError

    @staticmethod
    def _conflict_statement(
        statement: Any,
        table: Table,
        key: str,
        updates: dict[str, Any],
    ) -> Any:
        raise NotImplementedError

    async def _upsert(self, table: Table, values: dict[str, Any], *, key: str) -> None:
        statement = self._insert_statement(table).values(**values)
        updates = {name: value for name, value in values.items() if name != key}
        async with self._connection().begin() as connection:
            await connection.execute(self._conflict_statement(statement, table, key, updates))

    async def _ensure_tables(self) -> None:
        if not self._create_tables:
            return
        async with self._connection().begin() as connection:
            await connection.run_sync(self._schema.metadata.create_all)
        self._create_tables = False

    async def _read_column(self, table: Table, column: str, where: str, value: str) -> Any:
        async with self._connection().connect() as connection:
            row = (
                await connection.execute(select(table.c[column]).where(table.c[where] == value))
            ).first()
        return None if row is None else row[0]

    async def _read_assigned(self, principal: str) -> set[str]:
        raw = await self._read_column(self._schema.grants, "roles", "principal", principal)
        return set(_decode_names(raw))

    def _to_role(self, row: Any) -> Role:
        return Role(
            name=str(row[0]),
            grants=tuple(_decode_grants(row[2]).values()),
            parents=_decode_names(row[1]),
        )

    async def _write_row(
        self,
        principal: str,
        *,
        grants: Iterable[Grant],
        roles: Iterable[str],
    ) -> None:
        await self._upsert(
            self._schema.grants,
            {
                "principal": principal,
                "permissions": _encode_grants(grants),
                "roles": _encode_names(roles),
            },
            key="principal",
        )
