# Copyright (c) 2026-present Half_nothing.

"""消息发送前后的切面。

主动消息有官方配额, 本地令牌桶只管住了频率, 管不住「这个群 / 这个用户今天还能不能推」。
调用方实现 :class:`SendGuard` 就能拿到每次发送前后的决策点:

- ``before_send`` 返回拒绝时请求不会发出去, 调用方可以按自己的存储 (Redis / 数据库 /
  业务表) 判断主动消息是否到达限制, 并给出 ``retry_after``;
- ``after_send`` 拿到本次发送的异常 (成功时为 ``None``), 可以据此记账、冷却或告警。

默认的 :class:`LocalRateLimitGuard` 只做本地令牌桶, 不记录服务端配额, 也不假设任何
存储; 换掉它只需要给 ``ClientOptions.send_guard`` 传自己的实现。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Protocol, Self

from qbotsdk.exceptions import QQBotError, RateLimitExceededError
from qbotsdk.module.rate_limit import RateLimiter

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class SendContext:
    """一次发送的上下文。"""

    #: ``"group"`` 或 ``"c2c"``
    scope: str
    #: 群聊是 ``group_openid``, 单聊是 ``user_openid``
    target: str
    #: 是否主动消息: 既没有 ``reply_to`` 也没有 ``event_id`` 时计入主动消息配额
    active: bool
    #: 请求路径, 便于调用方按接口细分
    path: str


@dataclass(frozen=True, slots=True)
class SendVerdict:
    """``before_send`` 的判定。"""

    allowed: bool
    #: 建议等待秒数, 只有拒绝时有意义
    retry_after: float = 0.0
    #: 该 scope 的限额, 原样带进 ``RateLimitExceededError.limit``
    limit: float = 0.0
    #: 拒绝原因, 原样带进异常消息
    reason: str = ""

    @classmethod
    def allow(cls) -> Self:
        return cls(allowed=True)

    @classmethod
    def deny(cls, *, retry_after: float, reason: str = "", limit: float = 0.0) -> Self:
        return cls(allowed=False, retry_after=retry_after, limit=limit, reason=reason)


class SendGuard(Protocol):
    """发送切面, 两个方法都按需实现。"""

    async def before_send(self, context: SendContext) -> SendVerdict | None:
        """发送前判定, 返回 ``None`` 或 :meth:`SendVerdict.allow` 都表示放行。"""

        ...

    async def after_send(self, context: SendContext, error: QQBotError | None) -> None:
        """发送后回调, ``error`` 为 ``None`` 表示请求成功。"""

        ...


class LocalRateLimitGuard:
    """默认切面: 只做本地令牌桶, 不记录服务端配额。"""

    def __init__(self, limiter: RateLimiter) -> None:
        self._limiter = limiter

    @property
    def limiter(self) -> RateLimiter:
        return self._limiter

    async def before_send(self, context: SendContext) -> SendVerdict | None:
        wait, limit = self._limiter.acquire(context.scope, context.target)
        if wait is None:
            return None
        return SendVerdict.deny(
            retry_after=wait,
            limit=limit,
            reason=f"local rate limit reached for {context.scope}:{context.target}",
        )

    async def after_send(self, context: SendContext, error: QQBotError | None) -> None:
        return None


async def check_send(guard: SendGuard | None, context: SendContext) -> None:
    """执行 ``before_send``, 被拒绝时抛 :class:`RateLimitExceededError`。"""

    if guard is None:
        return
    verdict = await guard.before_send(context)
    if verdict is not None and not verdict.allowed:
        raise RateLimitExceededError(
            context.scope,
            context.target,
            verdict.retry_after,
            limit=verdict.limit,
            reason=verdict.reason or None,
        )


async def report_send(
    guard: SendGuard | None,
    context: SendContext,
    error: QQBotError | None,
) -> None:
    """执行 ``after_send``。切面自己的异常只记日志, 不覆盖发送结果。"""

    if guard is None:
        return
    try:
        await guard.after_send(context, error)
    except Exception:
        logger.exception("SendGuard.after_send failed for %s:%s", context.scope, context.target)
