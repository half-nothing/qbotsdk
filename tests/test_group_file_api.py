# Copyright (c) 2026-present Half_nothing.

"""群富媒体上传：URL 与二进制两条路径、参数互斥、体积上限。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import aiohttp.web
import pytest

from qbotsdk.bot import Bot
from qbotsdk.model.media import FileType, UploadedFile
from tests.support import MockServer

DATA = Path(__file__).parent / "data"

GROUP = "group-1"
FILES = f"/v2/groups/{GROUP}/files"


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


async def test_upload_binary_is_multipart(server: MockServer, bot: Bot) -> None:
    json_route(server, "POST", FILES, {"file_uuid": "u", "file_info": "i", "ttl": 3600})

    uploaded = await bot.api.group.upload_file(
        GROUP, FileType.VOICE, file_data=b"RIFF....", file_name="a.silk"
    )

    assert uploaded.file_info == "i"
    call = call_to(server, FILES)
    assert "multipart/form-data" in call.headers["Content-Type"]
    text = call.body.decode("utf-8", errors="replace")
    assert 'name="file_type"' in text
    assert 'name="file_data"; filename="a.silk"' in text
    assert 'name="file_name"' in text


async def test_upload_binary_with_srv_send_msg(server: MockServer, bot: Bot) -> None:
    json_route(server, "POST", FILES, {"file_uuid": "u", "file_info": "i", "ttl": 60, "id": "m1"})

    uploaded = await bot.api.group.upload_file(
        GROUP, FileType.IMAGE, file_data=b"png", file_name="a.png", srv_send_msg=True
    )

    assert uploaded.id == "m1"
    text = call_to(server, FILES).body.decode("utf-8", errors="replace")
    assert "true" in text


async def test_upload_rejects_oversize(server: MockServer, bot: Bot) -> None:
    json_route(server, "POST", FILES, snapshot("group_file.json"))

    with pytest.raises(ValueError, match="must not exceed 5 MB"):
        await bot.api.group.upload_file(
            GROUP,
            FileType.IMAGE,
            file_data=b"\0" * (5 * 1024 * 1024 + 1),
            file_name="a.png",
        )
    assert calls_to(server, FILES) == 0


async def test_upload_needs_exactly_one_source(server: MockServer, bot: Bot) -> None:
    with pytest.raises(ValueError, match="exactly one of url or file_data"):
        await bot.api.group.upload_file(GROUP, FileType.IMAGE)
    with pytest.raises(ValueError, match="exactly one of url or file_data"):
        await bot.api.group.upload_file(
            GROUP, FileType.IMAGE, url="https://example.com/a.png", file_data=b"x"
        )
    assert calls_to(server, FILES) == 0


async def test_upload_binary_needs_file_name(server: MockServer, bot: Bot) -> None:
    with pytest.raises(ValueError, match="needs file_name"):
        await bot.api.group.upload_file(GROUP, FileType.IMAGE, file_data=b"x")
    assert calls_to(server, FILES) == 0
