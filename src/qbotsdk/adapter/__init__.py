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

"""适配器: 核心不内置任何接入方式, 使用者显式选择或自己实现。"""

from .base import Adapter as Adapter
from .base import AdapterContext as AdapterContext
from .webhook import WebhookAdapter as WebhookAdapter
from .websocket import WebSocketAdapter as WebSocketAdapter

__all__ = [
    "Adapter",
    "AdapterContext",
    "WebSocketAdapter",
    "WebhookAdapter",
]
