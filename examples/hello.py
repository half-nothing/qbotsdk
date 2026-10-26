# Copyright (c) 2026-present Half_nothing.

"""列出机器人加入的频道与子频道，并在指定子频道里发一条消息

运行前设置环境变量 QQ_BOT_APP_ID 与 QQ_BOT_APP_SECRET；
再设置 QQ_BOT_CHANNEL_ID 则会往该子频道发一条消息并立刻撤回。
"""

import asyncio
import os
import sys

from loguru import logger

from qqbot import Bot

# 打开 TRACE 级别，输出底层网络日志
logger.remove()
logger.add(sys.stderr, level="TRACE")


async def main() -> None:
    async with Bot(
        app_id=os.environ["QQ_BOT_APP_ID"],
        client_secret=os.environ["QQ_BOT_APP_SECRET"],
    ) as bot:
        me = await bot.api.user.me()
        print(f"登录成功: {me.username} (id={me.id})")

        async for guild in bot.api.user.iter_guilds():
            channels = await bot.api.guild.channels(guild.id)
            print(f"频道 {guild.name} ({guild.id}) 共 {len(channels)} 个子频道")
            for channel in channels:
                print(f"  - {channel.name} type={channel.type} id={channel.id}")

        channel_id = os.environ.get("QQ_BOT_CHANNEL_ID")
        if channel_id is None:
            print("未设置 QQ_BOT_CHANNEL_ID，跳过发消息演示")
            return

        message = await bot.api.channel.send_message(channel_id, content="来自 qq-bot-sdk 的问好")
        print(f"已发送: id={message.id} channel={message.channel_id}")

        await bot.api.channel.recall_message(channel_id, message.id, hide_tip=True)
        print("已撤回")


if __name__ == "__main__":
    asyncio.run(main())
