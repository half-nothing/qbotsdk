# Copyright (c) 2026-present Half_nothing.

"""机器人门面：把 HTTP 资源层、网关长连接与事件分发串起来。"""

from __future__ import annotations

from asyncio import Task, create_task, gather
from collections.abc import Awaitable, Callable
from types import TracebackType

from async_event_bus import EventContext

from .api import ApiClient
from .gateway.connection import GatewayConnection
from .gateway.dispatcher import Dispatcher
from .model.event import EventModel, UnknownEvent
from .model.user import GuildUser
from .module.http_client import HTTPClient
from .options import ClientOptions


class Bot:
    def __init__(
        self,
        app_id: str,
        client_secret: str,
        *,
        options: ClientOptions | None = None,
        intents: int | None = None,
        shard: tuple[int, int] = (0, 1),
    ) -> None:
        self._http = HTTPClient(app_id, client_secret, options=options)
        self._api = ApiClient(self._http)
        self._options = options
        self._intents = intents
        self._shard = shard
        self._dispatcher = Dispatcher(api=self._api)
        self._connection: GatewayConnection | None = None
        self._tasks: set[Task[None]] = set()

    @property
    def api(self) -> ApiClient:
        return self._api

    @property
    def dispatcher(self) -> Dispatcher:
        """事件分发器, `on()` 只是它的转发。"""

        return self._dispatcher

    def on[E: EventModel](
        self, event_type: type[E]
    ) -> Callable[
        [Callable[[EventContext[E]], Awaitable[None]]],
        Callable[[EventContext[E]], Awaitable[None]],
    ]:
        """注册事件处理器, 只接受 `async def`。

        事件对象在 `ctx.event` 上; 能回复的事件类型直接提供 `reply()` 方法
        （目前是 `GroupAtMessageCreate`），没有该方法的事件就是不支持回复。
        """

        return self._dispatcher.on(event_type)

    def on_unknown(
        self,
    ) -> Callable[
        [Callable[[EventContext[UnknownEvent]], Awaitable[None]]],
        Callable[[EventContext[UnknownEvent]], Awaitable[None]],
    ]:
        """注册认不出来的事件的处理器。"""

        return self._dispatcher.on_unknown()

    async def start(self) -> None:
        """连上网关并在后台开始收事件, 立即返回。

        处理器的注册可以放在 start() 之前或之后, 不影响已经开始的事件。
        """

        if self._connection is not None:
            raise RuntimeError("bot is already started")
        connection = GatewayConnection(
            self._http,
            options=self._options,
            intents=self._intents,
            shard=self._shard,
        )
        self._connection = connection
        self._tasks = {
            create_task(connection.run()),
            create_task(self._dispatcher.run(connection.events)),
        }

    async def stop(self) -> None:
        """断开网关并停掉后台任务。

        停止后订阅会被清空, 再次 start() 需要重新注册处理器。
        """

        if self._connection is not None:
            await self._connection.close()
        for task in list(self._tasks):
            task.cancel()
        if self._tasks:
            await gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()
        self._connection = None
        await self._dispatcher.close()

    async def get_me(self) -> GuildUser:
        """已弃用：请改用 `bot.api.user.me()`，v0.3 移除。"""

        return await self._api.user.me()

    async def close(self) -> None:
        await self.stop()
        await self._http.close()

    async def __aenter__(self) -> Bot:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        await self.close()
