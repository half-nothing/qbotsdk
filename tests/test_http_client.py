# Copyright (c) 2026-present Half_nothing.

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

import aiohttp
import aiohttp.web
import pytest
from aiohttp import FormData

import qbotsdk.module.http_client
from qbotsdk.exceptions import APIError, ErrorCode, TransportError
from qbotsdk.module.http_client import HTTPClient
from qbotsdk.options import ClientOptions
from tests.support import TOKEN_PATH, MockServer, add_token_route


@pytest.fixture
def sleeps(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    recorded: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        recorded.append(seconds)

    monkeypatch.setattr(qbotsdk.module.http_client, "_sleep", fake_sleep)
    return recorded


@pytest.fixture
async def client(
    server: MockServer,
    point_at: None,
    sleeps: list[float],
) -> AsyncIterator[HTTPClient]:
    add_token_route(server)
    http = HTTPClient("app", "secret")
    try:
        yield http
    finally:
        await http.close()


async def test_204_returns_none(client: HTTPClient, server: MockServer) -> None:
    async def handler(request: aiohttp.web.Request) -> aiohttp.web.StreamResponse:
        return aiohttp.web.Response(status=204)

    server.route("DELETE", "/ping", handler)

    assert await client.request("DELETE", "/ping") is None


async def test_non_json_body(client: HTTPClient, server: MockServer) -> None:
    async def handler(request: aiohttp.web.Request) -> aiohttp.web.StreamResponse:
        return aiohttp.web.Response(text="pong", content_type="text/plain")

    server.route("GET", "/text", handler)

    assert await client.request("GET", "/text") == "pong"


async def test_err_code_mapped(client: HTTPClient, server: MockServer) -> None:
    async def handler(request: aiohttp.web.Request) -> aiohttp.web.StreamResponse:
        return aiohttp.web.json_response(
            {"err_code": 11253, "message": "no permission"}, status=403
        )

    server.route("GET", "/denied", handler)

    with pytest.raises(APIError) as excinfo:
        await client.request("GET", "/denied")

    error = excinfo.value
    assert error.status == 403
    assert error.code == ErrorCode.ERROR_CHECK_APP_PRIVILEGE_NOT_PASS
    assert error.code_name == "ERROR_CHECK_APP_PRIVILEGE_NOT_PASS"


async def test_trace_id_from_header(client: HTTPClient, server: MockServer) -> None:
    async def handler(request: aiohttp.web.Request) -> aiohttp.web.StreamResponse:
        return aiohttp.web.json_response(
            {"err_code": 12002, "message": "bad request"},
            status=400,
            headers={"X-Tps-trace-ID": "trace-abc"},
        )

    server.route("GET", "/broken", handler)

    with pytest.raises(APIError) as excinfo:
        await client.request("GET", "/broken")

    assert excinfo.value.trace_id == "trace-abc"


async def test_429_retries_with_retry_after(
    client: HTTPClient,
    server: MockServer,
    sleeps: list[float],
) -> None:
    attempts = {"n": 0}

    async def handler(request: aiohttp.web.Request) -> aiohttp.web.StreamResponse:
        attempts["n"] += 1
        if attempts["n"] == 1:
            return aiohttp.web.Response(status=429, headers={"Retry-After": "1"})
        return aiohttp.web.json_response({"ok": True})

    server.route("GET", "/limited", handler)

    assert await client.request("GET", "/limited") == {"ok": True}
    assert attempts["n"] == 2
    assert sleeps == [1.0]


async def test_429_retry_after_too_long(
    client: HTTPClient,
    server: MockServer,
    sleeps: list[float],
) -> None:
    attempts = {"n": 0}

    async def handler(request: aiohttp.web.Request) -> aiohttp.web.StreamResponse:
        attempts["n"] += 1
        return aiohttp.web.Response(status=429, headers={"Retry-After": "120"})

    server.route("GET", "/limited", handler)

    with pytest.raises(APIError) as excinfo:
        await client.request("GET", "/limited")

    assert excinfo.value.status == 429
    assert attempts["n"] == 1
    assert sleeps == []


async def test_500_no_retry_for_post(
    client: HTTPClient,
    server: MockServer,
    sleeps: list[float],
) -> None:
    attempts = {"n": 0}

    async def handler(request: aiohttp.web.Request) -> aiohttp.web.StreamResponse:
        attempts["n"] += 1
        return aiohttp.web.json_response({"err_code": 0, "message": "boom"}, status=500)

    server.route("POST", "/write", handler)

    with pytest.raises(APIError):
        await client.request("POST", "/write", json={"a": 1})

    assert attempts["n"] == 1
    assert sleeps == []


async def test_500_retries_for_get(
    client: HTTPClient,
    server: MockServer,
    sleeps: list[float],
) -> None:
    attempts = {"n": 0}

    async def handler(request: aiohttp.web.Request) -> aiohttp.web.StreamResponse:
        attempts["n"] += 1
        if attempts["n"] < 3:
            return aiohttp.web.Response(status=503)
        return aiohttp.web.json_response({"ok": True})

    server.route("GET", "/flaky", handler)

    assert await client.request("GET", "/flaky") == {"ok": True}
    assert attempts["n"] == 3
    assert len(sleeps) == 2


async def test_timeout_raises_transport_error(
    server: MockServer,
    point_at: None,
    sleeps: list[float],
) -> None:
    add_token_route(server)

    async def handler(request: aiohttp.web.Request) -> aiohttp.web.StreamResponse:
        await asyncio.sleep(0.5)
        return aiohttp.web.json_response({"ok": True})

    server.route("GET", "/slow", handler)
    http = HTTPClient(
        "app",
        "secret",
        options=ClientOptions(timeout_total=0.1, max_attempts=1),
    )
    try:
        with pytest.raises(TransportError):
            await http.request("GET", "/slow")
    finally:
        await http.close()


async def test_401_refreshes_token_once(client: HTTPClient, server: MockServer) -> None:
    attempts = {"n": 0}

    async def handler(request: aiohttp.web.Request) -> aiohttp.web.StreamResponse:
        attempts["n"] += 1
        if attempts["n"] == 1:
            return aiohttp.web.Response(status=401)
        return aiohttp.web.json_response({"ok": True})

    server.route("GET", "/secure", handler)

    assert await client.request("GET", "/secure") == {"ok": True}
    assert attempts["n"] == 2
    token_calls = [call for call in server.calls if call.path == TOKEN_PATH]
    assert len(token_calls) == 2


def _upload_form() -> FormData:
    form = FormData()
    form.add_field("content", "hello")
    form.add_field("file_image", b"\x89PNG\r\n", filename="a.png", content_type="image/png")
    return form


async def test_post_form_sends_multipart(client: HTTPClient, server: MockServer) -> None:
    async def handler(request: aiohttp.web.Request) -> aiohttp.web.StreamResponse:
        return aiohttp.web.json_response({"ok": True})

    server.route("POST", "/upload", handler)

    assert await client.post_form("/upload", form=_upload_form) == {"ok": True}

    call = server.calls[-1]
    assert call.headers["Content-Type"].startswith("multipart/form-data; boundary=")
    assert b'name="content"' in call.body
    assert b"hello" in call.body
    assert b'filename="a.png"' in call.body


async def test_post_not_retried_by_default(
    client: HTTPClient,
    server: MockServer,
    sleeps: list[float],
) -> None:
    attempts = {"n": 0}

    async def handler(request: aiohttp.web.Request) -> aiohttp.web.StreamResponse:
        attempts["n"] += 1
        return aiohttp.web.Response(status=503)

    server.route("POST", "/write", handler)

    with pytest.raises(APIError) as excinfo:
        await client.post("/write", json={"a": 1})

    assert excinfo.value.status == 503
    assert attempts["n"] == 1
    assert sleeps == []


async def test_retry_post_when_enabled(
    server: MockServer,
    point_at: None,
    sleeps: list[float],
) -> None:
    add_token_route(server)
    attempts = {"n": 0}

    async def handler(request: aiohttp.web.Request) -> aiohttp.web.StreamResponse:
        attempts["n"] += 1
        if attempts["n"] == 1:
            return aiohttp.web.Response(status=503)
        return aiohttp.web.json_response({"ok": True})

    server.route("POST", "/flaky", handler)
    http = HTTPClient("app", "secret", options=ClientOptions(retry_post=True))
    try:
        assert await http.post_form("/flaky", form=_upload_form) == {"ok": True}
    finally:
        await http.close()

    uploads = [call for call in server.calls if call.path == "/flaky"]
    assert attempts["n"] == 2
    # 重试时包体被重新构建了一份, 否则第二次发送会报 form data has been processed
    assert len(uploads) == 2
    assert uploads[0].body != b""
    assert b'name="content"' in uploads[1].body
    assert len(sleeps) == 1
