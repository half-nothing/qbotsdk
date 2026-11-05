# Copyright (c) 2026-present Half_nothing.

"""资源层, 每个资源只负责拼路径、调 HTTPClient、把返回值转模型。"""

from __future__ import annotations

from qbotsdk.module.http_client import HTTPClient
from qbotsdk.module.rate_limit import RateLimiter
from qbotsdk.module.send_guard import LocalRateLimitGuard, SendGuard

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
        # 调用方注入的切面优先; 没注入且开着限流才用本地令牌桶
        guard: SendGuard | None = options.send_guard
        if guard is None and options.respect_rate_limits:
            guard = LocalRateLimitGuard(RateLimiter(options.rate_limits))
        # 暴露出来便于调用方查询剩余额度或替换实现
        self.send_guard = guard
        self.user = UserResource(http)
        self.guild = GuildResource(http)
        self.group = GroupResource(http, guard=guard)
        self.channel = ChannelResource(http)
        self.message = MessageResource(http)
        self.user_message = UserMessageResource(http, guard=guard)
        self.interaction = InteractionResource(http)
        self.reaction = ReactionResource(http)
