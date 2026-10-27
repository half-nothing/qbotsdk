# Copyright (c) 2026-present Half_nothing.

"""包的版本号要与安装元数据一致，构建配置写错时这里会先红。"""

from __future__ import annotations

from importlib.metadata import version

import qbotsdk


def test_version_matches_metadata() -> None:
    assert qbotsdk.__version__ == version("qbotsdk")


def test_version_is_exported() -> None:
    assert "__version__" in qbotsdk.__all__


def test_session_storage_is_top_level() -> None:
    assert "qbotsdk.storage" in __import__("sys").modules
    assert qbotsdk.SessionStorage is not None
