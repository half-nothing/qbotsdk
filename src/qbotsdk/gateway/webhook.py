# Copyright (c) 2026-present Half_nothing.

"""Webhook 方式的纯函数"""

from __future__ import annotations

from binascii import Error

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from .payload import GatewayPayload

# Ed25519 私钥种子的长度
_SEED_SIZE = 32

# HTTP Callback ACK 的 opcode
_ACK_OP = 12


def _seed_bytes(app_secret: str) -> bytes:
    """把 botSecret 循环重复到 32 字节，作为 Ed25519 的私钥种子。"""

    raw = app_secret.encode("utf-8")
    if not raw:
        raise ValueError("app_secret must not be empty")
    return (raw * (_SEED_SIZE // len(raw) + 1))[:_SEED_SIZE]


def _private_key(app_secret: str) -> Ed25519PrivateKey:
    return Ed25519PrivateKey.from_private_bytes(_seed_bytes(app_secret))


def build_validation_response(app_secret: str, plain_token: str, event_ts: str) -> dict[str, str]:
    """op 13 地址验证的应答体，签名体是 event_ts + plain_token。"""

    signature = _private_key(app_secret).sign(f"{event_ts}{plain_token}".encode())
    return {"plain_token": plain_token, "signature": signature.hex()}


def verify_webhook_signature(app_secret: str, signature: str, timestamp: str, body: bytes) -> bool:
    """校验回调请求头 X-Signature-Ed25519。"""

    try:
        raw = bytes.fromhex(signature)
    except (Error, ValueError):
        return False

    public_key = _private_key(app_secret).public_key()
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
