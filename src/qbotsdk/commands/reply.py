# Copyright (c) 2026-present Half_nothing.

"""处理器对要回什么的统一描述。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from qbotsdk.model.keyboard import Keyboard


@dataclass(frozen=True, slots=True)
class Reply:
    """处理器返回的回复描述, 路由器据此发一条消息。"""

    text: str | None = None
    silent: bool = False
    keyboard: Keyboard | None = None
    markdown: bool = False
    mention: bool | None = None
    """正文前是否带 @发送者；`None` 表示跟随命令与路由器的默认设置。"""

    @classmethod
    def ok(cls) -> Reply:
        """什么也不发, 常用于已经自己 `ctx.reply()` 过的处理器。"""

        return cls(silent=True)

    @property
    def should_send(self) -> bool:
        """是否需要由路由器发一条消息。"""

        return not self.silent and self.text is not None
