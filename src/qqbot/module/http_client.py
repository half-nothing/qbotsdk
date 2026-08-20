from __future__ import annotations

from collections.abc import Mapping

from aiohttp import ClientSession
from yarl import URL

from ..constant import AUTHORIZATION_SCHEME, BASE_URL
from .token_manager import TokenManager


class APIError(Exception):
    def __init__(self, status: int, message: str, code: int | str | None = None) -> None:
        self.status = status
        self.code = code
        super().__init__(f"QQ API error {status} (code={code}): {message}")

    @classmethod
    def from_response(cls, status: int, data: object) -> "APIError":
        if isinstance(data, dict):
            return cls(status=status, message=str(data.get("message", "")), code=data.get("code"))
        return cls(status=status, message=str(data))


class HTTPClient:
    def __init__(self, app_id: str, client_secret: str) -> None:
        self._token_manager = TokenManager(app_id, client_secret)
        self._session: ClientSession | None = None

    async def _get_session(self) -> ClientSession:
        if self._session is not None and not self._session.closed:
            return self._session
        session = ClientSession()
        self._session = session
        return session

    async def request(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, str | int] | None = None,
        json: Mapping[str, object] | None = None,
    ) -> object:
        session = await self._get_session()
        token = await self._token_manager.get_token(session)
        # 鉴权头格式固定为 "QQBot <token>"
        headers = {
            "Authorization": f"{AUTHORIZATION_SCHEME} {token}"
        }
        # 用 yarl 拼接 URL，避免字符串拼接的斜杠/编码问题；path 前导斜杠会被 yarl 拒绝
        url = URL(BASE_URL) / path.lstrip("/")
        async with session.request(
                method,
                url,
                params=params,
                json=json,
                headers=headers,
        ) as resp:
            data = await resp.json()
            if resp.status >= 400:
                raise APIError.from_response(resp.status, data)
            return data

    async def close(self) -> None:
        if self._session is not None and not self._session.closed:
            await self._session.close()
        self._session = None
