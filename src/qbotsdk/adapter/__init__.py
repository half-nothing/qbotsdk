# Copyright (c) 2026-present Half_nothing.

"""适配器：核心不内置任何接入方式, 使用者显式选择或自己实现。"""

from .base import Adapter, AdapterContext
from .webhook import WebhookAdapter
from .websocket import WebSocketAdapter

__all__ = ["Adapter", "AdapterContext", "WebSocketAdapter", "WebhookAdapter"]
