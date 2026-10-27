# Copyright (c) 2026-present Half_nothing.

"""网关层的协议常量与载荷模型。"""

from __future__ import annotations

from enum import IntEnum, StrEnum
from typing import Any, ClassVar, Final

from pydantic import Field

from ..model.base import QQModel


class OpCode(IntEnum):
    """官方 payload 的 op 全表。"""

    DISPATCH = 0
    HEARTBEAT = 1
    IDENTIFY = 2
    RESUME = 6
    RECONNECT = 7
    INVALID_SESSION = 9
    HELLO = 10
    HEARTBEAT_ACK = 11
    HTTP_CALLBACK_ACK = 12
    CALLBACK_VALIDATION = 13


class Intents:
    """intents 位。官方分成基础事件与需申请两档，默认只开基础事件那一档。"""

    GUILDS: ClassVar[int] = 1 << 0
    GUILD_MEMBERS: ClassVar[int] = 1 << 1
    GUILD_MESSAGES: ClassVar[int] = 1 << 9
    GUILD_MESSAGE_REACTIONS: ClassVar[int] = 1 << 10
    DIRECT_MESSAGE: ClassVar[int] = 1 << 12
    GROUP_AND_C2C_EVENT: ClassVar[int] = 1 << 25
    INTERACTION: ClassVar[int] = 1 << 26
    MESSAGE_AUDIT: ClassVar[int] = 1 << 27
    FORUMS_EVENT: ClassVar[int] = 1 << 28
    AUDIO_ACTION: ClassVar[int] = 1 << 29
    PUBLIC_GUILD_MESSAGES: ClassVar[int] = 1 << 30

    # 传了没权限的 intent 会被直接断开
    DEFAULT: ClassVar[int] = GUILDS | PUBLIC_GUILD_MESSAGES | GROUP_AND_C2C_EVENT


class GatewayPayload(QQModel):
    """网关下发的任意一帧。d 的结构由 op 与 t 决定，这里不做细化。"""

    id: str | None = Field(alias="id", default=None)
    op: OpCode = Field(alias="op")
    d: Any = Field(alias="d", default=None)
    s: int | None = Field(alias="s", default=None)
    t: str | None = Field(alias="t", default=None)


class Frame(QQModel):
    """整帧的基类。"""

    op: OpCode

    def to_json(self) -> str:
        """序列化成可直接经 WebSocket 发送的文本。"""

        return self.model_dump_json()


class HelloData(QQModel):
    """op 10 的 d。"""

    heartbeat_interval: int


class HelloFrame(Frame):
    """连接建立后服务端下发的第一帧。"""

    op: OpCode = OpCode.HELLO
    d: HelloData


class IdentifyData(QQModel):
    """op 2 的 d。"""

    token: str
    intents: int
    shard: list[int]
    properties: dict[str, str]


class IdentifyFrame(Frame):
    """鉴权帧。"""

    op: OpCode = OpCode.IDENTIFY
    d: IdentifyData


class ResumeData(QQModel):
    """op 6 的 d。"""

    token: str
    session_id: str
    seq: int | None = None


class ResumeFrame(Frame):
    """恢复会话帧。"""

    op: OpCode = OpCode.RESUME
    d: ResumeData


class HeartbeatFrame(Frame):
    """心跳帧；d 是最近收到的 s，一次都还没收到就是 null。"""

    op: OpCode = OpCode.HEARTBEAT
    d: int | None = None


class HeartbeatAckFrame(Frame):
    """心跳回执。"""

    op: OpCode = OpCode.HEARTBEAT_ACK


class CloseAction(StrEnum):
    """收到关闭码之后该做什么。"""

    IDENTIFY = "identify"
    RESUME = "resume"
    STOP = "stop"


class GatewayCloseCode(IntEnum):
    """官方给的 WebSocket 关闭码。"""

    INVALID_OPCODE = 4001
    INVALID_PAYLOAD = 4002
    INVALID_SESSION_ID = 4006
    SEQ_ERROR = 4007
    RATE_LIMITED = 4008
    SESSION_EXPIRED = 4009
    INVALID_SHARD = 4010
    TOO_MANY_GUILDS = 4011
    INVALID_VERSION = 4012
    INVALID_INTENT = 4013
    DISALLOWED_INTENT = 4014
    SANDBOX_ONLY = 4914
    BANNED = 4915


_CLOSE_ACTIONS: Final[dict[int, CloseAction]] = {
    GatewayCloseCode.INVALID_OPCODE: CloseAction.IDENTIFY,
    GatewayCloseCode.INVALID_PAYLOAD: CloseAction.IDENTIFY,
    GatewayCloseCode.INVALID_SESSION_ID: CloseAction.IDENTIFY,
    GatewayCloseCode.SEQ_ERROR: CloseAction.IDENTIFY,
    GatewayCloseCode.RATE_LIMITED: CloseAction.RESUME,
    GatewayCloseCode.SESSION_EXPIRED: CloseAction.RESUME,
    GatewayCloseCode.INVALID_SHARD: CloseAction.STOP,
    GatewayCloseCode.TOO_MANY_GUILDS: CloseAction.STOP,
    GatewayCloseCode.INVALID_VERSION: CloseAction.STOP,
    GatewayCloseCode.INVALID_INTENT: CloseAction.STOP,
    GatewayCloseCode.DISALLOWED_INTENT: CloseAction.STOP,
    GatewayCloseCode.SANDBOX_ONLY: CloseAction.STOP,
    GatewayCloseCode.BANNED: CloseAction.STOP,
}

# 4900~4913 是官方内部的连接被重置区间, 重连即可
_INTERNAL_ERROR_RANGE: Final[range] = range(4900, 4914)


def close_action(code: int) -> CloseAction:
    """按关闭码决定重连方式；未知码按不可恢复处理，避免死循环重连。"""

    if code in _CLOSE_ACTIONS:
        return _CLOSE_ACTIONS[code]
    if code in _INTERNAL_ERROR_RANGE:
        return CloseAction.IDENTIFY
    return CloseAction.STOP


class GatewayError(Exception):
    """网关层的通用错误。"""


class GatewayClosedError(GatewayError):
    """对端用关闭码终止了连接，且该码不允许简单重试。"""

    def __init__(self, code: int, action: CloseAction, reason: str = "") -> None:
        self.code = code
        self.action = action
        self.reason = reason
        detail = f"{code} ({action.value})"
        if reason:
            detail = f"{detail}: {reason}"
        super().__init__(f"gateway closed with {detail}")
