# Copyright (c) 2026-present Half_nothing.

"""关系库类型。"""

from __future__ import annotations

from enum import StrEnum


class SqlBackend(StrEnum):
    """权限存储支持的关系库。"""

    SQLITE = "sqlite"
    MYSQL = "mysql"
    POSTGRES = "postgres"

    @property
    def drivername(self) -> str:
        """SQLAlchemy 的 driver 名。"""

        return _DRIVERNAMES[self]

    @property
    def driver(self) -> str:
        """驱动包名, 缺依赖时写进提示里。"""

        return _DRIVERS[self]


_DRIVERNAMES: dict[SqlBackend, str] = {
    SqlBackend.SQLITE: "sqlite+aiosqlite",
    SqlBackend.MYSQL: "mysql+asyncmy",
    SqlBackend.POSTGRES: "postgresql+asyncpg",
}

_DRIVERS: dict[SqlBackend, str] = {
    SqlBackend.SQLITE: "aiosqlite",
    SqlBackend.MYSQL: "asyncmy",
    SqlBackend.POSTGRES: "asyncpg",
}
