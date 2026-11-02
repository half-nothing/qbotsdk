# Copyright (c) 2026-present Half_nothing.

"""一次分派的结局, `Router.handle()` 的返回值。"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .errors import CommandError
    from .reply import Reply


class Status(StrEnum):
    """这次分派走到了哪一步。"""

    """没有任何路由匹配上, 路由器没有执行任何处理器。"""
    NOT_FOUND = "not_found"

    """匹配到路由并且处理器正常返回。"""
    HANDLED = "handled"

    """守卫或权限检查拒绝了这次调用。"""
    DENIED = "denied"

    """处理器或中间件抛了异常, 路由器已经把它转换成文案。"""
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class ExecutionResult:
    """命令执行结果。"""

    status: Status = Status.NOT_FOUND
    command: str | None = None
    reply: Reply | None = None
    replied: bool = False
    error: CommandError | None = None

    @property
    def handled(self) -> bool:
        """命令层是否处理了这条事件。"""

        return self.status is not Status.NOT_FOUND

    def __bool__(self) -> bool:
        return self.handled
