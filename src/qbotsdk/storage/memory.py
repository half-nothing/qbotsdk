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

"""内存存储, 进程内保留会话, 适合测试场景。"""

from __future__ import annotations

from typing import override

from .base import SessionData, SessionStorage

__all__ = ["MemorySessionStorage"]


class MemorySessionStorage(SessionStorage):
    """把会话放在进程内存里。"""

    __slots__ = ("_data",)

    def __init__(self) -> None:
        self._data: SessionData | None = None

    async def load(self) -> SessionData | None:
        return self._data

    async def save(self, data: SessionData) -> None:
        self._data = data

    async def clear(self) -> None:
        self._data = None

    @override
    async def close(self) -> None:
        # 内存存储不需要任何收尾工作
        pass
