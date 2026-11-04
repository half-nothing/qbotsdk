# Copyright (c) 2026-present Half_nothing.

"""Bot.run() 与 wait_for_exit() 的信号处理。"""

import asyncio
import signal
import sys
from collections.abc import Callable
from typing import Any, cast

import pytest

from qbotsdk import Bot
from qbotsdk.adapter.base import Adapter, AdapterContext


class StubAdapter(Adapter):
    """只记录 start/stop 次数, 不碰网络。"""

    def __init__(self) -> None:
        self.started = 0
        self.stopped = 0

    async def start(self, context: AdapterContext) -> None:
        self.started += 1

    async def stop(self) -> None:
        self.stopped += 1


async def test_run_starts_and_stops_around_the_signal_wait(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = StubAdapter()
    bot = Bot("app", "secret", adapter=adapter)
    seen: list[tuple[int, ...]] = []

    async def fake_wait(self: Bot, *, signals: tuple[int, ...] = ()) -> None:
        seen.append(signals)
        assert adapter.started == 1

    monkeypatch.setattr(Bot, "wait_for_exit", fake_wait)
    await bot.run(signals=(signal.SIGINT,))

    assert seen == [(signal.SIGINT,)]
    assert adapter.started == 1
    assert adapter.stopped == 1


async def test_run_propagates_a_start_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    adapter = StubAdapter()
    bot = Bot("app", "secret", adapter=adapter)
    await bot.start()

    with pytest.raises(RuntimeError, match="already started"):
        await bot.run()

    await bot.stop()


async def test_wait_for_exit_releases_on_a_signal() -> None:
    bot = Bot("app", "secret", adapter=StubAdapter())
    task = asyncio.create_task(bot.wait_for_exit(signals=(signal.SIGTERM,)))
    await asyncio.sleep(0)

    handler = cast("Callable[[int, Any], None]", signal.getsignal(signal.SIGTERM))
    handler(signal.SIGTERM, None)

    await asyncio.wait_for(task, timeout=2)


@pytest.mark.skipif(sys.platform != "win32", reason="只在 Windows 上走 signal.signal 回退")
async def test_wait_for_exit_restores_the_previous_handler() -> None:
    bot = Bot("app", "secret", adapter=StubAdapter())
    before: Any = signal.getsignal(signal.SIGTERM)

    task = asyncio.create_task(bot.wait_for_exit(signals=(signal.SIGTERM,)))
    await asyncio.sleep(0)
    installed = cast("Callable[[int, Any], None]", signal.getsignal(signal.SIGTERM))
    assert installed is not before
    installed(signal.SIGTERM, None)
    await asyncio.wait_for(task, timeout=2)

    assert signal.getsignal(signal.SIGTERM) is before
