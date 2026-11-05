# Copyright (c) 2026-present Half_nothing.

"""主动消息的本地限流。

三层限制叠在一起用:

- 每个会话的令牌桶, 限制每分钟条数;
- 每个会话的每日配额, 对齐平台的单群/单聊日上限;
- 机器人级令牌桶, 所有主动消息共用一个桶。

被动回复只走前两层, 不占机器人级额度, 避免正常回复被主动消息的配额拖住。
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from time import monotonic

from qbotsdk.exceptions import RateLimitExceededError

# 官方给出的默认值, 单位为条/分钟
DEFAULT_LIMITS: dict[str, float] = {"group": 20.0, "c2c": 20.0}

# 平台的日上限, 单位为条/天; 0 表示不限
DEFAULT_DAILY_LIMITS: dict[str, int] = {"group": 1000, "c2c": 1000}

# 桶的数量上限, 防止长期运行把每个会话都留一个桶在内存里
_MAX_BUCKETS = 4096


def _seconds_until_tomorrow() -> float:
    now = datetime.now()
    tomorrow = datetime.combine(now.date() + timedelta(days=1), time.min)
    return max(0.0, (tomorrow - now).total_seconds())


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

    def wait_time(self) -> float:
        """还差几个令牌, 折算成需要等待的秒数; 够用返回 0。"""

        self._refill_now()
        if self._tokens >= 1.0:
            return 0.0
        return (1.0 - self._tokens) / self._refill

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


@dataclass(slots=True)
class _DayCounter:
    day: date
    used: int = 0


class RateLimiter:
    """按 (scope, key) 分桶的限流器, 同时维护每日配额与机器人级总速率。

    scope 默认是 ``group`` 与 ``c2c``。``limits`` 覆盖每分钟条数,
    ``daily_limits`` 覆盖每日条数, ``global_rate`` 是机器人级每分钟条数,
    只对 ``active=True`` 的主动消息计数。
    """

    def __init__(
        self,
        limits: Mapping[str, float] | None = None,
        *,
        daily_limits: Mapping[str, int] | None = None,
        global_rate: float | None = None,
        clock: Callable[[], float] = monotonic,
        today: Callable[[], date] = date.today,
    ) -> None:
        merged = dict(DEFAULT_LIMITS)
        if limits:
            merged.update(limits)
        for scope, limit in merged.items():
            if limit < 0:
                raise ValueError(f"rate limit for {scope} must not be negative")

        merged_daily = dict(DEFAULT_DAILY_LIMITS)
        if daily_limits:
            merged_daily.update(daily_limits)
        for scope, quota in merged_daily.items():
            if quota < 0:
                raise ValueError(f"daily limit for {scope} must not be negative")

        if global_rate is not None and global_rate < 0:
            raise ValueError("global rate limit must not be negative")

        self._limits = merged
        self._daily_limits = merged_daily
        self._clock = clock
        self._today = today
        self._buckets: dict[tuple[str, str], TokenBucket] = {}
        self._daily: dict[tuple[str, str], _DayCounter] = {}
        self._global = TokenBucket(global_rate, clock=clock) if global_rate else None

    @property
    def global_bucket(self) -> TokenBucket | None:
        return self._global

    def limit_of(self, scope: str) -> float:
        return self._limits.get(scope, 0.0)

    def daily_limit_of(self, scope: str) -> int:
        return self._daily_limits.get(scope, 0)

    def _bucket_for(self, scope: str, key: str, limit: float) -> TokenBucket:
        bucket = self._buckets.get((scope, key))
        if bucket is None:
            if len(self._buckets) >= _MAX_BUCKETS:
                # 超出上限就丢掉最早建立的那个桶, 代价是该会话重新计一个整窗
                self._buckets.pop(next(iter(self._buckets)))
            bucket = TokenBucket(limit, clock=self._clock)
            self._buckets[(scope, key)] = bucket
        return bucket

    def _counter_for(self, scope: str, key: str) -> _DayCounter:
        counter = self._daily.get((scope, key))
        if counter is None:
            if len(self._daily) >= _MAX_BUCKETS:
                self._daily.pop(next(iter(self._daily)))
            counter = _DayCounter(day=self._today())
            self._daily[(scope, key)] = counter
        elif counter.day != self._today():
            counter.day = self._today()
            counter.used = 0
        return counter

    def acquire(
        self, scope: str, key: str, *, active: bool = True
    ) -> tuple[float | None, float, str]:
        """检查三层限制, 全部通过才扣减, 返回 ``(等待秒数, 限额, 窗口)``。

        不需要等待时秒数为 ``None``, 窗口为 ``""``。为了让「检查」与「扣减」
        不互相污染, 这里先分别看剩余量, 都够再一起扣。
        """

        limit = self._limits.get(scope, 0.0)
        bucket = self._bucket_for(scope, key, limit) if limit > 0 else None
        if bucket is not None:
            wait = bucket.wait_time()
            if wait > 0:
                return wait, limit, "minute"

        daily = self.daily_limit_of(scope)
        counter: _DayCounter | None = None
        if daily > 0:
            counter = self._counter_for(scope, key)
            if counter.used >= daily:
                return _seconds_until_tomorrow(), float(daily), "day"

        if active and self._global is not None:
            wait = self._global.wait_time()
            if wait > 0:
                return wait, self._global.capacity, "bot"

        if bucket is not None:
            bucket.take()
        if counter is not None:
            counter.used += 1
        if active and self._global is not None:
            self._global.take()
        return None, limit, ""

    def remaining(self, scope: str, key: str) -> float | None:
        """当前这一分钟还能发多少条; scope 不限流时返回 ``None``。"""

        limit = self._limits.get(scope, 0.0)
        if limit <= 0:
            return None
        bucket = self._buckets.get((scope, key))
        if bucket is None:
            return limit
        return bucket.peek()

    def daily_remaining(self, scope: str, key: str) -> int | None:
        """当前这一天还能发多少条; scope 没有日配额时返回 ``None``。"""

        daily = self.daily_limit_of(scope)
        if daily <= 0:
            return None
        counter = self._daily.get((scope, key))
        if counter is None or counter.day != self._today():
            return daily
        return max(0, daily - counter.used)

    def check(self, scope: str, key: str, *, active: bool = True) -> None:
        """有额度就扣一个, 没额度抛 RateLimitExceededError。

        scope 没有配置或配额为 0 时视为不限流。
        """

        wait, limit, window = self.acquire(scope, key, active=active)
        if wait is not None:
            raise RateLimitExceededError(scope, key, wait, limit=limit, window=window)
