# Copyright (c) 2026-present Half_nothing.

"""共享夹具，所有测试都通过本地 mock 服务驱动，不访问真实 QQ 接口。"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest

import qqbot.module.http_client
import qqbot.module.token_manager
from qqbot.bot import Bot
from tests.support import TOKEN_PATH, MockServer, add_token_route


@pytest.fixture
async def server() -> AsyncIterator[MockServer]:
    srv = MockServer()
    await srv.start()
    try:
        yield srv
    finally:
        await srv.stop()


@pytest.fixture
def point_at(server: MockServer, monkeypatch: pytest.MonkeyPatch) -> None:
    """把 BASE_URL / TOKEN_URL 指向本地服务，模块路径与设计文档一致。"""

    monkeypatch.setattr(qqbot.module.token_manager, "TOKEN_URL", f"{server.url}{TOKEN_PATH}")
    monkeypatch.setattr(qqbot.module.http_client, "BASE_URL", server.url)


@pytest.fixture
async def bot(server: MockServer, point_at: None) -> AsyncIterator[Bot]:
    add_token_route(server)
    async with Bot(app_id="app", client_secret="secret") as instance:
        yield instance
