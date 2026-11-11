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

from __future__ import annotations

from .bot import Bot as Bot
from .exceptions import APIError as APIError
from .exceptions import ErrorCode as ErrorCode
from .exceptions import QQBotError as QQBotError
from .exceptions import RateLimitExceededError as RateLimitExceededError
from .exceptions import TransportError as TransportError
from .options import ClientOptions as ClientOptions

__author__ = "Half_nothing"
__email__ = "Half_nothing@163.com"
__version__ = "0.9.1"

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
