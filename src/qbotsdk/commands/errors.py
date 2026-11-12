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

"""命令层异常, 路由器统一把它们转成回复。"""

from __future__ import annotations

__all__ = ["CommandError", "GuardFailed", "PermissionDenied", "UsageError"]


class CommandError(Exception):
    """命令层错误的基类。

    路由器的错误映射按子类挑选默认文案
    """

    def __init__(self, message: str = "") -> None:
        super().__init__(message)
        self.message = message

    @property
    def user_message(self) -> str:
        """直接展示给用户的文案, 空串表示交给路由器的默认文案。"""

        return self.message


class UsageError(CommandError):
    """参数不合法: 缺参数、转换失败、用法不对。"""


class PermissionDenied(CommandError):
    """当前主体没有使用该命令的权限。"""


class GuardFailed(CommandError):
    """守卫拦下了这次调用, 属于非权限类的前置条件。"""
