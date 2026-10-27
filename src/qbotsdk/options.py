# Copyright (c) 2026-present Half_nothing.

from __future__ import annotations

from collections.abc import Mapping
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
    # POST 是否参与 5xx 与网络异常重试
    retry_post: bool = False
    # 主动消息是否走本地令牌桶; 关掉就完全交给服务端频控
    respect_rate_limits: bool = True
    # 覆盖默认限流(条/分钟), 键为 "group" 与 "c2c", 0 表示不限
    rate_limits: Mapping[str, float] | None = None

    def __post_init__(self) -> None:
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")
        if self.timeout_total <= 0 or self.timeout_connect <= 0:
            raise ValueError("timeout values must be positive")
        if self.backoff_base < 0 or self.backoff_max < 0:
            raise ValueError("backoff values must not be negative")
        if self.max_retry_after < 0:
            raise ValueError("max_retry_after must not be negative")
        for scope, limit in (self.rate_limits or {}).items():
            if limit < 0:
                raise ValueError(f"rate limit for {scope} must not be negative")
