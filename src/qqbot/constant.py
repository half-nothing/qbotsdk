# Copyright (c) 2026-present Half_nothing.

# OpenAPI 根地址
BASE_URL: str = "https://api.bot.qq.com"
# 用 AppID/AppSecret 换取 access_token 的凭证接口
TOKEN_URL: str = f"{BASE_URL}/app/getAppAccessToken"
# 鉴权头固定前缀, 格式为 "QQBot <token>"
AUTHORIZATION_SCHEME: str = "QQBot"
# 响应头里的全链路追踪 ID
TRACE_ID_HEADER: str = "X-Tps-trace-ID"
