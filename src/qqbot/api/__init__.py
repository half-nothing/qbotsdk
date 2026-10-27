# Copyright (c) 2026-present Half_nothing.

"""资源层，每个资源只负责拼路径、调 HTTPClient、把返回值转模型。"""

from __future__ import annotations

from ..module.http_client import HTTPClient
from ..module.rate_limit import RateLimiter
from .channel import ChannelResource
from .group import GroupResource
from .guild import GuildResource
from .message import MessageResource
from .user import UserResource
from .user_message import UserMessageResource

__all__ = [
    "ApiClient",
    "ChannelResource",
    "GroupResource",
    "GuildResource",
    "MessageResource",
    "UserMessageResource",
    "UserResource",
]


class ApiClient:
    """六个资源域的聚合入口，由 `Bot` 持有并暴露为 `bot.api`。"""

    def __init__(self, http: HTTPClient) -> None:
        options = http.options
        # 关掉限流就整层不建桶, 资源层拿到的 limiter 为 None
        limiter = RateLimiter(options.rate_limits) if options.respect_rate_limits else None
        self.user = UserResource(http)
        self.guild = GuildResource(http)
        self.group = GroupResource(http, limiter=limiter)
        self.channel = ChannelResource(http)
        self.message = MessageResource(http)
        self.user_message = UserMessageResource(http, limiter=limiter)
