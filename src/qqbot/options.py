# Copyright (c) 2026-present Half_nothing.

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ClientOptions:
    """传输层可调参数, 默认值开箱可用。"""

    # 单次请求的总超时, 含连接与读取
    timeout_total: float = 30.0
    # 连接建立超时
    timeout_connect: float = 10.0
    # 含首次请求在内的最大尝试次数
    max_attempts: int = 3
    # 指数退避基数, 实际等待为 base * 2 ** (attempt - 1)
    backoff_base: float = 0.5
    # 退避上限
    backoff_max: float = 8.0
    # 429 的 Retry-After 超过此值就放弃, 不阻塞调用方
    max_retry_after: float = 30.0

    def __post_init__(self) -> None:
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")
        if self.timeout_total <= 0 or self.timeout_connect <= 0:
            raise ValueError("timeout values must be positive")
        if self.backoff_base < 0 or self.backoff_max < 0:
            raise ValueError("backoff values must not be negative")
        if self.max_retry_after < 0:
            raise ValueError("max_retry_after must not be negative")
