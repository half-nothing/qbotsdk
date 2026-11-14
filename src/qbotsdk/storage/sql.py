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

"""关系库存储的公共底座: 方言、驱动名与引擎生命周期, 不含任何业务表。"""

from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING, Any, ClassVar, Self

try:  # pragma: no cover
    from sqlalchemy import make_url
    from sqlalchemy.engine import URL
    from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
except ImportError as exc:  # pragma: no cover
    raise ImportError(
        "SQL storage requires SQLAlchemy; "
        "install it with `pip install qbotsdk[sqlite]` "
        "(or `qbotsdk[mysql]` / `qbotsdk[postgres]`)"
    ) from exc

if TYPE_CHECKING:
    from collections.abc import Mapping

__all__ = ["SqlBackend", "SqlStorage", "resolve_drivername"]


class SqlBackend(StrEnum):
    """SDK 内置的 SQL 方言, 与 extras 一一对应。"""

    SQLITE = "sqlite"
    MYSQL = "mysql"
    POSTGRES = "postgres"

    @property
    def drivername(self) -> str:
        """默认的 SQLAlchemy drivername。"""

        return _DRIVERNAMES[self]

    @property
    def driver(self) -> str:
        """默认的驱动包名, 缺依赖时写进提示里。"""

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


def resolve_drivername(
    driver: str | None,
    dialect_names: tuple[str, ...],
    default: str,
) -> str:
    """把用户给的驱动名归一成 SQLAlchemy 的 drivername。

    `driver` 可以是 `aiomysql` 这样的裸包名, 也可以是 `mysql+aiomysql`
    这样的完整写法; 方言必须落在 `dialect_names` 里。
    """

    if driver is None:
        return default
    name = driver.strip()
    if not name:
        raise ValueError("driver must not be empty")
    drivername = name if "+" in name else f"{dialect_names[0]}+{name}"
    dialect, _, resolved = drivername.partition("+")
    if not resolved:
        raise ValueError(f"driver {driver!r} must name a driver, e.g. {default!r}")
    if dialect not in dialect_names:
        raise ValueError(
            f"driver {driver!r} does not match the storage dialect; "
            f"expected one of: {', '.join(dialect_names)}"
        )
    return drivername


class SqlStorage:
    """SQL 存储的公共底座: URL 解析、引擎创建与释放。

    子类绑定 `backend` 与 `dialect_names` 并补自己的表; 连接层不掺业务,
    其它存储可以直接继承, 也可以单独使用。
    """

    backend: ClassVar[SqlBackend] = SqlBackend.SQLITE
    dialect_names: ClassVar[tuple[str, ...]] = ("sqlite",)

    def __init__(
        self,
        url: URL | str,
        *,
        connect_args: Mapping[str, Any] | None = None,
        engine: AsyncEngine | None = None,
    ) -> None:
        self._url = make_url(url) if isinstance(url, str) else url
        self._engine = engine
        self._owns_engine = engine is None
        self._connect_args = dict(connect_args or {})

    @classmethod
    def from_url(
        cls,
        url: str | URL,
        *,
        connect_args: Mapping[str, Any] | None = None,
    ) -> Self:
        """用完整连接串构造, 驱动名写在 URL 里。

        :param url:          完整连接串, `str` 或 `sqlalchemy.engine.URL`。
        :param connect_args: 直接交给驱动的连接参数, 放不进 URL 查询串的对象走这里。

        :raise ValueError: URL 没写异步驱动, 或方言与存储类不匹配。
        """

        parsed = make_url(url)
        cls._check_url(parsed)
        return cls._adopt(parsed, connect_args=connect_args)

    @classmethod
    def from_engine(cls, engine: AsyncEngine) -> Self:
        """复用调用方已有的异步引擎, `close()` 不负责关闭它。

        :param engine: `sqlalchemy.ext.asyncio.AsyncEngine`。

        :raise TypeError:  传入的不是 `AsyncEngine`。
        :raise ValueError: 引擎的方言与存储类不匹配。
        """

        if not isinstance(engine, AsyncEngine):
            raise TypeError("engine must be an AsyncEngine")
        cls._check_url(engine.url)
        return cls._adopt(engine.url, engine=engine)

    @classmethod
    def _adopt(
        cls,
        url: URL,
        *,
        engine: AsyncEngine | None = None,
        connect_args: Mapping[str, Any] | None = None,
    ) -> Self:
        """按已经解析好的 URL 建实例, 绕开子类构造函数的连接参数。"""

        store = cls.__new__(cls)
        SqlStorage.__init__(store, url, connect_args=connect_args, engine=engine)
        return store

    @classmethod
    def _check_url(cls, url: URL) -> None:
        dialect, _, driver = url.drivername.partition("+")
        if not driver:
            raise ValueError(f"URL must name an async driver, e.g. {cls.backend.drivername}://...")
        if dialect not in cls.dialect_names:
            raise ValueError(
                f"URL dialect {dialect!r} does not match {cls.__name__}; "
                f"expected one of: {', '.join(cls.dialect_names)}"
            )

    @property
    def url(self) -> str:
        """连接串, 密码已打码, 便于日志里确认连的是哪个库。"""

        return self._url.render_as_string(hide_password=True)

    async def close(self) -> None:
        """释放自己创建的引擎; `from_engine` 采纳的引擎归调用方, 这里不动它。"""

        if not self._owns_engine or self._engine is None:
            return
        await self._engine.dispose()
        self._engine = None

    def _driver_name(self) -> str:
        """实际使用的驱动包名, 从解析后的 URL 取。"""

        return self._url.drivername.rpartition("+")[2] or self._url.drivername

    def _connection(self) -> AsyncEngine:
        """引擎在第一次使用时才创建, 构造存储本身不需要驱动。"""

        if self._engine is None:
            try:
                self._engine = create_async_engine(
                    self._url,
                    future=True,
                    connect_args=self._connect_args,
                )
            except ModuleNotFoundError as exc:  # pragma: no cover
                driver = self._driver_name()
                install = (
                    f"qbotsdk[{self.backend.value}]" if driver == self.backend.driver else driver
                )
                raise ImportError(
                    f"{type(self).__name__} needs the {driver} driver; "
                    f"install it with `pip install {install}`"
                ) from exc
        assert self._engine is not None, (
            "Something that would never happen has occurred, the program is about to exit."
        )
        return self._engine
