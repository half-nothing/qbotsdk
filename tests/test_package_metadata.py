# Copyright (c) 2026-present Half_nothing.

"""包的版本号要与安装元数据一致，构建配置写错时这里会先红。"""

from __future__ import annotations

from importlib.metadata import version

import qbotsdk
from qbotsdk.storage import SessionStorage


def test_version_matches_metadata() -> None:
    assert qbotsdk.__version__ == version("qbotsdk")


def test_only_root_modules_are_reexported() -> None:
    assert set(qbotsdk.__all__) == {
        "APIError",
        "Bot",
        "ClientOptions",
        "ErrorCode",
        "QQBotError",
        "RateLimitExceededError",
        "TransportError",
        "__version__",
    }


def test_session_storage_lives_in_its_own_package() -> None:
    assert "qbotsdk.storage" in __import__("sys").modules
    assert SessionStorage is not None
