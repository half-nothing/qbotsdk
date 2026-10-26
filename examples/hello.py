# Copyright (c) 2026-present Half_nothing.

"""列出机器人加入的频道与子频道

运行前设置环境变量 QQ_BOT_APP_ID 与 QQ_BOT_APP_SECRET
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


if __name__ == "__main__":
    asyncio.run(main())
