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

from .api import ApiClient as ApiClient
from .channel import ChannelResource as ChannelResource
from .group import GroupResource as GroupResource
from .guild import GuildResource as GuildResource
from .interaction import InteractionResource as InteractionResource
from .message import MessageResource as MessageResource
from .reaction import ReactionResource as ReactionResource
from .user import UserResource as UserResource
from .user_message import UserMessageResource as UserMessageResource

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
