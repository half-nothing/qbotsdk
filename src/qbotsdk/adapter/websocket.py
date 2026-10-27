# Copyright (c) 2026-present Half_nothing.

"""WebSocket 适配器：连上网关、维持心跳、断线续连。"""

from __future__ import annotations

from asyncio import Task, create_task, gather

from qbotsdk.gateway.connection import GatewayConnection
from qbotsdk.gateway.payload import Intents
from qbotsdk.storage import SessionStorage

from .base import Adapter, AdapterContext


class WebSocketAdapter(Adapter):
    """用Websocket收事件。"""

    def __init__(
        self,
        *,
        intents: int | None = None,
        shard: tuple[int, int] = (0, 1),
        session_storage: SessionStorage | None = None,
    ) -> None:
        """记录连接参数, 真正连接发生在 start()。

        Args:
            intents:         订阅的事件位, 不传用 Intents.DEFAULT。
            shard:           (分片序号, 分片总数), 单连接保持默认即可。
            session_storage: 会话存储, 不传则用内存实现。
        """

        self._intents = intents if intents is not None else Intents.DEFAULT
        self._shard = shard
        self._storage = session_storage
        self._connection: GatewayConnection | None = None
        self._tasks: set[Task[None]] = set()

    async def start(self, context: AdapterContext) -> None:
        if self._connection is not None:
            raise RuntimeError("websocket adapter is already started")

        connection = GatewayConnection(
            context.http,
            options=context.http.options,
            intents=self._intents,
            shard=self._shard,
            session_storage=self._storage,
        )
        self._connection = connection
        self._tasks = {
            create_task(connection.run()),
            create_task(context.dispatcher.run(connection.events)),
        }

    async def stop(self) -> None:
        if self._connection is not None:
            await self._connection.close()
        for task in list(self._tasks):
            task.cancel()
        if self._tasks:
            await gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()
        self._connection = None
