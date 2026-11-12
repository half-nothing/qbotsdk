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

"""会话存储的抽象, 谁来决定会话放哪, 由使用者在适配器上指定。"""

from __future__ import annotations

from abc import ABC, abstractmethod

from pydantic import Field

from qbotsdk.model import QQModel

__all__ = ["SessionData", "SessionStorage"]


class SessionData(QQModel):
    """一条可续连的会话, seq 是最后收到的事件序号。

    intents是建立这条会话时用的订阅位, 如果订阅发生变化需要重新Identify。
    """

    session_id: str = Field(alias="session_id")
    seq: int | None = Field(default=None, alias="seq")
    intents: int = Field(default=0, alias="intents")


class SessionStorage(ABC):
    """会话存储接口。

    实现要能容忍并发调用, 同一个实例只服务一个GatewayConnection。
    """

    @abstractmethod
    async def load(self) -> SessionData | None:
        """读取上次会话, 没有则返回 None。"""

    @abstractmethod
    async def save(self, data: SessionData) -> None:
        """写入当前会话, 实现内部可以合并高频写入。"""

    @abstractmethod
    async def clear(self) -> None:
        """会话已作废, 把存的东西删掉。"""

    @abstractmethod
    async def close(self) -> None:
        """释放资源, 退出前调用。"""
