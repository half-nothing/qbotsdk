# Copyright (c) 2026-present Half_nothing.

from __future__ import annotations

from collections.abc import Mapping

from aiohttp import (
    ClientSession,
    TraceConfig,
    TraceRequestEndParams,
    TraceRequestExceptionParams,
    TraceRequestStartParams,
)
from loguru import logger
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


async def _on_request_start(
        session: ClientSession,
        trace_config_ctx: object,
        params: TraceRequestStartParams,
) -> None:
    logger.trace("HTTP --> {} {}", params.method, params.url)


async def _on_request_end(
        session: ClientSession,
        trace_config_ctx: object,
        params: TraceRequestEndParams,
) -> None:
    logger.trace(
        "HTTP <-- {} {} {}",
        params.response.status,
        params.response.request_info.method,
        params.response.request_info.url,
    )


async def _on_request_exception(
        session: ClientSession,
        trace_config_ctx: object,
        params: TraceRequestExceptionParams,
) -> None:
    logger.trace(
        "HTTP !! {} {}: {!r}",
        params.method,
        params.url,
        params.exception,
    )


class HTTPClient:
    def __init__(self, app_id: str, client_secret: str) -> None:
        self._token_manager = TokenManager(app_id, client_secret)
        self._session: ClientSession | None = None
        self._trace_config = self._make_trace_config()

    @staticmethod
    def _make_trace_config() -> TraceConfig:
        trace_config = TraceConfig()
        trace_config.on_request_start.append(_on_request_start)
        trace_config.on_request_end.append(_on_request_end)
        trace_config.on_request_exception.append(_on_request_exception)
        return trace_config

    async def _get_session(self) -> ClientSession:
        if self._session is not None and not self._session.closed:
            return self._session
        session = ClientSession(trace_configs=[self._trace_config])
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
        logger.trace("请求 {} {} body={}", method, url, json)
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
            logger.trace("响应 {} {} status={} body={}", method, url, resp.status, data)
            return data

    async def close(self) -> None:
        if self._session is not None and not self._session.closed:
            await self._session.close()
        self._session = None
