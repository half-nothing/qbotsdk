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

"""关系库类型。"""

from __future__ import annotations

from enum import StrEnum

__all__ = ["SqlBackend"]


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
