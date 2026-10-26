# Copyright (c) 2026-present Half_nothing.

from __future__ import annotations

from types import TracebackType

from .api import ApiClient
from .model.user import User
from .module.http_client import HTTPClient
from .options import ClientOptions


class Bot:
    def __init__(
        self,
        app_id: str,
        client_secret: str,
        *,
        options: ClientOptions | None = None,
    ) -> None:
        self._http = HTTPClient(app_id, client_secret, options=options)
        self._api = ApiClient(self._http)

    @property
    def api(self) -> ApiClient:
        """四个资源域：`api.user` / `api.guild` / `api.channel` / `api.message`。"""

        return self._api

    async def get_me(self) -> User:
        """已弃用：请改用 `bot.api.user.me()`，v0.3 移除。"""

        return await self._api.user.me()

    async def close(self) -> None:
        await self._http.close()

    async def __aenter__(self) -> Bot:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        await self.close()
