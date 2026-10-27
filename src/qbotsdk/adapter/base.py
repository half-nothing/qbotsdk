# Copyright (c) 2026-present Half_nothing.

"""适配器抽象：事件从哪里来由使用者决定, 核心只认这个接口。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from qbotsdk.api import ApiClient
    from qbotsdk.gateway.dispatcher import Dispatcher
    from qbotsdk.module.http_client import HTTPClient


@dataclass(slots=True)
class AdapterContext:
    """适配器启动时能拿到的东西, 由 Bot.start() 组装。"""

    http: HTTPClient
    api: ApiClient
    dispatcher: Dispatcher


class Adapter(ABC):
    """接入方式的公共接口。"""

    @abstractmethod
    async def start(self, context: AdapterContext) -> None:
        """开始收事件并立即返回, 后台任务由适配器自己持有。"""

    @abstractmethod
    async def stop(self) -> None:
        """停止收事件并释放资源, 允许重复调用。"""
