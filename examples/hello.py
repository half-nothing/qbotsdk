# Copyright (c) 2026-present Half_nothing.

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
        me = await bot.get_me()
        print(f"登录成功: {me.username} (id={me.id}, bot={me.bot})")


if __name__ == "__main__":
    asyncio.run(main())
