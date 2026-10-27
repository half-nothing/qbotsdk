# Copyright (c) 2026-present Half_nothing.

"""测试辅助，一个本地 aiohttp 服务，记录收到的每一次调用。

用例断言的是「SDK 发了什么」，因此 `MockServer.calls` 会记下每次调用的
method/path/query/headers/body，而不只是返回值。
"""

from __future__ import annotations

import json as jsonlib
import pathlib
import socket
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

import aiohttp
import aiohttp.web

from qbotsdk.gateway.payload import (
    GatewayPayload,
    HeartbeatAckFrame,
    HelloData,
    HelloFrame,
    OpCode,
)

Handler = Callable[[aiohttp.web.Request], Awaitable[aiohttp.web.StreamResponse]]

TOKEN_PATH = "/app/getAppAccessToken"


@dataclass
class RecordedCall:
    method: str
    path: str
    query: dict[str, str]
    headers: dict[str, str]
    # 原始请求体, multipart 只能从这里断言
    body: bytes
    json: object | None


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        _, port = sock.getsockname()
        return int(port)


class MockServer:
    def __init__(self) -> None:
        self._app = aiohttp.web.Application()
        self._runner: aiohttp.web.AppRunner | None = None
        self._url = ""
        # 路由表在服务启动后仍可增补：所有请求先落到统一分发器
        self._routes: dict[tuple[str, str], Handler] = {}
        self.calls: list[RecordedCall] = []

    @property
    def url(self) -> str:
        return self._url

    def route(self, method: str, path: str, handler: Handler) -> None:
        self._routes[(method.upper(), path)] = self._recording(handler)

    def _recording(self, handler: Handler) -> Handler:
        async def wrapper(request: aiohttp.web.Request) -> aiohttp.web.StreamResponse:
            raw = await request.read()
            text = raw.decode("utf-8", errors="replace")
            payload: object | None
            if text:
                try:
                    payload = jsonlib.loads(text)
                except jsonlib.JSONDecodeError:
                    payload = text
            else:
                payload = None
            self.calls.append(
                RecordedCall(
                    method=request.method,
                    path=request.path,
                    query=dict(request.query),
                    headers=dict(request.headers),
                    body=raw,
                    json=payload,
                )
            )
            return await handler(request)

        return wrapper

    async def _dispatch(self, request: aiohttp.web.Request) -> aiohttp.web.StreamResponse:
        handler = self._routes.get((request.method, request.path))
        if handler is None:
            text = f"unregistered route: {request.method} {request.path}"
            return aiohttp.web.Response(status=404, text=text)
        return await handler(request)

    async def start(self) -> None:
        self._app.router.add_route("*", "/{tail:.*}", self._dispatch)
        self._runner = aiohttp.web.AppRunner(self._app)
        await self._runner.setup()
        site = aiohttp.web.TCPSite(self._runner, "127.0.0.1", _free_port())
        await site.start()
        assert site._server is not None
        # aiohttp 把监听地址放在 TCPSite 的私有 server 上，抽象基类没有 sockets 属性
        port = site._server.sockets[0].getsockname()[1]  # type: ignore[attr-defined]
        self._url = f"http://127.0.0.1:{port}"

    async def stop(self) -> None:
        if self._runner is not None:
            await self._runner.cleanup()
            self._runner = None


async def token_handler(request: aiohttp.web.Request) -> aiohttp.web.StreamResponse:
    return aiohttp.web.json_response({"access_token": "test-token", "expires_in": 7200})


def add_token_route(server: MockServer, handler: Handler | None = None) -> None:
    """注册凭证接口；默认返回固定 token，需要计数时传自定义 handler。"""

    server.route("POST", TOKEN_PATH, handler if handler is not None else token_handler)


GATEWAY_FRAME_DIR = pathlib.Path(__file__).with_name("data")


def read_frame(name: str) -> str:
    """读 `tests/data/` 下的网关帧原文。"""

    return (GATEWAY_FRAME_DIR / name).read_text("utf-8")


def load_frame(name: str) -> GatewayPayload:
    """读 `tests/data/` 下的网关帧并解析成 payload 模型。"""

    return GatewayPayload.model_validate_json(read_frame(name))


class FakeGateway:
    """假网关：一个本地服务同时提供凭证、`/gateway/bot` 与 websocket。

    用例要断言「SDK 发了什么」，所以每帧都记进 `frames`；`hello` 的心跳间隔
    可以调小到几十毫秒，让心跳与重连在测试里几毫秒内就能观察到。
    """

    def __init__(self) -> None:
        self.heartbeat_interval = 50  # 毫秒
        self.ack_heartbeat = True
        self.close_after_ready: int | None = None
        self.frames: list[dict[str, Any]] = []
        self.connections = 0
        self._app = aiohttp.web.Application()
        self._runner: aiohttp.web.AppRunner | None = None
        self._url = ""
        self._ws_url = ""

    @property
    def url(self) -> str:
        return self._url

    async def start(self) -> None:
        self._app.router.add_post(TOKEN_PATH, self._token)
        self._app.router.add_get("/gateway/bot", self._bot)
        self._app.router.add_get("/websocket", self._websocket)
        self._runner = aiohttp.web.AppRunner(self._app)
        await self._runner.setup()
        site = aiohttp.web.TCPSite(self._runner, "127.0.0.1", _free_port())
        await site.start()
        assert site._server is not None
        port = site._server.sockets[0].getsockname()[1]  # type: ignore[attr-defined]
        self._url = f"http://127.0.0.1:{port}"
        self._ws_url = f"ws://127.0.0.1:{port}/websocket"

    async def stop(self) -> None:
        if self._runner is not None:
            await self._runner.cleanup()
            self._runner = None

    async def _token(self, request: aiohttp.web.Request) -> aiohttp.web.Response:
        return aiohttp.web.json_response({"access_token": "test-token", "expires_in": 7200})

    async def _bot(self, request: aiohttp.web.Request) -> aiohttp.web.Response:
        return aiohttp.web.json_response(
            {
                "url": self._ws_url,
                "shards": 1,
                "session_start_limit": {
                    "total": 1000,
                    "remaining": 999,
                    "reset_after": 60000,
                    "max_concurrency": 1,
                },
            }
        )

    async def _websocket(self, request: aiohttp.web.Request) -> aiohttp.web.WebSocketResponse:
        self.connections += 1
        ws = aiohttp.web.WebSocketResponse()
        await ws.prepare(request)
        await ws.send_str(
            HelloFrame(d=HelloData(heartbeat_interval=self.heartbeat_interval)).to_json()
        )
        async for message in ws:
            if message.type is not aiohttp.WSMsgType.TEXT:
                continue
            payload = GatewayPayload.model_validate_json(message.data)
            self.frames.append(payload.model_dump())
            if payload.op is OpCode.HEARTBEAT:
                if self.ack_heartbeat:
                    await ws.send_str(HeartbeatAckFrame().to_json())
            elif payload.op is OpCode.IDENTIFY:
                await ws.send_str(read_frame("gateway_ready.json"))
                if self.close_after_ready is not None:
                    await ws.close(code=self.close_after_ready)
            elif payload.op is OpCode.RESUME:
                await ws.send_str(read_frame("gateway_resumed.json"))
        return ws
