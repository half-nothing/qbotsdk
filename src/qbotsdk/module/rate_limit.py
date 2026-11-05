# Copyright (c) 2026-present Half_nothing.

"""主动消息的本地令牌桶。"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from time import monotonic

from qbotsdk.exceptions import RateLimitExceededError

# 官方给出的默认值
DEFAULT_LIMITS: dict[str, float] = {"group": 20.0, "c2c": 20.0}

# 桶的数量上限, 防止长期运行把每个会话都留一个桶在内存里
_MAX_BUCKETS = 4096


class TokenBucket:
    """以每分钟条数为容量的令牌桶, 允许一分钟的突发。"""

    __slots__ = ("_capacity", "_clock", "_refill", "_tokens", "_updated")

    def __init__(
        self,
        capacity: float,
        *,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        if capacity <= 0:
            raise ValueError("capacity must be positive")
        self._capacity = capacity
        # 容量是每分钟条数, 因此每秒回填 capacity / 60
        self._refill = capacity / 60.0
        self._clock = clock
        self._tokens = capacity
        self._updated = clock()

    @property
    def capacity(self) -> float:
        return self._capacity

    def _refill_now(self) -> None:
        now = self._clock()
        elapsed = now - self._updated
        if elapsed > 0:
            self._tokens = min(self._capacity, self._tokens + elapsed * self._refill)
            self._updated = now

    def take(self) -> float | None:
        """取一个令牌。

        成功返回None
        取不到返回还需要等待的秒数
        """

        self._refill_now()
        if self._tokens >= 1.0:
            self._tokens -= 1.0
            return None
        return (1.0 - self._tokens) / self._refill

    def peek(self) -> float:
        """看一眼当前可用令牌, 不扣减。"""

        self._refill_now()
        return self._tokens


class RateLimiter:
    """按 (scope, key) 分桶的限流器, 默认 scope 是 group 与 c2c。"""

    def __init__(
        self,
        limits: Mapping[str, float] | None = None,
        *,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        merged = dict(DEFAULT_LIMITS)
        if limits:
            merged.update(limits)
        for scope, limit in merged.items():
            if limit < 0:
                raise ValueError(f"rate limit for {scope} must not be negative")
        self._limits = merged
        self._clock = clock
        self._buckets: dict[tuple[str, str], TokenBucket] = {}

    def limit_of(self, scope: str) -> float:
        return self._limits.get(scope, 0.0)

    def acquire(self, scope: str, key: str) -> tuple[float | None, float]:
        """取一个令牌, 返回 ``(需要等待的秒数, 该 scope 的限额)``。

        无需等待时秒数为 ``None``; scope 没有配置或配额为 0 时视为不限流, 返回
        ``(None, 0.0)``, 调用方据此放行。
        """

        limit = self._limits.get(scope, 0.0)
        if limit <= 0:
            return None, limit
        bucket = self._buckets.get((scope, key))
        if bucket is None:
            if len(self._buckets) >= _MAX_BUCKETS:
                # 超出上限就丢掉最早建立的那个桶, 代价是该会话重新计一个整窗
                self._buckets.pop(next(iter(self._buckets)))
            bucket = TokenBucket(limit, clock=self._clock)
            self._buckets[(scope, key)] = bucket
        return bucket.take(), limit

    def remaining(self, scope: str, key: str) -> float | None:
        """当前还能发多少条; scope 不限流时返回 ``None``。"""

        limit = self._limits.get(scope, 0.0)
        if limit <= 0:
            return None
        bucket = self._buckets.get((scope, key))
        if bucket is None:
            return limit
        return bucket.peek()

    def check(self, scope: str, key: str) -> None:
        """有额度就扣一个, 没额度抛 RateLimitExceededError。

        scope 没有配置或配额为 0 时视为不限流。
        """

        wait, limit = self.acquire(scope, key)
        if wait is not None:
            raise RateLimitExceededError(scope, key, wait, limit=limit)
