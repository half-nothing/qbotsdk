# Copyright (c) 2026-present Half_nothing.

"""把回调请求翻译成事件的高层处理器。

和 `webhook.py` 的纯函数相比，这里一次做完解包、地址校验应答、验签，再把事件交给后台。
把回调接进自己已有的 aiohttp 应用时用它；要自己控制响应流程，就直接用 `webhook.py` 里的纯函数。
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING

from aiohttp.web import Request, Response, StreamResponse, json_response
from loguru import logger
from pydantic import ValidationError

from .payload import GatewayPayload, OpCode
from .webhook import (
    build_ack_payload,
    build_validation_response,
    verify_webhook_signature,
)

if TYPE_CHECKING:
    from .dispatcher import Dispatcher

# 平台推送回调时带的两个头
SIGNATURE_HEADER = "X-Signature-Ed25519"
TIMESTAMP_HEADER = "X-Signature-Timestamp"

WebhookHandler = Callable[[Request], Awaitable[StreamResponse]]


def build_webhook_handler(dispatcher: Dispatcher, app_secret: str) -> WebhookHandler:
    """返回aiohttp能直接使用的处理函数。

    op 13 是管理端配置回调地址时的地址校验，直接按 botSecret 签名应答；
    其余请求先验签，签名缺失或不对回 401，报文不是合法 JSON 回 400；
    通过后回 {"op": 12, "d": {}}，事件交给分发器后由后台任务处理，不等处理器跑完。
    """

    async def handle(request: Request) -> StreamResponse:
        # 签名体是时间戳 + 原始报文, 所以只能读原始字节, 不能先 request.json()
        body = await request.read()
        try:
            payload = GatewayPayload.model_validate_json(body)
        except ValidationError:
            return Response(status=400, text="invalid payload")

        if payload.op is OpCode.CALLBACK_VALIDATION:
            return _validation_response(payload, app_secret)

        signature = request.headers.get(SIGNATURE_HEADER, "")
        timestamp = request.headers.get(TIMESTAMP_HEADER, "")
        if not signature or not timestamp:
            return Response(status=401, text="missing signature")
        if not verify_webhook_signature(app_secret, signature, timestamp, body):
            return Response(status=401, text="invalid signature")

        # handle 只起一个后台任务就返回, 处理器本身不等
        # 所以平台收到 ACK 时事件往往还没处理完
        try:
            dispatcher.handle(payload)
        except ValidationError as exc:
            # 报文合法但字段对不上是我们的解析问题, 重推同样解不出来, 记日志后照常 ACK
            logger.warning("Dropping webhook event {}: {!r}", payload.t, exc)
        return json_response(build_ack_payload())

    return handle


def _validation_response(payload: GatewayPayload, app_secret: str) -> Response:
    data = payload.d
    if not isinstance(data, dict):
        return Response(status=400, text="invalid validation payload")
    plain_token = data.get("plain_token")
    event_ts = data.get("event_ts")
    if not isinstance(plain_token, str) or not isinstance(event_ts, str):
        return Response(status=400, text="invalid validation payload")
    return json_response(build_validation_response(app_secret, plain_token, event_ts))
