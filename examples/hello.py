import asyncio
import os

from qqbot import Bot


async def main() -> None:
    async with Bot(
        app_id=os.environ["QQ_BOT_APP_ID"],
        client_secret=os.environ["QQ_BOT_APP_SECRET"],
    ) as bot:
        me = await bot.get_me()
        print(f"登录成功: {me.username} (id={me.id}, bot={me.bot})")


if __name__ == "__main__":
    asyncio.run(main())
