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

from typing import TYPE_CHECKING

from .base import SessionData as SessionData
from .base import SessionStorage as SessionStorage
from .file import FileSessionStorage as FileSessionStorage
from .memory import MemorySessionStorage as MemorySessionStorage

if TYPE_CHECKING:
    from .redis import RedisSessionStorage as RedisSessionStorage

__all__ = [
    "FileSessionStorage",
    "MemorySessionStorage",
    "RedisSessionStorage",
    "SessionData",
    "SessionStorage",
]


def __getattr__(name: str) -> object:
    if name == "RedisSessionStorage":
        from .redis import RedisSessionStorage

        return RedisSessionStorage
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    return sorted(__all__)
