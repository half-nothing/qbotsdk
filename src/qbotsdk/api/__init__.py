# Copyright (c) 2026-present Half_nothing.

"""资源层, 每个资源只负责拼路径、调 HTTPClient、把返回值转模型。"""

from __future__ import annotations

from qbotsdk.module.http_client import HTTPClient
from qbotsdk.module.rate_limit import RateLimiter

from .channel import ChannelResource
from .group import GroupResource
from .guild import GuildResource
from .interaction import InteractionResource
from .message import MessageResource
from .reaction import ReactionResource
from .user import UserResource
from .user_message import UserMessageResource

__all__ = [
    "ApiClient",
    "ChannelResource",
    "GroupResource",
    "GuildResource",
    "InteractionResource",
    "MessageResource",
    "ReactionResource",
    "UserMessageResource",
    "UserResource",
]


class ApiClient:
    """八个资源域的聚合入口, 由 `Bot` 持有并暴露为 `bot.api`。"""

    def __init__(self, http: HTTPClient) -> None:
        options = http.options
        # 开着本地限流才建, 三种限制都由同一个 RateLimiter 承担
        limiter: RateLimiter | None = None
        if options.respect_rate_limits:
            limiter = RateLimiter(
                options.rate_limits,
                daily_limits=options.daily_limits,
                global_rate=options.global_rate_limit,
            )
        # 暴露出来便于调用方查询剩余额度
        self.limiter = limiter
        self.user = UserResource(http)
        self.guild = GuildResource(http)
        self.group = GroupResource(http, limiter=limiter)
        self.channel = ChannelResource(http)
        self.message = MessageResource(http)
        self.user_message = UserMessageResource(http, limiter=limiter)
        self.interaction = InteractionResource(http)
        self.reaction = ReactionResource(http)
