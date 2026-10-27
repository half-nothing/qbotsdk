# Copyright (c) 2026-present Half_nothing.

"""Webhook 纯函数的用例，签名向量逐字用官方示例。"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from qqbot.gateway.webhook import (
    build_ack_payload,
    build_validation_response,
    parse_webhook_event,
    verify_webhook_signature,
)
from tests.support import read_frame

#: 官方示例里的 AppID / botSecret / plain_token / event_ts
BOT_SECRET = "DG5g3B4j9X2KOErG"
PLAIN_TOKEN = "Arq0D5A61EgUu4OxUvOp"
EVENT_TS = "1725442341"
OFFICIAL_SIGNATURE = (
    "87befc99c42c651b3aac0278e71ada338433ae26fcb24307bdc5ad38c1adc2d01"
    "bcfcadc0842edac85e85205028a1132afe09280305f13aa6909ffc2d652c706"
)


def test_validation_response_matches_official_vector() -> None:
    response = build_validation_response(BOT_SECRET, PLAIN_TOKEN, EVENT_TS)

    assert response == {"plain_token": PLAIN_TOKEN, "signature": OFFICIAL_SIGNATURE}


def test_seed_repeats_secret_for_odd_length() -> None:
    """5 字节 secret 要重复到 32 字节，写死 `secret * 2` 会得到另一个签名。"""

    response = build_validation_response("abcde", PLAIN_TOKEN, EVENT_TS)

    assert response["signature"] == (
        "f032af1a43d7ffd78f79ae7cee7783460d41bfa2cbf98a5eb5e8cd9e72747680"
        "6c53e85a7c1c1cfced7db528c83312b0b415fa1e70e424e5b7fd9c29bbd9890d"
    )


def test_empty_secret_is_rejected() -> None:
    with pytest.raises(ValueError, match="bot_secret must not be empty"):
        build_validation_response("", PLAIN_TOKEN, EVENT_TS)


def test_verify_accepts_official_signature() -> None:
    """验证签名签的是 `event_ts + plain_token`，形状与 `timestamp + body` 相同。"""

    assert verify_webhook_signature(BOT_SECRET, OFFICIAL_SIGNATURE, EVENT_TS, PLAIN_TOKEN.encode())


def test_verify_rejects_tampered_body() -> None:
    assert not verify_webhook_signature(
        BOT_SECRET, OFFICIAL_SIGNATURE, EVENT_TS, b"Arq0D5A61EgUu4OxUvOpX"
    )


def test_verify_rejects_wrong_timestamp() -> None:
    assert not verify_webhook_signature(
        BOT_SECRET, OFFICIAL_SIGNATURE, "1725442342", PLAIN_TOKEN.encode()
    )


def test_verify_rejects_malformed_signature() -> None:
    assert not verify_webhook_signature(BOT_SECRET, "zz-not-hex", EVENT_TS, b"{}")
    assert not verify_webhook_signature(BOT_SECRET, "abc", EVENT_TS, b"{}")


def test_parse_webhook_event_reads_frame() -> None:
    payload = parse_webhook_event(read_frame("gateway_group_at_message_create.json").encode())

    assert payload.t == "GROUP_AT_MESSAGE_CREATE"
    assert payload.s == 2


def test_parse_webhook_event_rejects_invalid_json() -> None:
    with pytest.raises(ValidationError):
        parse_webhook_event(b"not json")


def test_ack_payload_is_op_12() -> None:
    assert build_ack_payload() == {"op": 12, "d": {}}
