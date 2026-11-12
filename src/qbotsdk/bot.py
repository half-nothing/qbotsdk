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

"""
机器人门面, 组装各模块并对外提供接口

把 HTTP 资源层与事件分发串起来, 接入方式由适配器决定。
"""

from __future__ import annotations

from asyncio import CancelledError, Event, get_running_loop
from collections.abc import Awaitable, Callable, Iterable
from contextlib import suppress
from signal import SIGINT, SIGTERM, signal
from types import FrameType, TracebackType
from typing import Any

from async_event_bus import EventContext

from .adapter import Adapter, AdapterContext, WebSocketAdapter
from .api import ApiClient
from .gateway import Dispatcher
from .model import EventModel, UnknownEvent
from .module import HttpClient
from .options import ClientOptions

__all__ = ["Bot"]


class Bot:
    """默认用 WebSocket 长连接收事件, 换接入方式显示传递 `adapter=`。

    ```python
    bot = Bot(app_id, app_secret)  # 等价于 adapter=WebSocketAdapter()
    bot = Bot(app_id, app_secret, adapter=WebhookAdapter(...))
    ```
    """

    def __init__(
        self,
        app_id: str,
        app_secret: str,
        *,
        adapter: Adapter | None = None,
        options: ClientOptions | None = None,
    ) -> None:
        """创建门面, 不做任何网络操作。

        :param app_id:        机器人 AppID。
        :param app_secret:    机器人 AppSecret。
        :param adapter:       接入方式, 不传用 WebSocketAdapter()。
        :param options:       客户端配置, 见 ClientOptions。
        """

        self._http = HttpClient(app_id, app_secret, options=options)
        self._api = ApiClient(self._http)
        self._adapter: Adapter = adapter if adapter is not None else WebSocketAdapter()
        self._dispatcher = Dispatcher(api=self._api)
        self._started = False

    @property
    def api(self) -> ApiClient:
        return self._api

    @property
    def adapter(self) -> Adapter:
        return self._adapter

    @property
    def dispatcher(self) -> Dispatcher:
        """事件分发器, ``on()`` 只是它的转发。"""

        return self._dispatcher

    def on[E: EventModel](
        self, event_type: type[E]
    ) -> Callable[
        [Callable[[EventContext[E]], Awaitable[None]]],
        Callable[[EventContext[E]], Awaitable[None]],
    ]:
        """注册事件处理器, 只接受异步函数。

        事件对象在 `ctx.event` 上, 支持回复的事件类型直接提供 `reply()` 方法

        目前支持回复的事件如下:
            - `GroupAtMessageCreate`
            - `C2CMessageCreate`
            - `ChannelMessageCreate`

        互动事件提供`respond()`方法, 用于响应事件

        两个方法都没有的事件就是不支持回复。
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
        """让适配器开始收事件, 立即返回。

        处理器的注册放在调用start()前后均可

        :raise RuntimeError: 重复调用时抛出
        """

        if self._started:
            raise RuntimeError("bot is already started")

        await self._adapter.start(
            AdapterContext(http=self._http, api=self._api, dispatcher=self._dispatcher)
        )
        self._started = True

    async def stop(self) -> None:
        """停掉适配器并清空事件订阅。

        停止后订阅会被清空, 需要重新注册处理器。
        """

        if self._started:
            await self._adapter.stop()
        self._started = False
        await self._dispatcher.close()

    async def run(
        self,
        *,
        signals: Iterable[int] = (SIGINT, SIGTERM),
    ) -> None:
        """启动并阻塞, 直到收到退出信号。"""

        await self.start()
        try:
            await self.wait_for_exit(signals=signals)
        finally:
            await self.stop()

    @staticmethod
    async def wait_for_exit(
        *,
        signals: Iterable[int] = (SIGINT, SIGTERM),
    ) -> None:
        """阻塞直到收到任一退出信号。"""

        loop = get_running_loop()
        stopped = Event()
        handled: list[int] = []
        restores: list[tuple[int, Any]] = []

        def on_signal(_signum: int, _frame: FrameType | None) -> None:
            loop.call_soon_threadsafe(stopped.set)

        for sig in signals:
            try:
                loop.add_signal_handler(sig, stopped.set)
            except (NotImplementedError, RuntimeError, ValueError):
                try:
                    restores.append((sig, signal(sig, on_signal)))
                except (OSError, ValueError):
                    continue
            else:
                handled.append(sig)

        if not handled and not restores:
            raise RuntimeError(
                "wait_for_exit() must run in the main thread to receive exit signals"
            )

        try:
            with suppress(KeyboardInterrupt, CancelledError):
                await stopped.wait()
        finally:
            for sig in handled:
                loop.remove_signal_handler(sig)
            for sig, previous in restores:
                signal(sig, previous)

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
