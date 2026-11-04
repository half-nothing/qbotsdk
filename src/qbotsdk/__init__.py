# Copyright (c) 2026-present Half_nothing.

from __future__ import annotations

from .bot import Bot
from .exceptions import APIError, ErrorCode, QQBotError, RateLimitExceededError, TransportError
from .options import ClientOptions

__author__ = "Half_nothing"
__email__ = "Half_nothing@163.com"
__version__ = "0.7.1"

__all__ = [
    "APIError",
    "Bot",
    "ClientOptions",
    "ErrorCode",
    "QQBotError",
    "RateLimitExceededError",
    "TransportError",
    "__version__",
]
