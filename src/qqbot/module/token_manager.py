# Copyright (c) 2026-present Half_nothing.

from __future__ import annotations

from asyncio import Lock
from time import monotonic

from aiohttp import ClientSession
from loguru import logger

from ..constant import TOKEN_URL
from ..model.token import Token

# 提前 60s 刷新：平台只在旧 token 到期前 60s 内才签发新 token，且旧 token 在这 60s 内仍有效
_REFRESH_BUFFER_SECONDS = 60


class TokenManager:
    """Fetch and cache the app access token.

    A new token is only issued by the platform when the old one is within 60
    seconds of expiry, so refresh is triggered early under a lock to keep
    concurrent callers from stampeding the token endpoint.
    """

    def __init__(self, app_id: str, client_secret: str) -> None:
        self._app_id = app_id
        self._client_secret = client_secret
        self._access_token: str | None = None
        self._expire_at: float = 0.0
        self._lock = Lock()

    async def get_token(self, session: ClientSession) -> str:
        cached = self._get_cached()
        if cached is not None:
            return cached

        # 双检锁：进入锁后再查一次，避免并发协程重复请求凭证接口
        async with self._lock:
            cached = self._get_cached()
            if cached is not None:
                return cached
            token = await self._fetch(session)
            self._access_token = token.access_token
            self._expire_at = monotonic() + token.expires_in - _REFRESH_BUFFER_SECONDS
            return token.access_token

    def _get_cached(self) -> str | None:
        if self._access_token is None:
            return None
        if monotonic() >= self._expire_at:
            return None
        return self._access_token

    async def _fetch(self, session: ClientSession) -> Token:
        logger.trace("获取 access_token")
        async with session.post(
                TOKEN_URL,
                json={"appId": self._app_id, "clientSecret": self._client_secret},
        ) as resp:
            resp.raise_for_status()
            data = await resp.json()
            token = Token.model_validate(data)
            # 打印完整返回值，方便排查；access_token 属于凭证，仅 TRACE 级别输出
            logger.trace("access_token 响应: {} (有效期 {}s)", data, token.expires_in)
            return token
