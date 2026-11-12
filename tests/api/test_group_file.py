# Copyright (c) 2026-present Half_nothing.

"""群富媒体上传: URL 直传、小文件 base64、大文件分片、并发与重试。"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

import aiohttp.web
import pytest

from qbotsdk.api._upload import DIRECT_UPLOAD_LIMIT
from qbotsdk.bot import Bot
from qbotsdk.exceptions import APIError
from qbotsdk.model.media import FileType, UploadedFile
from qbotsdk.module import SendRecord
from qbotsdk.options import ClientOptions
from tests.support import MockServer, add_token_route

DATA = Path(__file__).parents[1] / "data"

GROUP = "group-1"
FILES = f"/v2/groups/{GROUP}/files"
PREPARE = f"/v2/groups/{GROUP}/upload_prepare"
FINISH = f"/v2/groups/{GROUP}/upload_part_finish"

Handler = Callable[[aiohttp.web.Request], Awaitable[aiohttp.web.StreamResponse]]


def snapshot(name: str) -> Any:
    return json.loads((DATA / name).read_text(encoding="utf-8"))


def json_route(server: MockServer, method: str, path: str, payload: object) -> None:
    async def handler(request: aiohttp.web.Request) -> aiohttp.web.StreamResponse:
        return aiohttp.web.json_response(payload)

    server.route(method, path, handler)


def call_to(server: MockServer, path: str) -> Any:
    return next(call for call in server.calls if call.path == path)


def payload(call: Any) -> dict[str, Any]:
    assert isinstance(call.json, dict)
    return call.json


def calls_to(server: MockServer, path: str) -> int:
    return len([call for call in server.calls if call.path == path])


def digest(data: bytes) -> tuple[str, str, str]:
    return (
        hashlib.md5(data, usedforsecurity=False).hexdigest(),
        hashlib.sha1(data, usedforsecurity=False).hexdigest(),
        hashlib.md5(data[:10_002_432], usedforsecurity=False).hexdigest(),
    )


def prepare_route(
    server: MockServer,
    *,
    block_size: int,
    part_count: int,
    concurrency: int = 1,
    retry_delay: int = 0,
) -> None:
    async def handler(request: aiohttp.web.Request) -> aiohttp.web.StreamResponse:
        return aiohttp.web.json_response(
            {
                "upload_id": "up-1",
                "block_size": str(block_size),
                "parts": [
                    {
                        "index": index,
                        "presigned_url": f"{server.url}/cos/part-{index}",
                        "block_size": str(block_size),
                    }
                    for index in range(part_count)
                ],
                "upload_config": {
                    "concurrency": concurrency,
                    "retry_timeout": 5,
                    "retry_delay": retry_delay,
                },
            }
        )

    server.route("POST", PREPARE, handler)


def put_routes(server: MockServer, part_count: int, handler: Handler | None = None) -> None:
    async def ok(request: aiohttp.web.Request) -> aiohttp.web.StreamResponse:
        return aiohttp.web.Response(status=200)

    for index in range(part_count):
        server.route("PUT", f"/cos/part-{index}", handler if handler is not None else ok)


def finish_route(server: MockServer, handler: Handler | None = None) -> None:
    async def ok(request: aiohttp.web.Request) -> aiohttp.web.StreamResponse:
        return aiohttp.web.json_response({})

    server.route("POST", FINISH, handler if handler is not None else ok)


def file_json() -> dict[str, Any]:
    return {"file_uuid": "u", "file_info": "i", "ttl": 3600}


async def test_upload_by_url_sends_json(server: MockServer, bot: Bot) -> None:
    json_route(server, "POST", FILES, snapshot("group_file.json"))

    uploaded = await bot.api.group.upload_file(
        GROUP, FileType.IMAGE, url="https://example.com/a.png"
    )

    assert isinstance(uploaded, UploadedFile)
    assert uploaded.ttl == 3600
    assert payload(call_to(server, FILES)) == {
        "file_type": 1,
        "url": "https://example.com/a.png",
        "srv_send_msg": False,
    }
    assert calls_to(server, PREPARE) == 0


async def test_upload_small_file_is_json_base64(server: MockServer, bot: Bot) -> None:
    json_route(server, "POST", FILES, file_json())

    uploaded = await bot.api.group.upload_file(
        GROUP, FileType.VOICE, file=b"RIFF....", file_name="a.silk"
    )

    assert uploaded.file_info == "i"
    call = call_to(server, FILES)
    assert call.headers["Content-Type"].startswith("application/json")
    assert payload(call) == {
        "file_type": 3,
        "file_data": base64.b64encode(b"RIFF....").decode("ascii"),
        "file_name": "a.silk",
        "srv_send_msg": False,
    }
    # 小文件不走预上传
    assert calls_to(server, PREPARE) == 0


async def test_upload_still_respects_direct_limit(server: MockServer, bot: Bot) -> None:
    json_route(server, "POST", FILES, file_json())

    await bot.api.group.upload_file(
        GROUP, FileType.IMAGE, file=b"a" * DIRECT_UPLOAD_LIMIT, file_name="a.png"
    )

    assert "file_data" in payload(call_to(server, FILES))
    assert calls_to(server, PREPARE) == 0


async def test_upload_reports_send_record(server: MockServer, point_at: None) -> None:
    add_token_route(server)
    json_route(server, "POST", FILES, {"file_uuid": "u", "file_info": "i", "ttl": 60, "id": "m1"})

    class Hook:
        def __init__(self) -> None:
            self.records: list[SendRecord] = []

        async def on_sent(self, record: SendRecord) -> None:
            self.records.append(record)

    hook = Hook()
    async with Bot(app_id="app", app_secret="secret", options=ClientOptions(send_hook=hook)) as bot:
        uploaded = await bot.api.group.upload_file(
            GROUP, FileType.IMAGE, file=b"png", file_name="a.png", srv_send_msg=True
        )

    assert uploaded.id == "m1"
    (record,) = hook.records
    assert record.scope == "group"
    assert record.target == GROUP
    assert record.path == FILES
    assert record.proactive is True
    assert record.message is None
    assert record.message_id == "m1"
    assert record.error is None


async def test_upload_large_file_streams_parts(server: MockServer, bot: Bot) -> None:
    data = b"a" * DIRECT_UPLOAD_LIMIT + b"b"
    json_route(server, "POST", FILES, file_json())
    prepare_route(server, block_size=DIRECT_UPLOAD_LIMIT, part_count=2)
    put_routes(server, 2)
    finish_route(server)

    seen: list[tuple[int, int]] = []
    uploaded = await bot.api.group.upload_file(
        GROUP,
        FileType.FILE,
        file=data,
        file_name="a.bin",
        progress=lambda done, total: seen.append((done, total)),
    )

    assert uploaded.file_info == "i"
    md5, sha1, md5_10m = digest(data)
    assert payload(call_to(server, PREPARE)) == {
        "file_type": 4,
        "file_size": str(len(data)),
        "file_name": "a.bin",
        "md5": md5,
        "sha1": sha1,
        "md5_10m": md5_10m,
    }

    parts = sorted(
        (call for call in server.calls if call.method == "PUT"), key=lambda call: call.path
    )
    assert [call.body for call in parts] == [data[:DIRECT_UPLOAD_LIMIT], b"b"]
    # 预签名地址是外部对象存储, 不能带 QQ 的 Authorization
    assert all("Authorization" not in call.headers for call in parts)

    finishes = [payload(call) for call in server.calls if call.path == FINISH]
    finishes.sort(key=lambda body: body["part_index"])
    assert [body["block_size"] for body in finishes] == [DIRECT_UPLOAD_LIMIT, 1]
    assert [body["md5"] for body in finishes] == [
        hashlib.md5(data[:DIRECT_UPLOAD_LIMIT], usedforsecurity=False).hexdigest(),
        hashlib.md5(b"b", usedforsecurity=False).hexdigest(),
    ]
    assert all(body["upload_id"] == "up-1" for body in finishes)

    assert payload(call_to(server, FILES)) == {
        "file_type": 4,
        "file_name": "a.bin",
        "upload_id": "up-1",
        "srv_send_msg": False,
    }
    assert sorted(seen) == [(len(data) - 1, len(data)), (len(data), len(data))]


async def test_upload_accepts_path(server: MockServer, bot: Bot, tmp_path: Path) -> None:
    data = b"c" * DIRECT_UPLOAD_LIMIT + b"d"
    file = tmp_path / "a.bin"
    file.write_bytes(data)
    json_route(server, "POST", FILES, file_json())
    prepare_route(server, block_size=DIRECT_UPLOAD_LIMIT, part_count=2)
    put_routes(server, 2)
    finish_route(server)

    await bot.api.group.upload_file(GROUP, FileType.FILE, file=file)

    md5, _, _ = digest(data)
    assert payload(call_to(server, PREPARE))["md5"] == md5
    assert payload(call_to(server, PREPARE))["file_name"] == "a.bin"
    parts = sorted(
        (call for call in server.calls if call.method == "PUT"), key=lambda call: call.path
    )
    assert [call.body for call in parts] == [data[:DIRECT_UPLOAD_LIMIT], b"d"]


async def test_upload_caps_concurrency_with_server_value(server: MockServer, bot: Bot) -> None:
    data = b"e" * (DIRECT_UPLOAD_LIMIT + 1)
    block_size = 1024 * 1024
    part_count = 6
    json_route(server, "POST", FILES, file_json())
    prepare_route(server, block_size=block_size, part_count=part_count, concurrency=2)
    finish_route(server)

    inflight = 0
    peak = 0

    async def put(request: aiohttp.web.Request) -> aiohttp.web.StreamResponse:
        nonlocal inflight, peak
        inflight += 1
        peak = max(peak, inflight)
        await asyncio.sleep(0.05)
        inflight -= 1
        return aiohttp.web.Response(status=200)

    put_routes(server, part_count, put)

    await bot.api.group.upload_file(GROUP, FileType.FILE, file=data, file_name="a.bin")

    # 本地默认 4, 服务端给 2, 以服务端为上界
    assert peak == 2


async def test_upload_retries_transient_put(server: MockServer, bot: Bot) -> None:
    data = b"f" * DIRECT_UPLOAD_LIMIT + b"g"
    json_route(server, "POST", FILES, file_json())
    prepare_route(server, block_size=DIRECT_UPLOAD_LIMIT, part_count=2)
    finish_route(server)

    attempts: dict[str, int] = {}

    async def flaky(request: aiohttp.web.Request) -> aiohttp.web.StreamResponse:
        attempts[request.path] = attempts.get(request.path, 0) + 1
        if request.path.endswith("part-0") and attempts[request.path] == 1:
            return aiohttp.web.Response(status=500, text="try again")
        return aiohttp.web.Response(status=200)

    put_routes(server, 2, flaky)

    uploaded = await bot.api.group.upload_file(GROUP, FileType.FILE, file=data, file_name="a.bin")

    assert uploaded.file_info == "i"
    assert calls_to(server, "/cos/part-0") == 2


async def test_upload_does_not_retry_daily_limit(server: MockServer, bot: Bot) -> None:
    data = b"h" * DIRECT_UPLOAD_LIMIT + b"i"
    json_route(server, "POST", FILES, file_json())
    prepare_route(server, block_size=DIRECT_UPLOAD_LIMIT, part_count=2)
    put_routes(server, 2)

    async def reject(request: aiohttp.web.Request) -> aiohttp.web.StreamResponse:
        return aiohttp.web.json_response(
            {"err_code": 40093002, "message": "daily upload limit reached"}, status=400
        )

    finish_route(server, reject)

    with pytest.raises(APIError):
        await bot.api.group.upload_file(GROUP, FileType.FILE, file=data, file_name="a.bin")

    first = [
        call for call in server.calls if call.path == FINISH and payload(call)["part_index"] == 0
    ]
    assert len(first) == 1


async def test_upload_needs_exactly_one_source(server: MockServer, bot: Bot) -> None:
    with pytest.raises(ValueError, match="exactly one of url or file"):
        await bot.api.group.upload_file(GROUP, FileType.IMAGE)
    with pytest.raises(ValueError, match="exactly one of url or file"):
        await bot.api.group.upload_file(
            GROUP, FileType.IMAGE, url="https://example.com/a.png", file=b"x"
        )
    assert calls_to(server, FILES) == 0


async def test_upload_needs_file_name(server: MockServer, bot: Bot) -> None:
    with pytest.raises(ValueError, match="needs file_name"):
        await bot.api.group.upload_file(GROUP, FileType.IMAGE, file=b"x")
    assert calls_to(server, FILES) == 0


async def test_upload_rejects_empty_and_missing_file(server: MockServer, bot: Bot) -> None:
    with pytest.raises(ValueError, match="must not be empty"):
        await bot.api.group.upload_file(GROUP, FileType.IMAGE, file=b"", file_name="a.png")
    with pytest.raises(ValueError, match="does not exist"):
        await bot.api.group.upload_file(GROUP, FileType.IMAGE, file="missing.png")
    assert calls_to(server, FILES) == 0
