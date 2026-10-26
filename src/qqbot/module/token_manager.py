# Copyright (c) 2026-present Half_nothing.

from __future__ import annotations

from asyncio import Lock
from time import monotonic

from aiohttp import ClientSession
from loguru import logger

from ..constant import TOKEN_URL
from ..model.token import Token

# 提前60s刷新，平台只在旧token到期前60s内才签发新token, 且旧token在这60s内仍有效
_REFRESH_BUFFER_SECONDS = 60


class TokenManager:
    """获取并缓存访问令牌

    当旧令牌距离过期仅剩60秒时，平台才会发放新令牌
    因此在锁定机制下会提前触发刷新，以防止并发调用者同时冲击令牌端点
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

        # 双检锁，进入锁后再查一次, 避免并发协程重复请求凭证接口
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

    def invalidate(self) -> None:
        """丢弃缓存凭证，强制下一次调用重新取 token"""

        self._access_token = None
        self._expire_at = 0.0

    async def _fetch(self, session: ClientSession) -> Token:
        logger.trace("Fetching access_token")
        async with session.post(
            TOKEN_URL,
            json={"appId": self._app_id, "clientSecret": self._client_secret},
        ) as resp:
            resp.raise_for_status()
            data = await resp.json()
            token = Token.model_validate(data)
            # 打印完整返回值, 方便排查
            # access_token 属于凭证, 仅 TRACE 级别输出
            logger.trace("access_token response: {} (expires in {}s)", data, token.expires_in)
            return token
