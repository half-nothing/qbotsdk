# Copyright (c) 2026-present Half_nothing.

"""开箱即用的 Webhook 服务器。"""

from __future__ import annotations

from typing import TYPE_CHECKING
from ssl import SSLContext, PROTOCOL_TLS_SERVER

from aiohttp.web import AppRunner, TCPSite, Application, Request, Response, json_response
from loguru import logger
from pydantic import ValidationError

from .payload import GatewayPayload, OpCode
from .webhook import (
    build_ack_payload,
    build_validation_response,
    verify_webhook_signature,
)

if TYPE_CHECKING:
    from ..bot import Bot

# 平台允许在管理端配置的回调端口
CALLBACK_PORTS = frozenset({80, 443, 8080, 8443})

# 明文监听这些端口时大概率是忘了配证书
_TLS_PORTS = frozenset({443, 8443})

_SIGNATURE_HEADER = "X-Signature-Ed25519"
_TIMESTAMP_HEADER = "X-Signature-Timestamp"


class WebhookServer:
    """把事件回调转发给 Bot 的分发器。

    典型用法：

    ```python
    server = WebhookServer(bot, bot_secret="...", certfile="cert.pem", keyfile="key.pem")
    await server.start()
    ...
    await server.close()
    ```
    """

    def __init__(
        self,
        bot: Bot,
        bot_secret: str,
        *,
        host: str = "0.0.0.0",
        port: int = 8443,
        path: str = "/qqbot",
        certfile: str | None = None,
        keyfile: str | None = None,
        ssl_context: SSLContext | None = None,
    ) -> None:
        """创建服务器，但先不监听。

        Args:
            bot:        事件最终交给 bot.dispatcher 分发。
            bot_secret: 机器人密钥，用于验签与 op 13 应答。
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

        self._bot = bot
        self._bot_secret = bot_secret
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
        app.router.add_post(self._path, self._handle)
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

    async def _handle(self, request: Request) -> Response:
        # 签名体是时间戳 + 原始报文, 所以只能读原始字节, 不能先 request.json()
        body = await request.read()
        try:
            payload = GatewayPayload.model_validate_json(body)
        except ValidationError:
            return Response(status=400, text="invalid payload")

        if payload.op is OpCode.CALLBACK_VALIDATION:
            return self._validation_response(payload)

        signature = request.headers.get(_SIGNATURE_HEADER, "")
        timestamp = request.headers.get(_TIMESTAMP_HEADER, "")
        if not signature or not timestamp:
            return Response(status=401, text="missing signature")
        if not verify_webhook_signature(self._bot_secret, signature, timestamp, body):
            return Response(status=401, text="invalid signature")

        # 官方要求快速 ACK, 处理慢会被重推, 所以先回包再分发
        self._bot.dispatcher.handle(payload)
        return json_response(build_ack_payload())

    def _validation_response(self, payload: GatewayPayload) -> web.Response:
        data = payload.d
        if not isinstance(data, dict):
            return Response(status=400, text="invalid validation payload")
        plain_token = data.get("plain_token")
        event_ts = data.get("event_ts")
        if not isinstance(plain_token, str) or not isinstance(event_ts, str):
            return Response(status=400, text="invalid validation payload")
        return json_response(build_validation_response(self._bot_secret, plain_token, event_ts))

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
