# Copyright (c) 2026-present Half_nothing.

"""会话存储的抽象，谁来决定会话放哪，由使用者在适配器上指定。"""

from __future__ import annotations

from abc import ABC, abstractmethod

from pydantic import Field

from qbotsdk.model.base import QQModel


class SessionData(QQModel):
    """一条可续连的会话，seq 是最后收到的事件序号。"""

    session_id: str = Field(alias="session_id")
    seq: int | None = Field(default=None, alias="seq")


class SessionStorage(ABC):
    """会话存储接口。

    内置内存与文件两种实现，Redis 之类的外部存储按同一接口补上即可。
    实现要能容忍并发调用，同一个实例只服务一个 GatewayConnection。
    """

    @abstractmethod
    async def load(self) -> SessionData | None:
        """读出上次的会话，没有则返回 None。"""

    @abstractmethod
    async def save(self, data: SessionData) -> None:
        """写下当前会话，实现内部可以合并高频写入。"""

    @abstractmethod
    async def clear(self) -> None:
        """会话已作废，把存的东西删掉。"""

    async def close(self) -> None:  # noqa: B027
        """释放资源，退出前调用；默认什么都不做。"""
        pass
