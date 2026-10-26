# Copyright (c) 2026-present Half_nothing.

from __future__ import annotations

from types import TracebackType

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

    async def get_me(self) -> User:
        # 获取机器人自身信息
        data = await self._http.get("/users/@me")
        return User.model_validate(data)

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
