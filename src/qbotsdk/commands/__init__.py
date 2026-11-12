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

"""命令与按钮回调, 注册、匹配、执行与结果映射。"""

from __future__ import annotations

from .adapters import Invocation as Invocation
from .adapters import adapt_event as adapt_event
from .context import C2CContext as C2CContext
from .context import ChannelContext as ChannelContext
from .context import Context as Context
from .context import GroupContext as GroupContext
from .context import InteractionContext as InteractionContext
from .context import Kind as Kind
from .context import Sender as Sender
from .convert import DEFAULT_CONVERTERS as DEFAULT_CONVERTERS
from .convert import Converter as Converter
from .convert import FloatConverter as FloatConverter
from .convert import IntConverter as IntConverter
from .convert import MentionConverter as MentionConverter
from .convert import RestConverter as RestConverter
from .convert import StrConverter as StrConverter
from .convert import accepts_annotation as accepts_annotation
from .errors import CommandError as CommandError
from .errors import GuardFailed as GuardFailed
from .errors import PermissionDenied as PermissionDenied
from .errors import UsageError as UsageError
from .execution import ExecutionResult as ExecutionResult
from .execution import Status as Status
from .messages import Messages as Messages
from .reply import Reply as Reply
from .route import AckPolicy as AckPolicy
from .route import Binding as Binding
from .route import CallbackHandler as CallbackHandler
from .route import CommandHandler as CommandHandler
from .route import PayloadTrigger as PayloadTrigger
from .route import Route as Route
from .route import TextTrigger as TextTrigger
from .route import Trigger as Trigger
from .route import action_of as action_of
from .route import build_binding as build_binding
from .route import check_callback_handler as check_callback_handler
from .route import event_types as event_types
from .router import Guard as Guard
from .router import Middleware as Middleware
from .router import Router as Router
from .router import strip_prefix as strip_prefix
from .template import PathTemplate as PathTemplate
from .template import Placeholder as Placeholder
from .template import compile_template as compile_template
from .trie import Node as Node
from .trie import Partial as Partial
from .trie import TextMatch as TextMatch
from .trie import insert as insert
from .trie import resolve as resolve
from .trie import usage_for as usage_for

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
    "Invocation",
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
    "accepts_annotation",
    "action_of",
    "adapt_event",
    "build_binding",
    "check_callback_handler",
    "compile_template",
    "event_types",
    "insert",
    "resolve",
    "strip_prefix",
    "usage_for"
]
