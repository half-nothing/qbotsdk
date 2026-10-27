# Copyright (c) 2026-present Half_nothing.

from __future__ import annotations

from asyncio import sleep
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from json import JSONDecodeError, loads
from random import uniform

from aiohttp import (
    ClientError,
    ClientSession,
    ClientTimeout,
    FormData,
    TraceConfig,
    TraceRequestEndParams,
    TraceRequestExceptionParams,
    TraceRequestStartParams,
)
from loguru import logger
from yarl import URL

from ..constant import AUTHORIZATION_SCHEME, BASE_URL, TRACE_ID_HEADER
from ..exceptions import APIError, TransportError, error_code_of
from ..options import ClientOptions
from .token_manager import TokenManager

# 5xx 与网络异常无法确认服务端是否已处理, 只对有幂等语义的方法重试
_RETRYABLE_STATUS: frozenset[int] = frozenset({500, 502, 503, 504})
_RETRYABLE_METHODS: frozenset[str] = frozenset({"GET", "HEAD", "PUT", "DELETE"})

# 现成的 FormData 只能写进流一次, 重试必须能重建, 因此也接受工厂函数
FormSource = FormData | Callable[[], FormData]


def _make_form(form: FormSource) -> tuple[FormData, bool]:
    """返回 (本次要发的 FormData, 是否只能发一次)。"""

    if isinstance(form, FormData):
        # 调用方传了实例, 流已经就绪, 再发一次会报 "form data has been processed"
        return form, True
    return form(), False


async def _sleep(seconds: float) -> None:
    """可替换的等待函数：测试里 monkeypatch 掉它，避免真实等待。"""
    await sleep(seconds)


def _decode(text: str) -> object:
    """空包体返回 None；JSON 返回解析结果；其余原样返回文本。"""

    stripped = text.strip()
    if not stripped:
        return None
    try:
        return loads(stripped)
    except JSONDecodeError:
        return text


def _parse_retry_after(raw: str | None) -> float | None:
    """Retry-After 支持整数秒与 HTTP-date 两种格式。"""

    if raw is None:
        return None
    value = raw.strip()
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        pass
    try:
        when = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=UTC)
    return max(0.0, (when - datetime.now(UTC)).total_seconds())


@dataclass(frozen=True, slots=True)
class _RawResponse:
    status: int
    retry_after: str | None
    trace_id: str | None
    payload: object


# noinspection PyUnusedLocal
async def _on_request_start(
    session: ClientSession,
    trace_config_ctx: object,
    params: TraceRequestStartParams,
) -> None:
    logger.trace("HTTP --> {} {}", params.method, params.url)


# noinspection PyUnusedLocal
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


# noinspection PyUnusedLocal
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
    """传输层，超时、重试、限流与错误映射。"""

    def __init__(
        self,
        app_id: str,
        client_secret: str,
        *,
        options: ClientOptions | None = None,
    ) -> None:
        self._options = options if options is not None else ClientOptions()
        self._token_manager = TokenManager(app_id, client_secret)
        self._session: ClientSession | None = None
        self._trace_config = self._make_trace_config()

    # noinspection PyTypeChecker
    @staticmethod
    def _make_trace_config() -> TraceConfig:
        trace_config = TraceConfig()
        trace_config.on_request_start.append(_on_request_start)
        trace_config.on_request_end.append(_on_request_end)
        trace_config.on_request_exception.append(_on_request_exception)
        return trace_config

    @property
    def options(self) -> ClientOptions:
        """资源层要读限流开关与配额, 只读暴露给它们。"""

        return self._options

    async def _get_session(self) -> ClientSession:
        if self._session is not None and not self._session.closed:
            return self._session
        session = ClientSession(
            trace_configs=[self._trace_config],
            timeout=ClientTimeout(
                total=self._options.timeout_total,
                connect=self._options.timeout_connect,
            ),
        )
        self._session = session
        return session

    async def get_session(self) -> ClientSession:
        """给网关层复用同一个 ClientSession。"""

        return await self._get_session()

    async def access_token(self) -> str:
        """取当前可用的 access_token，供网关 Identify / Resume 使用。"""

        session = await self._get_session()
        return await self._token_manager.get_token(session)

    async def request(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, str | int] | None = None,
        json: Mapping[str, object] | None = None,
        form: FormSource | None = None,
    ) -> object:
        method = method.upper()
        if json is not None and form is not None:
            raise ValueError("json and form are mutually exclusive")
        attempt = 0
        auth_retried = False
        while True:
            attempt += 1
            if form is None:
                form_data: FormData | None = None
                replayable = True
            else:
                form_data, single_use = _make_form(form)
                replayable = not single_use
            try:
                raw = await self._send(method, path, params, json, form_data)
            except (ClientError, TimeoutError) as exc:
                if self._retryable(method, replayable) and attempt < self._options.max_attempts:
                    delay = self._backoff(attempt)
                    logger.trace("Network error, retrying {} in {:.2f}s: {!r}", method, delay, exc)
                    await _sleep(delay)
                    continue
                raise TransportError(
                    f"{method} {path} request failed: {exc!r}",
                    method=method,
                    path=path,
                    cause=exc,
                ) from exc

            # 401 说明缓存的 token 失效，丢弃后重试一次，仍失败才抛出
            if raw.status == 401 and not auth_retried and replayable:
                auth_retried = True
                logger.trace("Received 401, dropping cached token and retrying once")
                self._token_manager.invalidate()
                continue

            if raw.status == 429:
                retry_after = _parse_retry_after(raw.retry_after)
                if retry_after is not None and retry_after > self._options.max_retry_after:
                    logger.trace("Retry-After {:.2f}s exceeds the limit, giving up", retry_after)
                    raise self._error(method, path, raw)
                if attempt >= self._options.max_attempts:
                    raise self._error(method, path, raw)
                wait = retry_after if retry_after is not None else self._backoff(attempt)
                logger.trace("Rate limited, retrying {} in {:.2f}s", method, wait)
                await _sleep(wait)
                continue

            if (
                raw.status in _RETRYABLE_STATUS
                and self._retryable(method, replayable)
                and attempt < self._options.max_attempts
            ):
                delay = self._backoff(attempt)
                logger.trace(
                    "Server returned {}, retrying {} in {:.2f}s", raw.status, method, delay
                )
                await _sleep(delay)
                continue

            if raw.status >= 400:
                raise self._error(method, path, raw)

            # 201/202 表示异步成功，但仍可能带 error body，err_code 非 0 即失败
            if error_code_of(raw.payload) != 0:
                raise self._error(method, path, raw)

            return raw.payload

    async def get(
        self,
        path: str,
        *,
        params: Mapping[str, str | int] | None = None,
        json: Mapping[str, object] | None = None,
    ) -> object:
        return await self.request("GET", path, params=params, json=json)

    async def post(
        self,
        path: str,
        *,
        params: Mapping[str, str | int] | None = None,
        json: Mapping[str, object] | None = None,
    ) -> object:
        return await self.request("POST", path, params=params, json=json)

    async def put(
        self,
        path: str,
        *,
        params: Mapping[str, str | int] | None = None,
        json: Mapping[str, object] | None = None,
    ) -> object:
        return await self.request("PUT", path, params=params, json=json)

    async def post_form(
        self,
        path: str,
        *,
        form: Callable[[], FormData],
    ) -> object:
        """发 `multipart/form-data`。传工厂而不是实例: 每次重试都要一份新的流。"""

        return await self.request("POST", path, form=form)

    async def _send(
        self,
        method: str,
        path: str,
        params: Mapping[str, str | int] | None,
        json: Mapping[str, object] | None,
        form: FormData | None = None,
    ) -> _RawResponse:
        session = await self._get_session()
        token = await self._token_manager.get_token(session)
        # 鉴权头格式固定为 "QQBot <token>"
        headers = {"Authorization": f"{AUTHORIZATION_SCHEME} {token}"}
        # 用 yarl 拼接 URL, 避免字符串拼接的斜杠/编码问题；path 前导斜杠会被 yarl 拒绝
        url = URL(BASE_URL) / path.lstrip("/")
        logger.trace("Request {} {} body={} form={}", method, url, json, form is not None)
        async with session.request(
            method,
            url,
            params=params,
            json=json,
            data=form,
            headers=headers,
        ) as resp:
            payload = None if resp.status == 204 else _decode(await resp.text())
            logger.trace("Response {} {} status={} body={}", method, url, resp.status, payload)
            return _RawResponse(
                status=resp.status,
                retry_after=resp.headers.get("Retry-After"),
                trace_id=resp.headers.get(TRACE_ID_HEADER),
                payload=payload,
            )

    def _retryable(self, method: str, replayable: bool) -> bool:
        """POST 默认不重试; 打开 `retry_post` 且包体可重建时才允许。"""

        if method in _RETRYABLE_METHODS:
            return True
        return method == "POST" and self._options.retry_post and replayable

    @staticmethod
    def _error(method: str, path: str, raw: _RawResponse) -> APIError:
        error = APIError.from_response(
            raw.status,
            raw.payload,
            trace_id=raw.trace_id,
            method=method,
            path=path,
        )
        logger.error(
            "API error method={} path={} status={} code={} trace_id={}",
            method,
            path,
            error.status,
            error.code,
            error.trace_id,
        )
        return error

    def _backoff(self, attempt: int) -> float:
        """指数退避 + 0~25% 抖动，避免多实例同时重试。"""

        base_delay = float(
            min(
                self._options.backoff_base * (2 ** (attempt - 1)),
                self._options.backoff_max,
            )
        )
        return base_delay * (1 + float(uniform(0.0, 0.25)))

    async def close(self) -> None:
        if self._session is not None and not self._session.closed:
            await self._session.close()
        self._session = None
