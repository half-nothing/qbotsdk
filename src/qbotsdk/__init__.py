# Copyright (c) 2026-present Half_nothing.

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

from .adapter import Adapter, AdapterContext, WebhookAdapter, WebSocketAdapter
from .api import ApiClient
from .bot import Bot
from .exceptions import APIError, ErrorCode, QQBotError, RateLimitExceededError, TransportError
from .gateway import WebhookServer, build_webhook_handler
from .model import (
    Channel,
    ChannelMessageCreate,
    ChannelMessageDraft,
    Group,
    GroupBotState,
    GroupMember,
    GroupMessageDraft,
    GroupMessageReceipt,
    GroupMuteState,
    GroupUser,
    Guild,
    GuildUser,
    InteractionCreate,
    Member,
    Message,
    Role,
    User,
)
from .options import ClientOptions
from .storage import FileSessionStorage, MemorySessionStorage, SessionData, SessionStorage

try:
    __version__ = version("qbotsdk")
except PackageNotFoundError:  # pragma: no cover
    __version__ = "0.0.0"

__all__ = [
    "APIError",
    "Adapter",
    "AdapterContext",
    "ApiClient",
    "Bot",
    "Channel",
    "ChannelMessageCreate",
    "ChannelMessageDraft",
    "ClientOptions",
    "ErrorCode",
    "FileSessionStorage",
    "Group",
    "GroupBotState",
    "GroupMember",
    "GroupMessageDraft",
    "GroupMessageReceipt",
    "GroupMuteState",
    "GroupUser",
    "Guild",
    "GuildUser",
    "InteractionCreate",
    "Member",
    "MemorySessionStorage",
    "Message",
    "QQBotError",
    "RateLimitExceededError",
    "Role",
    "SessionData",
    "SessionStorage",
    "TransportError",
    "User",
    "WebSocketAdapter",
    "WebhookAdapter",
    "WebhookServer",
    "__version__",
    "build_webhook_handler",
]
