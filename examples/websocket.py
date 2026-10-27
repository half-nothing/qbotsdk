# Copyright (c) 2026-present Half_nothing.

"""用 WebSocket 长连接收事件

运行前设置环境变量：
    QQ_BOT_APP_ID / QQ_BOT_APP_SECRET  机器人凭证
    QQ_BOT_INTENTS                     可选，十进制 intents；不设则用 Intents.DEFAULT
"""

import asyncio
import contextlib
import os
import signal
import sys

from async_event_bus import EventContext
from loguru import logger

from qbotsdk import Bot
from qbotsdk.model.event import (
    C2CMessageCreate,
    ChannelMessageCreate,
    GroupAtMessageCreate,
    InteractionCreate,
    UnknownEvent,
)

# 打开 TRACE 级别，输出底层网络日志；只看业务事件可以改成 INFO
logger.remove()
logger.add(sys.stderr, level="TRACE")


async def main() -> None:
    raw_intents = os.environ.get("QQ_BOT_INTENTS")

    async with Bot(
        app_id=os.environ["QQ_BOT_APP_ID"],
        client_secret=os.environ["QQ_BOT_APP_SECRET"],
        intents=int(raw_intents) if raw_intents else None,
    ) as bot:

        @bot.on(GroupAtMessageCreate)
        async def on_group_at(ctx: EventContext[GroupAtMessageCreate]) -> None:
            event = ctx.event
            print(f"[群] {event.group_openid} {event.author.member_openid}: {event.content}")
            await event.reply(f"收到: {event.content}")

        @bot.on(C2CMessageCreate)
        async def on_c2c(ctx: EventContext[C2CMessageCreate]) -> None:
            event = ctx.event
            print(f"[单聊] {event.author.user_openid}: {event.content}")
            await event.reply(f"收到: {event.content}")

        @bot.on(ChannelMessageCreate)
        async def on_at(ctx: EventContext[ChannelMessageCreate]) -> None:
            event = ctx.event
            print(f"[频道] {event.channel_id}: {event.content}")
            await event.reply(f"收到: {event.content}")

        @bot.on(InteractionCreate)
        async def on_interaction(ctx: EventContext[InteractionCreate]) -> None:
            event = ctx.event
            print(f"[互动] type={event.type.name} scene={event.scene}")
            # 只有消息按钮与快捷菜单需要回应，同一 id 只能回一次
            if event.needs_response:
                await event.respond()

        @bot.on_unknown()
        async def on_unknown(ctx: EventContext[UnknownEvent]) -> None:
            print(f"[未建模] {ctx.event.t}")

        stopped = asyncio.Event()
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            # Windows 的 ProactorEventLoop 不支持信号处理，靠 Ctrl+C 抛 KeyboardInterrupt
            with contextlib.suppress(NotImplementedError):
                loop.add_signal_handler(sig, stopped.set)

        await bot.start()
        print("WebSocket 已连接，按 Ctrl+C 退出")
        with contextlib.suppress(KeyboardInterrupt, asyncio.CancelledError):
            await stopped.wait()


asyncio.run(main())
