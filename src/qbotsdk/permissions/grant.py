# Copyright (c) 2026-present Half_nothing.

"""授予、角色与授权码中间态。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Scope = Literal["global", "group"]


@dataclass(frozen=True, slots=True)
class Grant:
    """一条授予, allow=False就是拒绝, 存储里写成 -key。"""

    permission: str
    allow: bool = True

    def __post_init__(self) -> None:
        if not self.permission:
            raise ValueError("permission must not be empty")
        if any(char.isspace() for char in self.permission):
            raise ValueError("permission must not contain whitespace")

    @property
    def encoded(self) -> str:
        """存储与 show 输出用的字符串形态。"""

        return self.permission if self.allow else f"-{self.permission}"

    @classmethod
    def decode(cls, text: str) -> Grant:
        """把 -key / key 解析回授予。"""

        if not text:
            raise ValueError("permission must not be empty")
        if text.startswith("-"):
            return cls(text[1:], allow=False)
        return cls(text, allow=True)


@dataclass(frozen=True, slots=True)
class Role:
    """可继承的角色。"""

    name: str
    grants: tuple[Grant, ...] = ()
    parents: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("role name must not be empty")


@dataclass(frozen=True, slots=True)
class PendingGrant:
    """授权码/按钮背后的待领取授予, 领取之前只记键与作用域。"""

    permission: str
    scope: Scope = "group"
    group_openid: str | None = None

    def __post_init__(self) -> None:
        if not self.permission:
            raise ValueError("permission must not be empty")
        if self.scope == "group" and not self.group_openid:
            raise ValueError("a group-scoped pending grant needs group_openid")
