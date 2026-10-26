# Copyright (c) 2026-present Half_nothing.

"""测试辅助，一个本地 aiohttp 服务，记录收到的每一次调用。

用例断言的是「SDK 发了什么」，因此 `MockServer.calls` 会记下每次调用的
method/path/query/headers/body，而不只是返回值。
"""

from __future__ import annotations

import json as jsonlib
import socket
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

import aiohttp
import aiohttp.web

Handler = Callable[[aiohttp.web.Request], Awaitable[aiohttp.web.StreamResponse]]

TOKEN_PATH = "/app/getAppAccessToken"


@dataclass
class RecordedCall:
    method: str
    path: str
    query: dict[str, str]
    headers: dict[str, str]
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
            raw = await request.text()
            payload: object | None
            if raw:
                try:
                    payload = jsonlib.loads(raw)
                except jsonlib.JSONDecodeError:
                    payload = raw
            else:
                payload = None
            self.calls.append(
                RecordedCall(
                    method=request.method,
                    path=request.path,
                    query=dict(request.query),
                    headers=dict(request.headers),
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
