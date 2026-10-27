# Copyright (c) 2026-present Half_nothing.

"""Webhook 适配器：由平台回调推事件, 自己不再连网关。"""

from __future__ import annotations

from ssl import SSLContext

from qbotsdk.gateway.webhook_server import WebhookServer

from .base import Adapter, AdapterContext


class WebhookAdapter(Adapter):
    """把 HTTP 回调收进同一个分发器, 与Websocket二选一。"""

    def __init__(
        self,
        bot_secret: str,
        *,
        host: str = "0.0.0.0",
        port: int = 8443,
        path: str = "/qbotsdk",
        certfile: str | None = None,
        keyfile: str | None = None,
        ssl_context: SSLContext | None = None,
    ) -> None:
        """记录监听参数, 真正监听发生在 start()。

        Args:
            bot_secret:  机器人密钥, 用于验签与 op 13 应答。
            host:        监听地址。
            port:        监听端口, 0 表示让操作系统挑一个空闲端口。
            path:        回调路径, 管理端填的地址要与之对应。
            certfile:    证书链路径, 必须与 keyfile 成对出现。
            keyfile:     私钥路径。
            ssl_context: 现成的 SSLContext, 与 certfile/keyfile 互斥。
        """

        self._bot_secret = bot_secret
        self._host = host
        self._port = port
        self._path = path
        self._certfile = certfile
        self._keyfile = keyfile
        self._ssl_context = ssl_context
        self._server: WebhookServer | None = None

    @property
    def port(self) -> int:
        """实际监听的端口, 传 0 时要等 start() 之后才有值。"""

        if self._server is not None:
            return self._server.port
        return self._port

    async def start(self, context: AdapterContext) -> None:
        if self._server is not None:
            raise RuntimeError("webhook adapter is already started")

        server = WebhookServer(
            context.dispatcher,
            self._bot_secret,
            host=self._host,
            port=self._port,
            path=self._path,
            certfile=self._certfile,
            keyfile=self._keyfile,
            ssl_context=self._ssl_context,
        )
        await server.start()
        self._server = server
        self._port = server.port

    async def stop(self) -> None:
        if self._server is not None:
            await self._server.close()
            self._server = None
