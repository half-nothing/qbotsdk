# Copyright (c) 2026-present Half_nothing.

"""命令层对用户可见的文案, 可按字段覆盖。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Messages:
    """路由器的默认文案。"""

    denied: str = "You do not have permission to use this command."
    internal_error: str = "Something went wrong while handling this command."
    missing_arguments: str = "Invalid arguments."
    usage: str = "Invalid arguments. Usage: {usage}"
    unknown_command: str = "Unknown command."
