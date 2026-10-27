# Copyright (c) 2026-present Half_nothing.

"""文件存储，会话写进一个 JSON 文件，进程重启后还能接着 Resume。"""

from __future__ import annotations

from asyncio import Task, create_task, sleep
from collections.abc import Callable
from contextlib import suppress
from os import replace
from pathlib import Path
from time import monotonic

from loguru import logger

from .base import SessionData, SessionStorage


class FileSessionStorage(SessionStorage):
    """把一个会话写进文件。"""

    __slots__ = (
        "_clock",
        "_flush_interval",
        "_flush_task",
        "_last_write",
        "_path",
        "_pending",
        "_written",
    )

    def __init__(
        self,
        path: str | Path,
        *,
        flush_interval: float = 1.0,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        """记录文件位置与落盘节奏。

        Args:
            path:           会话文件路径，父目录不存在时自动创建。
            flush_interval: 两次写盘的最小间隔, 也是待写值最长滞留时间。
            clock:          单调时钟，测试可以换成假时钟。
        """

        self._path = Path(path).expanduser()
        self._flush_interval = flush_interval
        self._clock = clock
        self._written: tuple[str | None, int | None] = (None, None)
        self._pending: SessionData | None = None
        self._last_write = 0.0
        self._flush_task: Task[None] | None = None

    @property
    def path(self) -> Path:
        return self._path

    async def load(self) -> SessionData | None:
        try:
            raw = self._path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return None
        except OSError as exc:
            logger.warning("Cannot read session file {}: {!r}", self._path, exc)
            return None
        try:
            data = SessionData.model_validate_json(raw)
        except ValueError:
            logger.warning("Ignoring unreadable session file {}", self._path)
            return None
        self._written = (data.session_id, data.seq)
        return data

    async def save(self, data: SessionData) -> None:
        snapshot = (data.session_id, data.seq)
        if snapshot == self._written:
            self._pending = None
            self._cancel_flush_task()
            return
        self._pending = data
        # 换了会话说明 session_id 变了，必须立刻落盘，否则重启接不上
        if self._written[0] != data.session_id:
            self._write()
            return
        if self._clock() - self._last_write >= self._flush_interval:
            self._write()
            return
        # 推迟写盘
        self._schedule_flush()

    async def clear(self) -> None:
        self._cancel_flush_task()
        self._written = (None, None)
        self._pending = None
        with suppress(FileNotFoundError):
            self._path.unlink()

    async def close(self) -> None:
        self._cancel_flush_task()
        self._flush()

    def _schedule_flush(self) -> None:
        task = self._flush_task
        if task is not None and not task.done():
            return
        self._flush_task = create_task(self._flush_later())

    async def _flush_later(self) -> None:
        await sleep(self._flush_interval)
        self._flush_task = None
        self._flush()

    def _cancel_flush_task(self) -> None:
        task = self._flush_task
        self._flush_task = None
        if task is not None and not task.done():
            task.cancel()

    def _flush(self) -> None:
        pending = self._pending
        if pending is not None and (pending.session_id, pending.seq) != self._written:
            self._write()

    def _write(self) -> None:
        data = self._pending
        if data is None:
            return
        self._cancel_flush_task()
        tmp = self._path.with_name(self._path.name + ".tmp")
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            tmp.write_text(data.model_dump_json(by_alias=True), encoding="utf-8")
            replace(tmp, self._path)
        except OSError as exc:
            logger.warning("Cannot write session file {}: {!r}", self._path, exc)
            with suppress(OSError):
                tmp.unlink()
            return
        self._written = (data.session_id, data.seq)
        self._pending = None
        self._last_write = self._clock()
