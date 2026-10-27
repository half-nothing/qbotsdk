# Copyright (c) 2026-present Half_nothing.

"""单聊机器人：输入中状态、文本与 Markdown 回复、超回复次数时降级

环境变量：
    QQ_BOT_APP_ID / QQ_BOT_APP_SECRET  机器人凭证，必填

单聊的规则与群聊不同，示例里体现三点：
    - 被动回复窗口 60 分钟，每条用户消息最多回 4 次
    - 「正在输入」是独立的 msg_type=6 消息，可以先发它再做耗时的事
    - Markdown 与纯文本不能同时带，reply() 传了 markdown 就会忽略 content
"""

import asyncio
import contextlib
import os
import signal
import sys

from async_event_bus import EventContext
from loguru import logger

from qbotsdk import Bot, WebSocketAdapter
from qbotsdk.exceptions import APIError
from qbotsdk.model.draft import MessageMarkdown
from qbotsdk.model.event import C2CMessageCreate

logger.remove()
logger.add(sys.stderr, level="TRACE")


async def answer(bot: Bot, event: C2CMessageCreate) -> None:
    user_openid = event.author.user_openid
    text = event.content.strip()

    if text.startswith("/md"):
        # Markdown 消息：reply() 会自动丢掉 content
        await event.reply(markdown=MessageMarkdown(content=f"**收到**：{text.removeprefix('/md')}"))
        return

    # 先申请「正在输入」，最多 60 秒，随后做耗时的事
    await bot.api.user_message.notify_input(user_openid, seconds=30)
    await asyncio.sleep(1)
    await event.reply(f"收到：{text}")


async def main() -> None:
    async with Bot(
        app_id=os.environ["QQ_BOT_APP_ID"],
        app_secret=os.environ["QQ_BOT_APP_SECRET"],
        adapter=WebSocketAdapter(),
    ) as bot:

        @bot.on(C2CMessageCreate)
        async def on_c2c(ctx: EventContext[C2CMessageCreate]) -> None:
            event = ctx.event
            print(f"[单聊] {event.author.user_openid}: {event.content}")
            try:
                await answer(bot, event)
            except ValueError as exc:
                # 同一条消息第 5 次回复会被本地拦下，官方限制是 4 次
                print(f"回复次数用完了: {exc}")
            except APIError as exc:
                # 窗口过期、用户拒收之类由服务端拒绝
                print(f"发送失败 status={exc.status} code={exc.code} message={exc.message}")

        await bot.start()
        print("WebSocket 已连接，给机器人发私聊消息试试，/md 开头会走 Markdown")

        stopped = asyncio.Event()
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            with contextlib.suppress(NotImplementedError):
                loop.add_signal_handler(sig, stopped.set)
        with contextlib.suppress(KeyboardInterrupt, asyncio.CancelledError):
            await stopped.wait()


if __name__ == "__main__":
    asyncio.run(main())
