# Copyright (c) 2026-present Half_nothing.

from __future__ import annotations

from enum import IntEnum

# 错误体里只有 err_code 稳定, message 会变, 因此判定一律看 err_code
_BODY_PREVIEW_LIMIT = 2048

# 官方明确说明可重试的错误码
RETRYABLE_CODES: frozenset[int] = frozenset(
    {11252, 11262, 11263, 11281, 50055001, 850027, 40093001}
)

# 按区间归类的错误码, 用于提示不枚举具体值
ERROR_CODE_RANGES: dict[tuple[int, int], str] = {
    (301000, 301099): "sub-channel permission error",
}


class ErrorCode(IntEnum):
    """本阶段收录的官方错误码。

    这是便利集合而不是白名单，未知错误码保留原值，不因不在表里就丢弃。
    """

    UNKNOWN_ACCOUNT = 10001
    UNKNOWN_CHANNEL = 10003
    UNKNOWN_GUILD = 10004
    ERROR_WRONG_TOKEN = 11241
    ERROR_CHECK_TOKEN_NOT_PASS = 11243
    ERROR_WRONG_APPID = 11251
    ERROR_CHECK_SYSTEM = 11252
    ERROR_CHECK_APP_PRIVILEGE_NOT_PASS = 11253
    ERROR_WRONG_APPID_2 = 11261
    ERROR_CHECK_SYSTEM_2 = 11262
    ERROR_CHECK_SYSTEM_3 = 11263
    ERROR_GUILD_AUTH_NOT_PASS = 11264
    ERROR_ROBOT_HAS_BANNED = 11265
    ERROR_WRONG_APPID_3 = 11275
    ERROR_CHECK_SYSTEM_4 = 11281
    ERROR_CHECK_ADMIN_NOT_PASS = 11282
    REQUEST_INVALID = 12002
    CHANNEL_HIT_WRITE_RATE_LIMIT = 20028
    CHANNEL_MESSAGE_SUBMITTED_FOR_REVIEW = 40034120


def describe_code(code: int) -> str:
    """给错误码一个可读标签, 未知码返回空串。"""

    try:
        return ErrorCode(code).name
    except ValueError:
        pass
    for (low, high), label in ERROR_CODE_RANGES.items():
        if low <= code <= high:
            return label
    return ""


class QQBotError(Exception):
    """SDK 所有异常的基类。"""


class TransportError(QQBotError):
    """没有拿到 HTTP 响应，连接失败、DNS 失败、读写超时"""

    def __init__(
        self,
        message: str,
        *,
        method: str = "",
        path: str = "",
        cause: BaseException | None = None,
    ) -> None:
        super().__init__(message)
        self.method = method
        self.path = path
        self.cause = cause


class APIError(QQBotError):
    """拿到了 HTTP 响应但请求失败。"""

    def __init__(
        self,
        status: int,
        message: str,
        code: int | str | None = None,
        *,
        trace_id: str | None = None,
        method: str = "",
        path: str = "",
        body: object = None,
    ) -> None:
        self.status = status
        self.message = message
        self.code = code
        self.trace_id = trace_id
        self.method = method
        self.path = path
        self.body = body
        super().__init__(f"QQ API error {status} (code={code}, trace_id={trace_id}): {message}")

    @classmethod
    def from_response(
        cls,
        status: int,
        data: object,
        *,
        trace_id: str | None = None,
        method: str = "",
        path: str = "",
    ) -> APIError:
        payload = data if isinstance(data, dict) else {}
        code = error_code_of(data)
        message = str(payload.get("message", "") or f"HTTP {status}")
        return cls(
            status=status,
            message=message,
            code=code,
            trace_id=trace_id or _as_str(payload.get("trace_id")),
            method=method,
            path=path,
            body=_preview(data),
        )

    @property
    def retryable(self) -> bool:
        """系统类错误码或 5xx 视为可重试。"""

        return self.status >= 500 or _as_int(self.code) in RETRYABLE_CODES

    @property
    def code_name(self) -> str:
        return describe_code(_as_int(self.code))


def _as_int(value: object) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return 0


def _as_str(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _preview(data: object) -> object:
    """错误体只留 2KB 预览, 避免大响应体长期挂在异常对象上。"""

    if data is None:
        return None
    text = data if isinstance(data, str) else repr(data)
    return text if len(text) <= _BODY_PREVIEW_LIMIT else text[:_BODY_PREVIEW_LIMIT] + "…"


def error_code_of(payload: object) -> int:
    """取响应体里的业务错误码，取不到时返回 0。

    凭证接口与 REST 接口都用它判定「HTTP 200 但业务失败」的情形。
    """

    if not isinstance(payload, dict):
        return 0
    return _as_int(payload.get("err_code", payload.get("code", 0)))
