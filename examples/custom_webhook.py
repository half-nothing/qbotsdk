# Copyright (c) 2026-present Half_nothing.

"""把 Webhook 接进自己已有的 aiohttp 应用

与 `webhook.py` 的区别：那边用 `WebhookAdapter` 让 SDK 自己起服务，这边复用你现有的
aiohttp 应用与中间件（鉴权、日志、限流都按你自己的来）。

回调处理有两种写法，这里同时挂在两条路径上方便对照，实际项目里挑一种就行：

- `/qbotsdk`：直接用 `build_webhook_handler`，解包、op 13 应答、验签、回 ACK 都在里面。
- `/qbotsdk-manual`：只借四个纯函数自己拼一份，适合要自定义响应体或塞进别的框架。
    build_validation_response  应答平台的回调地址校验（op 13）
    verify_webhook_signature   校 X-Signature-Ed25519 + X-Signature-Timestamp
    parse_webhook_event        把报文解析成 GatewayPayload
    build_ack_payload          应答 op 12

环境变量：
    QQ_BOT_APP_ID / QQ_BOT_APP_SECRET  机器人凭证
    QQ_BOT_SECRET                      botSecret，用于验签与 op 13 应答
    QQ_BOT_WEBHOOK_PORT                本地监听端口，默认 8080
"""

from __future__ import annotations

import asyncio
import os
import sys
from typing import TYPE_CHECKING

from aiohttp import web
from async_event_bus import EventContext
from loguru import logger

from qbotsdk import Bot, build_webhook_handler
from qbotsdk.gateway import (
    OpCode,
    build_ack_payload,
    build_validation_response,
    parse_webhook_event,
    verify_webhook_signature,
)
from qbotsdk.model.event import GroupAtMessageCreate

if TYPE_CHECKING:
    from qbotsdk.gateway.dispatcher import Dispatcher

logger.remove()
logger.add(sys.stderr, level="TRACE")

# 平台推送回调时带的两个头
SIGNATURE_HEADER = "X-Signature-Ed25519"
TIMESTAMP_HEADER = "X-Signature-Timestamp"


def build_handler_by_hand(dispatcher: Dispatcher, bot_secret: str) -> web.Handler:
    """用纯函数拼一份处理函数，这也是SDK的高层封装具体做的事情。

    当然提供的函数也是经过封装的，还有更底层的操作，但这里我们不做展开。
    """

    async def handle(request: web.Request) -> web.StreamResponse:
        # 签名体是时间戳加上原始报文，所以只能读字节，不能直接request.json()
        body = await request.read()
        try:
            payload = parse_webhook_event(body)
        except ValueError:
            return web.json_response({"error": "bad payload"}, status=400)

        # 平台配置回调地址时会先推一条 op 13，要按 botSecret 回签名
        if payload.op is OpCode.CALLBACK_VALIDATION:
            data = payload.d if isinstance(payload.d, dict) else {}
            return web.json_response(
                build_validation_response(
                    bot_secret,
                    str(data.get("plain_token", "")),
                    str(data.get("event_ts", "")),
                )
            )

        signature = request.headers.get(SIGNATURE_HEADER, "")
        timestamp = request.headers.get(TIMESTAMP_HEADER, "")
        if not signature or not timestamp:
            return web.json_response({"error": "missing signature"}, status=401)
        if not verify_webhook_signature(bot_secret, signature, timestamp, body):
            return web.json_response({"error": "bad signature"}, status=401)

        # 平台要求尽快 ACK，回慢了会被重推
        dispatcher.handle(payload)  # 只起后台任务，处理器本身不在这里等
        return web.json_response(build_ack_payload())

    return handle


async def main() -> None:
    bot_secret = os.environ["QQ_BOT_SECRET"]
    port = int(os.environ.get("QQ_BOT_WEBHOOK_PORT", "8080"))

    async with Bot(
        app_id=os.environ["QQ_BOT_APP_ID"],
        app_secret=os.environ["QQ_BOT_APP_SECRET"],
    ) as bot:

        @bot.on(GroupAtMessageCreate)
        async def on_group_at(ctx: EventContext[GroupAtMessageCreate]) -> None:
            event = ctx.event
            print(f"[群] {event.group_openid}: {event.content}")
            await event.reply(f"收到：{event.content}")

        app = web.Application()
        # SDK 提供的组合层
        app.router.add_post("/qbotsdk", build_webhook_handler(bot.dispatcher, bot_secret))
        # 自己用纯函数拼
        app.router.add_post("/qbotsdk-manual", build_handler_by_hand(bot.dispatcher, bot_secret))
        app.router.add_get("/healthz", lambda _: web.json_response({"ok": True}))

        runner = web.AppRunner(app)
        await runner.setup()
        # 只监听明文端口，TLS 交给前面的反向代理
        await web.TCPSite(runner, "0.0.0.0", port).start()
        print(f"已挂在自有应用上，端口 {port}，回调地址填 https://你的域名/qbotsdk")

        try:
            await asyncio.Event().wait()
        finally:
            await runner.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
