# Copyright (c) 2026-present Half_nothing.

"""网关连接所需的状态与接入点信息。"""

from __future__ import annotations

from pydantic import Field

from ..model.base import QQModel


class SessionStartLimit(QQModel):
    """同一 AppID 的建连配额。"""

    total: int = Field(alias="total")
    remaining: int = Field(alias="remaining")
    reset_after: int = Field(alias="reset_after", description="配额重置的剩余毫秒")
    max_concurrency: int = Field(alias="max_concurrency")


class GatewayInfo(QQModel):
    """GET /gateway/bot 的返回值。"""

    url: str = Field(alias="url")
    shards: int = Field(alias="shards")
    session_start_limit: SessionStartLimit = Field(alias="session_start_limit")


class SessionState:
    """一次连接会话的状态。

    只有 session_id 非空才允许 Resume
    seq 是最后收到的事件序号，跳与 Resume 都要带它
    """

    __slots__ = ("seq", "session_id")

    def __init__(self) -> None:
        self.session_id: str | None = None
        self.seq: int | None = None

    @property
    def can_resume(self) -> bool:
        return self.session_id is not None

    def update(self, session_id: str | None = None, seq: int | None = None) -> None:
        if session_id is not None:
            self.session_id = session_id
        if seq is not None:
            self.seq = seq

    def reset(self) -> None:
        """会话作废。"""

        self.session_id = None
        self.seq = None

    def __repr__(self) -> str:
        return f"SessionState(session_id={self.session_id!r}, seq={self.seq!r})"
