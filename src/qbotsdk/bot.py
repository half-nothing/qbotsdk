# Copyright (c) 2026-present Half_nothing.

"""机器人门面：把 HTTP 资源层与事件分发串起来, 接入方式由适配器决定。"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from types import TracebackType

from async_event_bus import EventContext

from .adapter.base import Adapter, AdapterContext
from .adapter.websocket import WebSocketAdapter
from .api import ApiClient
from .gateway.dispatcher import Dispatcher
from .model.event import EventModel, UnknownEvent
from .model.user import GuildUser
from .module.http_client import HTTPClient
from .options import ClientOptions


class Bot:
    """默认用 WebSocket 长连接收事件，换接入方式就传 `adapter=`。

    ```python
    bot = Bot(app_id, client_secret)  # 等价于 adapter=WebSocketAdapter()
    bot = Bot(app_id, client_secret, adapter=WebhookAdapter(...))
    ```
    """

    def __init__(
        self,
        app_id: str,
        client_secret: str,
        *,
        adapter: Adapter | None = None,
        options: ClientOptions | None = None,
    ) -> None:
        """创建门面, 不做任何网络操作。

        Args:
            app_id:        机器人 AppID。
            client_secret: 机器人 AppSecret。
            adapter:       接入方式, 不传用 `WebSocketAdapter()`。
            options:       客户端配置, 见 `ClientOptions`。
        """

        self._http = HTTPClient(app_id, client_secret, options=options)
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
        （`GroupAtMessageCreate`/`C2CMessageCreate`/`ChannelMessageCreate`），
        互动事件用 `respond()`，没有这些方法的事件就是不支持回复。
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

        处理器的注册可以放在 start() 前后；重复调用抛 `RuntimeError`。
        """

        if self._started:
            raise RuntimeError("bot is already started")

        await self._adapter.start(
            AdapterContext(http=self._http, api=self._api, dispatcher=self._dispatcher)
        )
        self._started = True

    async def stop(self) -> None:
        """停掉适配器并清空事件订阅。

        停止后订阅会被清空, 再次 start() 需要重新注册处理器。
        """

        if self._started:
            await self._adapter.stop()
        self._started = False
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
