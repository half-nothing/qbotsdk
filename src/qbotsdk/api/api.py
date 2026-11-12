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

"""资源层, 每个资源只负责拼路径、调 HttpClient、把返回值转模型。"""

from __future__ import annotations

from collections.abc import Mapping
from typing import cast

from qbotsdk.module import HttpClient, RateLimiter

from .channel import ChannelResource
from .group import GroupResource
from .guild import GuildResource
from .interaction import InteractionResource
from .message import MessageResource
from .reaction import ReactionResource
from .user import UserResource
from .user_message import UserMessageResource

__all__ = ["ApiClient"]


class ApiClient:
    """八个资源域的聚合入口, 由 `Bot` 持有并暴露为 `bot.api`。"""

    def __init__(self, http: HttpClient) -> None:
        options = http.options
        # 开着本地限流才建, 三种限制都由同一个 RateLimiter 承担
        limiter: RateLimiter | None = None
        if options.respect_rate_limits:
            # RateLimiter 收任意 str scope, 而 options 把键收窄成 group/c2c;
            # Mapping 的键是不变的, 这里只放宽类型不改数据。
            limiter = RateLimiter(
                cast("Mapping[str, float]", options.rate_limits),
                daily_limits=cast("Mapping[str, int]", options.daily_limits),
                global_rate=options.global_rate_limit,
            )
        # 暴露出来便于调用方查询剩余额度
        self.limiter = limiter
        hook = options.send_hook
        self.user = UserResource(http)
        self.guild = GuildResource(http)
        self.group = GroupResource(http, limiter=limiter, hook=hook)
        self.channel = ChannelResource(http, hook=hook)
        self.message = MessageResource(http, hook=hook)
        self.user_message = UserMessageResource(http, limiter=limiter, hook=hook)
        self.interaction = InteractionResource(http)
        self.reaction = ReactionResource(http)
