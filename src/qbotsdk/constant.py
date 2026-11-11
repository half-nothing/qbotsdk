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

from typing import Final

__all__ = [
    "AUTHORIZATION_SCHEME",
    "BASE_URL",
    "TOKEN_URL",
    "TRACE_ID_HEADER",
]

# OpenAPI 根地址
BASE_URL: Final[str] = "https://api.bot.qq.com"
# 用 AppID/AppSecret 换取 access_token 的凭证接口
TOKEN_URL: Final[str] = f"{BASE_URL}/app/getAppAccessToken"
# 鉴权头固定前缀, 格式为 "QQBot <token>"
AUTHORIZATION_SCHEME: Final[str] = "QQBot"
# 响应头里的全链路追踪 ID
TRACE_ID_HEADER: Final[str] = "X-Tps-trace-ID"
