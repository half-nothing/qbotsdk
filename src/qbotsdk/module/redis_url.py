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

"""Redis 连接地址拼装, 会话存储与权限存储共用。"""

from __future__ import annotations

from urllib.parse import quote

__all__ = ["build_redis_unix_url", "build_redis_url"]


def _auth_prefix(username: str | None, password: str | None) -> str:
    """拼认证前缀, {username}:{password}@, 两项都没给时返回空串。"""

    if username is None and password is None:
        return ""
    user = quote(username, safe="") if username is not None else ""
    secret = quote(password, safe="") if password is not None else ""
    return f"{user}:{secret}@"


def build_redis_url(
    *,
    host: str,
    port: int,
    db: int,
    username: str | None,
    password: str | None,
    ssl: bool,
) -> str:
    """把主机、端口、账号密码拼成 redis 地址。"""

    if not host:
        raise ValueError("host must not be empty")
    if not 0 < port < 65536:
        raise ValueError("port must be between 1 and 65535")
    if db < 0:
        raise ValueError("db must not be negative")

    scheme = "rediss" if ssl else "redis"
    return f"{scheme}://{_auth_prefix(username, password)}{host}:{port}/{db}"


def build_redis_unix_url(
    *,
    unix_socket: str,
    db: int,
    username: str | None,
    password: str | None,
) -> str:
    """拼 unix socket 地址。"""

    if not unix_socket:
        raise ValueError("unix_socket must not be empty")
    if db < 0:
        raise ValueError("db must not be negative")

    # 路径里的斜杠是分隔符, 不能整体转义
    # db只能通过查询参数指定
    return f"unix://{_auth_prefix(username, password)}{unix_socket}?db={db}"
