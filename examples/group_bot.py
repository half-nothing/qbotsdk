# Copyright (c) 2026-present Half_nothing.

"""群聊机器人：被动回复、按钮键盘、按钮回调、富媒体与撤回

环境变量：
    QQ_BOT_APP_ID / QQ_BOT_APP_SECRET  机器人凭证，必填
    QQ_BOT_IMAGE_PATH                  可选，收到 /image 时上传的本地图片路径
    QQ_BOT_SESSION_FILE                可选，会话落盘路径，重启后直接 Resume

在群里 @ 机器人发这些指令：
    /button   回一条带两个按钮的消息（一个回调、一个打开链接）
    /image    上传 QQ_BOT_IMAGE_PATH 指向的图片，再以富媒体消息发出去
    /recall   撤回机器人上一条 /button 消息
    其它文本  原样回一句
点按钮会走 INTERACTION_CREATE，示例里回应一下再打印按钮数据。
"""

import asyncio
import contextlib
import os
import signal
import sys
from pathlib import Path

from async_event_bus import EventContext
from loguru import logger

from qbotsdk import Bot, FileSessionStorage, WebSocketAdapter
from qbotsdk.model import MessageMarkdown
from qbotsdk.model.event import GroupAtMessageCreate, InteractionCreate
from qbotsdk.model.keyboard import (
    Button,
    ButtonAction,
    ButtonActionType,
    ButtonPermission,
    ButtonPermissionType,
    ButtonRenderData,
    ButtonStyle,
    Keyboard,
    KeyboardContent,
    KeyboardRow,
)
from qbotsdk.model.media import FileType, MediaInfo

# 打开 TRACE 级别，输出底层网络日志；只看业务输出可以改成 INFO
logger.remove()
logger.add(sys.stderr, level="TRACE")

# 记下机器人自己发出去的消息，撤回时要用 message id
_sent: dict[str, str] = {}


def build_keyboard() -> Keyboard:
    """两个按钮：一个回调本机，一个打开链接。"""

    callback = Button(
        id="ping",
        render_data=ButtonRenderData(
            label="点我一下",
            visited_label="点过了",
            style=ButtonStyle.BLUE,
        ),
        action=ButtonAction(
            type=ButtonActionType.CALLBACK,
            data="ping",
            permission=ButtonPermission(type=ButtonPermissionType.EVERYONE),
        ),
    )
    link = Button(
        id="docs",
        render_data=ButtonRenderData(
            label="打开文档",
            visited_label="打开文档",
            style=ButtonStyle.GREY,
        ),
        action=ButtonAction(
            type=ButtonActionType.LINK,
            data="https://github.com/half-nothing/qbotsdk",
            permission=ButtonPermission(type=ButtonPermissionType.EVERYONE),
        ),
    )
    return Keyboard(content=KeyboardContent(rows=[KeyboardRow(buttons=[callback, link])]))


def build_adapter() -> WebSocketAdapter:
    session_file = os.environ.get("QQ_BOT_SESSION_FILE")
    return WebSocketAdapter(
        # 会话落盘，进程重启后直接 Resume；不设则用内存存储
        session_storage=FileSessionStorage(session_file) if session_file else None,
    )


async def send_button(bot: Bot, event: GroupAtMessageCreate) -> None:
    receipt = await bot.api.group.send_message(
        event.group_openid,
        # 按钮只在 Markdown 消息上渲染；只给 content 的话 SDK 会自动升成 Markdown
        markdown=MessageMarkdown(content="**试试下面的按钮**"),
        keyboard=build_keyboard(),
        reply_to=event.id,
    )
    _sent[event.group_openid] = receipt.id
    print(f"已发送按钮消息 id={receipt.id}")


async def send_image(bot: Bot, event: GroupAtMessageCreate) -> None:
    raw_path = os.environ.get("QQ_BOT_IMAGE_PATH")
    if not raw_path:
        await event.reply("没有设置 QQ_BOT_IMAGE_PATH，跳过富媒体演示")
        return

    path = Path(raw_path)
    # 上传拿 file_info，再拿它发一条富媒体消息
    uploaded = await bot.api.group.upload_file(
        event.group_openid,
        FileType.IMAGE,
        file_data=path.read_bytes(),
        file_name=path.name,
    )
    await bot.api.group.send_message(
        event.group_openid,
        media=MediaInfo(file_info=uploaded.file_info),
        reply_to=event.id,
    )
    print(f"已发送图片 file_uuid={uploaded.file_uuid} ttl={uploaded.ttl}")


async def main() -> None:
    async with Bot(
        app_id=os.environ["QQ_BOT_APP_ID"],
        client_secret=os.environ["QQ_BOT_APP_SECRET"],
        adapter=build_adapter(),
    ) as bot:

        @bot.on(GroupAtMessageCreate)
        async def on_group_at(ctx: EventContext[GroupAtMessageCreate]) -> None:
            event = ctx.event
            text = event.content.strip()

            if text == "/button":
                await send_button(bot, event)
            elif text == "/image":
                await send_image(bot, event)
            elif text == "/recall":
                message_id = _sent.pop(event.group_openid, None)
                if message_id:
                    await bot.api.group.recall_message(event.group_openid, message_id)
                    await event.reply("已撤回上一条消息")
                else:
                    await event.reply("还没有可撤回的消息")
            else:
                await event.reply(f"收到：{text}")

        @bot.on(InteractionCreate)
        async def on_interaction(ctx: EventContext[InteractionCreate]) -> None:
            event = ctx.event
            data = event.data.resolved.button_data if event.data and event.data.resolved else None
            print(f"[按钮] type={event.type.name} data={data}")

            # 消息按钮与快捷菜单必须回应，否则客户端一直转圈
            if event.needs_response:
                await event.respond()

        await bot.start()
        print("WebSocket 已连接，在群里 @ 机器人试试 /button、/image、/recall")

        stopped = asyncio.Event()
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            # Windows 的 ProactorEventLoop 不支持信号处理，靠 Ctrl+C 抛 KeyboardInterrupt
            with contextlib.suppress(NotImplementedError):
                loop.add_signal_handler(sig, stopped.set)
        with contextlib.suppress(KeyboardInterrupt, asyncio.CancelledError):
            await stopped.wait()


if __name__ == "__main__":
    asyncio.run(main())
