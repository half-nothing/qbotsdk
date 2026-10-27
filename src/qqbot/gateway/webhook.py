# Copyright (c) 2026-present Half_nothing.

"""Webhook 方式的纯函数：地址验证、请求验签、回调解析。

这一层不依赖 aiohttp，自带 HTTP 框架的项目直接调这几个函数就能对接平台；
需要开箱即用的服务器见 `webhook_server`（T6）。
"""

from __future__ import annotations

import binascii

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from .payload import GatewayPayload

#: Ed25519 私钥种子的长度
_SEED_SIZE = 32

#: HTTP Callback ACK 的 opcode
_ACK_OP = 12


def _seed_bytes(bot_secret: str) -> bytes:
    """把 botSecret 循环重复到 32 字节，作为 Ed25519 的私钥种子。

    官方示例是 Go 的 `strings.Repeat(secret, 2)`：只保证「至少 32 字节再截断」。
    所以这里必须按循环重复写，不能写成 `secret * 2` —— secret 长度不整除 32 时
    两者结果不同（示例的 secret 正好 16 字节，看不出区别）。
    """

    raw = bot_secret.encode("utf-8")
    if not raw:
        raise ValueError("bot_secret must not be empty")
    return (raw * (_SEED_SIZE // len(raw) + 1))[:_SEED_SIZE]


def _private_key(bot_secret: str) -> Ed25519PrivateKey:
    return Ed25519PrivateKey.from_private_bytes(_seed_bytes(bot_secret))


def build_validation_response(bot_secret: str, plain_token: str, event_ts: str) -> dict[str, str]:
    """op 13 地址验证的应答体，签名体是 `event_ts + plain_token`。"""

    signature = _private_key(bot_secret).sign(f"{event_ts}{plain_token}".encode())
    return {"plain_token": plain_token, "signature": signature.hex()}


def verify_webhook_signature(bot_secret: str, signature: str, timestamp: str, body: bytes) -> bool:
    """校验回调请求头 `X-Signature-Ed25519`。

    签名体是 `timestamp + body`，其中 `body` 必须是原始字节，不能重新序列化 JSON，
    否则签名对不上。签名格式不对直接返回 `False`：这是外部输入，不该抛异常。
    """

    try:
        raw = bytes.fromhex(signature)
    except (binascii.Error, ValueError):
        return False

    public_key = _private_key(bot_secret).public_key()
    try:
        public_key.verify(raw, timestamp.encode("utf-8") + body)
    except InvalidSignature:
        return False
    return True


def parse_webhook_event(body: bytes) -> GatewayPayload:
    """把回调请求体解析成网关帧。"""

    return GatewayPayload.model_validate_json(body)


def build_ack_payload() -> dict[str, object]:
    """回调处理完要回的 op 12 HTTP Callback ACK。"""

    return {"op": _ACK_OP, "d": {}}
