# Copyright (c) 2026-present Half_nothing.

from __future__ import annotations

from asyncio import Lock
from time import monotonic

from aiohttp import ClientError, ClientResponseError, ClientSession
from loguru import logger
from pydantic import ValidationError

from ..constant import BASE_URL, TOKEN_URL, TRACE_ID_HEADER
from ..exceptions import APIError, TransportError, error_code_of
from ..model.token import Token

# 提前60s刷新，平台只在旧token到期前60s内才签发新token, 且旧token在这60s内仍有效
_REFRESH_BUFFER_SECONDS = 60

# 凭证接口只认这一个 path, 出错时用来定位
_TOKEN_PATH = TOKEN_URL.removeprefix(BASE_URL)


class TokenManager:
    """获取并缓存访问令牌

    两个时间点分开记：

    - ``refresh_at``：到点后就主动换新。平台只在旧 token 到期前 60 秒内才签发新 token，
      所以正常路径下这里是「到期 - 60 秒」。
    - ``hard_expire_at``：到点后旧 token 确定不可用了。刷新失败时只要还没到这里，
      就继续用旧 token，让调用方不至于因为一次凭证抖动而失败。

    并发的第一波调用由 ``Lock`` 收敛成一次凭证请求（双检锁）。
    """

    def __init__(
        self,
        app_id: str,
        client_secret: str,
        *,
        refresh_buffer: float = _REFRESH_BUFFER_SECONDS,
    ) -> None:
        self._app_id = app_id
        self._client_secret = client_secret
        self._refresh_buffer = refresh_buffer
        self._access_token: str | None = None
        self._refresh_at: float = 0.0
        self._hard_expire_at: float = 0.0
        self._lock = Lock()

    async def get_token(self, session: ClientSession) -> str:
        cached = self._usable_token()
        if cached is not None:
            return cached

        # 双检锁，进入锁后再查一次, 避免并发协程重复请求凭证接口
        async with self._lock:
            cached = self._usable_token()
            if cached is not None:
                return cached
            return await self._refresh(session)

    def invalidate(self) -> None:
        """丢弃缓存凭证，强制下一次调用重新取 token"""

        self._access_token = None
        self._refresh_at = 0.0
        self._hard_expire_at = 0.0

    async def _refresh(self, session: ClientSession) -> str:
        try:
            token = await self._fetch(session)
        except Exception as exc:
            # 旧 token 还在硬有效期内就先用着，凭证抖动不该让整次调用失败
            stale = self._stale_token()
            if stale is not None:
                logger.warning("Token refresh failed, falling back to the cached token: {!r}", exc)
                return stale
            raise

        now = monotonic()
        # expires_in 比预留窗口还短时按半程刷新, 否则每次调用都会去打凭证接口
        window = token.expires_in - self._refresh_buffer
        if window <= 0:
            window = token.expires_in / 2
        self._access_token = token.access_token
        self._refresh_at = now + window
        self._hard_expire_at = now + token.expires_in
        return token.access_token

    def _usable_token(self) -> str | None:
        """还没到刷新点、可以直接用的 token。"""

        if self._access_token is None or monotonic() >= self._refresh_at:
            return None
        return self._access_token

    def _stale_token(self) -> str | None:
        """已过刷新点、但还在硬有效期内的 token，只用于刷新失败时兜底。"""

        if self._access_token is None or monotonic() >= self._hard_expire_at:
            return None
        return self._access_token

    async def _fetch(self, session: ClientSession) -> Token:
        logger.trace("Fetching access_token")
        try:
            async with session.post(
                TOKEN_URL,
                json={"appId": self._app_id, "clientSecret": self._client_secret},
            ) as resp:
                status = resp.status
                trace_id = resp.headers.get(TRACE_ID_HEADER)
                resp.raise_for_status()
                data = await resp.json()
        except ClientResponseError as exc:
            # 凭证接口的错误体只有 message，没有 err_code，转成统一的 APIError
            raise APIError(exc.status, exc.message, method="POST", path=_TOKEN_PATH) from exc
        except (ClientError, TimeoutError) as exc:
            raise TransportError(
                f"POST {_TOKEN_PATH} request failed: {exc!r}",
                method="POST",
                path=_TOKEN_PATH,
                cause=exc,
            ) from exc

        # 凭证接口也会用 HTTP 200 返回 err_code，不能直接交给模型校验
        if error_code_of(data) != 0:
            raise APIError.from_response(
                status,
                data,
                trace_id=trace_id,
                method="POST",
                path=_TOKEN_PATH,
            )

        try:
            token = Token.model_validate(data)
        except ValidationError as exc:
            # 200 但包体不是凭证结构，同样是上游错误，不该把 pydantic 的报错漏给调用方
            raise APIError.from_response(
                status,
                data,
                trace_id=trace_id,
                method="POST",
                path=_TOKEN_PATH,
            ) from exc

        # access_token 属于凭证, 仅 TRACE 级别输出
        logger.trace("access_token response: {} (expires in {}s)", data, token.expires_in)
        return token
