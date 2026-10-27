from typing import TYPE_CHECKING

from .base import SessionData, SessionStorage
from .file import FileSessionStorage
from .memory import MemorySessionStorage

if TYPE_CHECKING:
    from .redis import RedisSessionStorage

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
