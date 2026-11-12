# Copyright (c) 2026-present Half_nothing.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from qbotsdk.module import SendHook

__all__ = ["ClientOptions"]


@dataclass(frozen=True, slots=True)
class ClientOptions:
    """传输层可调参数, 默认值开箱可用。"""

    # 单次请求的总超时, 含连接与读取
    timeout_total: float = 30.0
    # 连接建立超时
    timeout_connect: float = 10.0
    # WebSocket 关闭握手等对端 CLOSE 帧的上限
    timeout_ws_close: float = 1.0
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
    rate_limits: Mapping[Literal["group", "c2c"], float] | None = None
    # 覆盖默认日上限(条/天), 键为 "group" 与 "c2c", 0 表示不限
    daily_limits: Mapping[Literal["group", "c2c"], int] | None = None
    # 机器人级总速率(条/分钟), 只统计主动消息; None 或 0 表示不限
    global_rate_limit: float | None = None
    # 发送结果切面, 每次发送结束后回调一次; None 表示不观察
    send_hook: SendHook | None = None

    def __post_init__(self) -> None:
        """验证配置参数是否合法。"""
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")
        if self.timeout_total <= 0 or self.timeout_connect <= 0 or self.timeout_ws_close <= 0:
            raise ValueError("timeout values must be positive")
        if self.backoff_base < 0 or self.backoff_max < 0:
            raise ValueError("backoff values must not be negative")
        if self.max_retry_after < 0:
            raise ValueError("max_retry_after must not be negative")
        for scope, limit in (self.rate_limits or {}).items():
            if limit < 0:
                raise ValueError(f"rate limit for {scope} must not be negative")
        for scope, quota in (self.daily_limits or {}).items():
            if quota < 0:
                raise ValueError(f"daily limit for {scope} must not be negative")
        if self.global_rate_limit is not None and self.global_rate_limit < 0:
            raise ValueError("global rate limit must not be negative")
