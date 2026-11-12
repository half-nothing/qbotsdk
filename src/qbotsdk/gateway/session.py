# Copyright (c) 2026-present Half_nothing.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""网关连接所需的状态与接入点信息。"""

from __future__ import annotations

from pydantic import Field

from qbotsdk.model import QQModel

__all__ = [
    "GatewayInfo",
    "SessionStartLimit",
    "SessionState",
]


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
    seq 是最后收到的事件序号, 跳与 Resume 都要带它
    intents 是建立会话时用的订阅位, Resume 不改它, 换过就得重新 Identify; 没有会话时是 0
    """

    __slots__ = ("intents", "seq", "session_id")

    def __init__(self) -> None:
        self.session_id: str | None = None
        self.seq: int | None = None
        self.intents: int = 0

    @property
    def can_resume(self) -> bool:
        return self.session_id is not None

    def update(
        self,
        session_id: str | None = None,
        seq: int | None = None,
        intents: int | None = None,
    ) -> None:
        if session_id is not None:
            self.session_id = session_id
        if seq is not None:
            self.seq = seq
        if intents is not None:
            self.intents = intents

    def reset(self) -> None:
        """会话作废。"""

        self.session_id = None
        self.seq = None
        self.intents = 0

    def __repr__(self) -> str:
        return (
            f"SessionState(session_id={self.session_id!r}, seq={self.seq!r}, "
            f"intents={self.intents!r})"
        )
