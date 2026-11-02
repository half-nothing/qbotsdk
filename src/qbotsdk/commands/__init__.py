# Copyright (c) 2026-present Half_nothing.

"""命令与按钮回调, 注册、匹配、执行与结果映射。"""

from __future__ import annotations

from .context import (
    C2CContext,
    ChannelContext,
    Context,
    GroupContext,
    InteractionContext,
    Kind,
    Sender,
)
from .convert import (
    DEFAULT_CONVERTERS,
    Converter,
    FloatConverter,
    IntConverter,
    MentionConverter,
    RestConverter,
    StrConverter,
)
from .errors import CommandError, GuardFailed, PermissionDenied, UsageError
from .execution import ExecutionResult, Status
from .messages import Messages
from .reply import Reply
from .route import (
    AckPolicy,
    Binding,
    CallbackHandler,
    CommandHandler,
    PayloadTrigger,
    Route,
    TextTrigger,
    Trigger,
    event_types,
)
from .router import Guard, Middleware, Router, strip_prefix
from .template import PathTemplate, Placeholder, compile_template
from .trie import Node, Partial, TextMatch, insert, resolve, usage_for

__all__ = [
    "DEFAULT_CONVERTERS",
    "AckPolicy",
    "Binding",
    "C2CContext",
    "CallbackHandler",
    "ChannelContext",
    "CommandError",
    "CommandHandler",
    "Context",
    "Converter",
    "ExecutionResult",
    "FloatConverter",
    "GroupContext",
    "Guard",
    "GuardFailed",
    "IntConverter",
    "InteractionContext",
    "Kind",
    "MentionConverter",
    "Messages",
    "Middleware",
    "Node",
    "Partial",
    "PathTemplate",
    "PayloadTrigger",
    "PermissionDenied",
    "Placeholder",
    "Reply",
    "RestConverter",
    "Route",
    "Router",
    "Sender",
    "Status",
    "StrConverter",
    "TextMatch",
    "TextTrigger",
    "Trigger",
    "UsageError",
    "compile_template",
    "event_types",
    "insert",
    "resolve",
    "strip_prefix",
    "usage_for",
]
