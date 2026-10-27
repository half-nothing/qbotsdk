# Copyright (c) 2026-present Half_nothing.

"""事件分发。"""

from __future__ import annotations

from asyncio import Queue, Task, create_task, gather
from collections import deque
from collections.abc import Awaitable, Callable
from inspect import iscoroutinefunction
from typing import cast

from async_event_bus import EmitResult, EventBus, EventContext, ExceptionStrategy
from loguru import logger

from ..model.event import EventModel, UnknownEvent, parse_event
from .payload import GatewayPayload, OpCode

# 官方会重复推送同一个 msg_id, 所以只留最近 N 条做去重
DEFAULT_DEDUPE_SIZE = 512


class Dispatcher:
    """事件注册与派发。"""

    def __init__(
        self,
        *,
        dedupe_size: int = DEFAULT_DEDUPE_SIZE,
        max_concurrent_tasks: int = 16,
        exception_strategy: ExceptionStrategy = ExceptionStrategy.IGNORE,
    ) -> None:
        """创建分发器。

        Args:
            dedupe_size:          去重窗口大小, 0 表示关闭。
            max_concurrent_tasks: 总线同时运行的处理器上限。
            exception_strategy:   处理器抛异常时的策略, 默认记日志后继续。
        """

        if dedupe_size < 0:
            raise ValueError("dedupe_size must not be negative")
        self._bus: EventBus[EventContext[EventModel], None] = EventBus(
            max_concurrent_tasks=max_concurrent_tasks,
            exception_strategy=exception_strategy,
        )
        self._dedupe_size = dedupe_size
        self._seen: deque[str] = deque(maxlen=max(dedupe_size, 1))
        self._seen_ids: set[str] = set()
        self._tasks: set[Task[EmitResult[None] | None]] = set()

    def on[E: EventModel](
        self, event_type: type[E]
    ) -> Callable[
        [Callable[[EventContext[E]], Awaitable[None]]],
        Callable[[EventContext[E]], Awaitable[None]],
    ]:
        """注册某个事件类型的处理器。

        同一类型可以注册多个，只接受协程函数。
        """

        def register(
            handler: Callable[[EventContext[E]], Awaitable[None]],
        ) -> Callable[[EventContext[E]], Awaitable[None]]:
            if not iscoroutinefunction(handler):
                raise TypeError(f"handler for {event_type.__name__} must be an async function")
            # 总线按类建键, 但 EventBus.on 不为每个键单独收窄上下文类型, 只能在这里断言
            self._bus.on(event_type)(
                cast("Callable[[EventContext[EventModel]], Awaitable[None]]", handler)
            )
            return handler

        return register

    def on_unknown(
        self,
    ) -> Callable[
        [Callable[[EventContext[UnknownEvent]], Awaitable[None]]],
        Callable[[EventContext[UnknownEvent]], Awaitable[None]],
    ]:
        """注册未建模事件的处理器。"""

        return self.on(UnknownEvent)

    def handle(self, payload: GatewayPayload) -> None:
        """把一帧交给总线，非 dispatch 帧与重复消息直接丢弃。"""

        if payload.op is not OpCode.DISPATCH or not payload.t:
            return
        event = parse_event(payload.t, payload.d)
        if self._is_duplicate(event):
            logger.debug("Duplicate event dropped: t={}", payload.t)
            return
        task = create_task(self._bus.emit(event))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def run(self, events: Queue[GatewayPayload]) -> None:
        """消费网关连接的事件队列, 直到被取消。"""

        while True:
            self.handle(await events.get())

    async def join(self) -> None:
        """等已经排队的处理器跑完。"""

        while self._tasks:
            await gather(*list(self._tasks), return_exceptions=True)

    async def close(self) -> None:
        """取消还没跑完的处理器并清空订阅。"""

        for task in list(self._tasks):
            task.cancel()
        if self._tasks:
            await gather(*list(self._tasks), return_exceptions=True)
        self._tasks.clear()
        self._bus.clear()

    def _is_duplicate(self, event: EventModel) -> bool:
        if self._dedupe_size <= 0:
            return False
        message_id = getattr(event, "id", None)
        if not isinstance(message_id, str) or not message_id:
            return False
        if message_id in self._seen_ids:
            return True
        if len(self._seen) == self._dedupe_size:
            self._seen_ids.discard(self._seen[0])
        self._seen.append(message_id)
        self._seen_ids.add(message_id)
        return False
