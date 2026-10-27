# Copyright (c) 2026-present Half_nothing.

"""用 Webhook 方式收群聊 @ 消息

运行前设置环境变量：
    QQ_BOT_APP_ID / QQ_BOT_APP_SECRET  机器人凭证
    QQ_BOT_SECRET                      botSecret，用于验签
    QQ_BOT_CERTFILE / QQ_BOT_KEYFILE   证书与私钥；不设则走明文，仅适合本地调试
"""

import asyncio
import os
import sys

from async_event_bus import EventContext
from loguru import logger

from qbotsdk import Bot, WebhookAdapter
from qbotsdk.model.event import GroupAtMessageCreate

# 打开 TRACE 级别，输出底层网络日志
logger.remove()
logger.add(sys.stderr, level="TRACE")


async def main() -> None:
    certfile = os.environ.get("QQ_BOT_CERTFILE")
    keyfile = os.environ.get("QQ_BOT_KEYFILE")

    async with Bot(
        app_id=os.environ["QQ_BOT_APP_ID"],
        client_secret=os.environ["QQ_BOT_APP_SECRET"],
        adapter=WebhookAdapter(
            os.environ["QQ_BOT_SECRET"],
            host="0.0.0.0",
            port=8443,
            path="/qbotsdk",
            certfile=certfile,
            keyfile=keyfile,
        ),
    ) as bot:

        @bot.on(GroupAtMessageCreate)
        async def on_group_at(ctx: EventContext[GroupAtMessageCreate]) -> None:
            event = ctx.event
            print(f"群 {event.group_openid} 收到: {event.content}")
            await event.reply(f"收到: {event.content}")

        await bot.start()
        print(f"Webhook 已启动，端口 {bot.adapter.port}")
        await asyncio.Event().wait()


asyncio.run(main())
