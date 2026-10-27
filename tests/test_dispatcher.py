# Copyright (c) 2026-present Half_nothing.

"""分发层：注册、异常隔离、去重与队列消费。"""

from __future__ import annotations

import asyncio

import pytest
from async_event_bus import EventContext

from qbotsdk.gateway.dispatcher import Dispatcher
from qbotsdk.gateway.payload import GatewayPayload
from qbotsdk.model.event import GroupAtMessageCreate, UnknownEvent
from tests.support import load_frame

GROUP_FRAME = "gateway_group_at_message_create.json"


def group_payload() -> GatewayPayload:
    return load_frame(GROUP_FRAME)


async def test_handler_receives_group_event() -> None:
    dispatcher = Dispatcher()
    seen: list[GroupAtMessageCreate] = []

    @dispatcher.on(GroupAtMessageCreate)
    async def on_group(ctx: EventContext[GroupAtMessageCreate]) -> None:
        seen.append(ctx.event)

    dispatcher.handle(group_payload())
    await dispatcher.join()

    assert len(seen) == 1
    assert seen[0].group_openid
    assert seen[0].author.member_openid


async def test_all_handlers_of_one_event_run() -> None:
    dispatcher = Dispatcher()
    seen: list[str] = []

    @dispatcher.on(GroupAtMessageCreate)
    async def first(ctx: EventContext[GroupAtMessageCreate]) -> None:
        seen.append("first")

    @dispatcher.on(GroupAtMessageCreate)
    async def second(ctx: EventContext[GroupAtMessageCreate]) -> None:
        seen.append("second")

    dispatcher.handle(group_payload())
    await dispatcher.join()

    # 总线把异步处理器并发跑, 所以只断言都跑到, 不锁顺序
    assert sorted(seen) == ["first", "second"]


async def test_failing_handler_does_not_block_next() -> None:
    dispatcher = Dispatcher()
    seen: list[str] = []

    @dispatcher.on(GroupAtMessageCreate)
    async def broken(ctx: EventContext[GroupAtMessageCreate]) -> None:
        raise RuntimeError("boom")

    @dispatcher.on(GroupAtMessageCreate)
    async def healthy(ctx: EventContext[GroupAtMessageCreate]) -> None:
        seen.append(ctx.event.id)

    dispatcher.handle(group_payload())
    await dispatcher.join()

    assert seen == [group_payload().d["id"]]


async def test_duplicate_message_is_skipped() -> None:
    dispatcher = Dispatcher()
    seen: list[str] = []

    @dispatcher.on(GroupAtMessageCreate)
    async def on_group(ctx: EventContext[GroupAtMessageCreate]) -> None:
        seen.append(ctx.event.id)

    dispatcher.handle(group_payload())
    dispatcher.handle(group_payload())
    await dispatcher.join()

    assert len(seen) == 1


async def test_dedupe_can_be_disabled() -> None:
    dispatcher = Dispatcher(dedupe_size=0)
    seen: list[str] = []

    @dispatcher.on(GroupAtMessageCreate)
    async def on_group(ctx: EventContext[GroupAtMessageCreate]) -> None:
        seen.append(ctx.event.id)

    dispatcher.handle(group_payload())
    dispatcher.handle(group_payload())
    await dispatcher.join()

    assert len(seen) == 2


def test_sync_handler_is_rejected() -> None:
    dispatcher = Dispatcher()

    def not_async(ctx: EventContext[GroupAtMessageCreate]) -> None:  # pragma: no cover
        return None

    with pytest.raises(TypeError, match="must be an async function"):
        dispatcher.on(GroupAtMessageCreate)(not_async)  # type: ignore[arg-type]


async def test_unknown_event_reaches_unknown_handler() -> None:
    dispatcher = Dispatcher()
    seen: list[UnknownEvent] = []

    @dispatcher.on_unknown()
    async def on_unknown(ctx: EventContext[UnknownEvent]) -> None:
        seen.append(ctx.event)

    frame = GatewayPayload(op=0, t="NOT_MODELED_EVENT", d={"id": "m1"}, s=3)  # type: ignore[arg-type]
    dispatcher.handle(frame)
    await dispatcher.join()

    assert len(seen) == 1
    assert seen[0].t == "NOT_MODELED_EVENT"
    assert seen[0].data == {"id": "m1"}


async def test_run_consumes_queue() -> None:
    dispatcher = Dispatcher()
    seen: list[str] = []
    queue: asyncio.Queue[GatewayPayload] = asyncio.Queue()

    @dispatcher.on(GroupAtMessageCreate)
    async def on_group(ctx: EventContext[GroupAtMessageCreate]) -> None:
        seen.append(ctx.event.id)

    runner = asyncio.create_task(dispatcher.run(queue))
    await queue.put(group_payload())
    await asyncio.sleep(0.05)
    runner.cancel()
    with pytest.raises(asyncio.CancelledError):
        await runner
    await dispatcher.join()

    assert len(seen) == 1
