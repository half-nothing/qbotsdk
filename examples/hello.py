# Copyright (c) 2026-present Half_nothing.

"""REST 只读接口与发消息演示

环境变量：
    QQ_BOT_APP_ID / QQ_BOT_APP_SECRET  机器人凭证，必填
    QQ_BOT_CHANNEL_ID                  可选，设置后在该子频道发一条消息、表态、再撤回
    QQ_BOT_GROUP_OPENID                可选，设置后列出群信息、机器人在群内的状态与成员

群 openid 只能从消息事件里拿到，官方没有「群列表」接口，所以示例用环境变量指定一个群。
"""

import asyncio
import os
import sys

from loguru import logger

from qbotsdk import Bot
from qbotsdk.model.reaction import EmojiType

# 打开 TRACE 级别，输出底层网络日志；只看业务输出可以改成 INFO
logger.remove()
logger.add(sys.stderr, level="TRACE")


async def show_guilds(bot: Bot) -> None:
    async for guild in bot.api.user.iter_guilds():
        channels = await bot.api.guild.channels(guild.id)
        roles = await bot.api.guild.roles(guild.id)
        print(f"频道 {guild.name} ({guild.id}) 子频道 {len(channels)} 身份组 {len(roles.roles)}")
        for channel in channels:
            print(f"  - {channel.name} type={channel.type} id={channel.id}")


async def demo_channel(bot: Bot, channel_id: str) -> None:
    message = await bot.api.channel.send_message(channel_id, content="来自 qbotsdk 的问好")
    print(f"已发送: id={message.id} channel={message.channel_id}")

    # 表态只作用于频道消息，emoji_id 是表情代码
    await bot.api.reaction.add(channel_id, message.id, EmojiType.SYSTEM, "4")
    users = await bot.api.reaction.users(channel_id, message.id, EmojiType.SYSTEM)
    print(f"表态成功: {users.users[0].username if users.users else '(列表为空)'}")

    await bot.api.reaction.remove(channel_id, message.id, EmojiType.SYSTEM, "4")
    await bot.api.channel.recall_message(channel_id, message.id, hide_tip=True)
    print("已撤回")


async def show_group(bot: Bot, group_openid: str) -> None:
    group = await bot.api.group.get(group_openid)
    state = await bot.api.group.bot_state(group_openid)
    print(f"群 {group.group_name} 成员 {group.group_member_num} 人")
    print(f"  机器人已加入: {state.joined_at} 收消息策略: {state.recv_msg_setting}")

    count = 0
    async for member in bot.api.group.iter_members(group_openid):
        count += 1
        print(f"  - {member.username or member.member_openid} role={member.member_role}")
    print(f"  群成员共 {count} 人")


async def main() -> None:
    async with Bot(
        app_id=os.environ["QQ_BOT_APP_ID"],
        app_secret=os.environ["QQ_BOT_APP_SECRET"],
    ) as bot:
        me = await bot.api.user.me()
        print(f"登录成功: {me.username} (id={me.id})")

        await show_guilds(bot)

        channel_id = os.environ.get("QQ_BOT_CHANNEL_ID")
        if channel_id:
            await demo_channel(bot, channel_id)
        else:
            print("未设置 QQ_BOT_CHANNEL_ID，跳过发消息与表态演示")

        group_openid = os.environ.get("QQ_BOT_GROUP_OPENID")
        if group_openid:
            await show_group(bot, group_openid)
        else:
            print("未设置 QQ_BOT_GROUP_OPENID，跳过群信息演示")


if __name__ == "__main__":
    asyncio.run(main())
