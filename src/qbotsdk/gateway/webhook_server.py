# Copyright (c) 2026-present Half_nothing.

"""开箱即用的 Webhook 服务器。"""

from __future__ import annotations

from ssl import PROTOCOL_TLS_SERVER, SSLContext
from typing import TYPE_CHECKING

from aiohttp.web import Application, AppRunner, TCPSite
from loguru import logger

from .handler import build_webhook_handler

if TYPE_CHECKING:
    from .dispatcher import Dispatcher

# 平台允许在管理端配置的回调端口
CALLBACK_PORTS = frozenset({80, 443, 8080, 8443})

# 明文监听这些端口时大概率是忘了配证书
_TLS_PORTS = frozenset({443, 8443})


class WebhookServer:
    """把事件回调转发给分发器。

    一般通过 `WebhookAdapter` 使用, 也可以用这个低层实现接进自己的 aiohttp 应用：

    ```python
    server = WebhookServer(bot.dispatcher, "secret", certfile="cert.pem", keyfile="key.pem")
    await server.start()
    ...
    await server.close()
    ```
    """

    def __init__(
        self,
        dispatcher: Dispatcher,
        app_secret: str,
        *,
        host: str = "0.0.0.0",
        port: int = 8443,
        path: str = "/qbotsdk",
        certfile: str | None = None,
        keyfile: str | None = None,
        ssl_context: SSLContext | None = None,
    ) -> None:
        """创建服务器，但先不监听。

        Args:
            dispatcher: 事件最终交给它分发。
            app_secret: 机器人密钥，用于验签与 op 13 应答。
            host:       监听地址。
            port:       监听端口，0 表示让操作系统挑一个空闲端口。
            path:       回调路径。
            certfile:   证书链路径，必须与 keyfile 成对出现。
            keyfile:    私钥路径。
            ssl_context: 现成的 SSLContext，与 certfile/keyfile 互斥。
        """

        if (certfile is None) != (keyfile is None):
            raise ValueError("certfile and keyfile must be provided together")
        if ssl_context is not None and certfile is not None:
            raise ValueError("ssl_context cannot be combined with certfile and keyfile")

        self._dispatcher = dispatcher
        self._app_secret = app_secret
        self._handler = build_webhook_handler(dispatcher, app_secret)
        self._host = host
        self._port = port
        self._path = path
        self._ssl_context = _build_ssl_context(certfile, keyfile, ssl_context)
        self._runner: AppRunner | None = None
        self._site: TCPSite | None = None

    @property
    def port(self) -> int:
        """实际监听的端口，port=0 时在 start() 之后才有意义。"""

        return self._port

    @property
    def url(self) -> str:
        """本机访问地址，只用于日志与测试。"""

        scheme = "https" if self._ssl_context is not None else "http"
        return f"{scheme}://{self._host}:{self._port}{self._path}"

    async def start(self) -> None:
        """开始监听，立即返回。"""

        if self._runner is not None:
            raise RuntimeError("webhook server is already started")

        app = Application()
        app.router.add_post(self._path, self._handler)
        runner = AppRunner(app)
        await runner.setup()
        site = TCPSite(runner, self._host, self._port, ssl_context=self._ssl_context)
        try:
            await site.start()
        except OSError:
            await runner.cleanup()
            raise

        self._runner = runner
        self._site = site
        self._port = _bound_port(site, self._port)
        logger.info("Webhook server listening on {}", self.url)
        self._warn_about_port()

    async def close(self) -> None:
        """停止监听并释放端口。"""

        if self._site is not None:
            await self._site.stop()
            self._site = None
        if self._runner is not None:
            await self._runner.cleanup()
            self._runner = None

    async def __aenter__(self) -> WebhookServer:
        await self.start()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: object | None,
    ) -> None:
        await self.close()

    def _warn_about_port(self) -> None:
        if self._ssl_context is None and self._port in _TLS_PORTS:
            logger.warning(
                "Webhook server is listening on port {} without TLS, terminate TLS in front of it",
                self._port,
            )
        if self._port not in CALLBACK_PORTS:
            logger.warning(
                "Port {} is not in the callback port list, the platform rejects direct connections;"
                " put a reverse proxy in front of it",
                self._port,
            )


def _build_ssl_context(
    certfile: str | None,
    keyfile: str | None,
    ssl_context: SSLContext | None,
) -> SSLContext | None:
    if ssl_context is not None:
        return ssl_context
    if certfile is None or keyfile is None:
        return None
    context = SSLContext(PROTOCOL_TLS_SERVER)
    context.load_cert_chain(certfile, keyfile)
    return context


def _bound_port(site: TCPSite, fallback: int) -> int:
    """`port=0` 时向操作系统要实际端口。"""

    server = getattr(site, "_server", None)
    sockets = getattr(server, "sockets", None) or []
    if not sockets:
        return fallback
    return int(sockets[0].getsockname()[1])
