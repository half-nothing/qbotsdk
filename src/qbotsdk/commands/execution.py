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

"""一次分派的结局, `Router.handle()` 的返回值。"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from .errors import CommandError
    from .reply import Reply

__all__ = ["ExecutionResult", "Status"]


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
    handler: Callable[..., Awaitable[object]] | None = field(default=None, repr=False)
    reply: Reply | None = None
    replied: bool = False
    error: CommandError | None = None

    @property
    def handled(self) -> bool:
        """命令层是否处理了这条事件。"""

        return self.status is not Status.NOT_FOUND

    def __bool__(self) -> bool:
        return self.handled
