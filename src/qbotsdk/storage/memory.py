# Copyright (c) 2026-present Half_nothing.

"""内存存储，进程内保留会话，重启就丢，适合单进程无所谓断线的场景。"""

from __future__ import annotations

from .base import SessionData, SessionStorage


class MemorySessionStorage(SessionStorage):
    """把会话放在进程内存里。"""

    __slots__ = ("_data",)

    def __init__(self) -> None:
        self._data: SessionData | None = None

    async def load(self) -> SessionData | None:
        return self._data

    async def save(self, data: SessionData) -> None:
        self._data = data

    async def clear(self) -> None:
        self._data = None
