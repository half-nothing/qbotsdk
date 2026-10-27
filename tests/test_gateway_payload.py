# Copyright (c) 2026-present Half_nothing.

"""T1：payload 解析、intents 常量、关闭码表。

快照来源：
- `gateway_ready.json`：官方 READY 示例（version / session_id / user / shard）。
- `gateway_group_at_message_create.json`：字段取自设计文档 §5.3 的官方字段表，
  事件页本身抓不到逐字示例，因此结构按字段表构造，不冒充逐字快照。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

import pytest
from pydantic import ValidationError

from qbotsdk.gateway.payload import (
    CloseAction,
    GatewayPayload,
    Intents,
    OpCode,
    close_action,
)
from qbotsdk.model.event import GroupAtMessageCreate, ReadyEvent, ResumedEvent, UnknownEvent

DATA = Path(__file__).parent / "data"


def load_frame(name: str) -> dict[str, Any]:
    raw: Any = json.loads((DATA / name).read_text(encoding="utf-8"))
    assert isinstance(raw, dict)
    return cast(dict[str, Any], raw)


def test_parse_hello_frame() -> None:
    payload = GatewayPayload.model_validate({"op": 10, "d": {"heartbeat_interval": 45000}})

    assert payload.op is OpCode.HELLO
    assert payload.d["heartbeat_interval"] == 45000
    assert payload.s is None


def test_parse_ready_snapshot() -> None:
    payload = GatewayPayload.model_validate(load_frame("gateway_ready.json"))

    assert payload.op is OpCode.DISPATCH
    assert payload.t == "READY"
    assert payload.s == 1

    event = ReadyEvent.model_validate(payload.d)
    assert event.session_id == "xxxxxx"
    assert event.shard == [0, 1]
    assert event.user.username == "abc"
    assert event.user.bot is True


def test_parse_group_at_message_create_snapshot() -> None:
    payload = GatewayPayload.model_validate(load_frame("gateway_group_at_message_create.json"))
    assert payload.t == "GROUP_AT_MESSAGE_CREATE"

    event = GroupAtMessageCreate.model_validate(payload.d)
    assert event.content == "hello"
    assert event.group_openid == "group-1"
    assert event.author.member_openid == "member-1"
    assert event.attachments[0].filename == "a.png"
    assert event.message_scene is not None
    assert event.message_scene.ext["msg_idx"] == "101"
    assert event.message_scene.ext.get("missing") is None


def test_unknown_event_keeps_raw_payload() -> None:
    raw = {"id": "guild-1", "name": "x"}
    event = UnknownEvent(t="GUILD_CREATE", data=raw)

    assert event.t == "GUILD_CREATE"
    assert event.data == raw


def test_resumed_allows_empty_body() -> None:
    assert ResumedEvent.model_validate({}) is not None


def test_default_intents() -> None:
    assert (
        Intents.DEFAULT
        == Intents.GUILDS
        | Intents.PUBLIC_GUILD_MESSAGES
        | Intents.GROUP_AND_C2C_EVENT
        | Intents.INTERACTION
    )
    assert Intents.DEFAULT & Intents.GUILD_MEMBERS == 0


@pytest.mark.parametrize(
    ("code", "action"),
    [
        (4006, CloseAction.IDENTIFY),
        (4007, CloseAction.IDENTIFY),
        (4008, CloseAction.RESUME),
        (4009, CloseAction.RESUME),
        (4010, CloseAction.STOP),
        (4011, CloseAction.STOP),
        (4013, CloseAction.STOP),
        (4014, CloseAction.STOP),
        (4914, CloseAction.STOP),
        (4915, CloseAction.STOP),
        (4900, CloseAction.IDENTIFY),
        (4913, CloseAction.IDENTIFY),
        (1000, CloseAction.STOP),
        (0, CloseAction.STOP),
    ],
)
def test_close_action_table(code: int, action: CloseAction) -> None:
    assert close_action(code) is action


def test_payload_is_frozen() -> None:
    payload = GatewayPayload.model_validate({"op": 11})

    with pytest.raises(ValidationError):
        payload.op = OpCode.HELLO
