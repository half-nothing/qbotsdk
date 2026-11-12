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

"""互动回调接口。

- 互动事件: https://bot.q.qq.com/wiki/develop/api-v2/autogen/event/interaction_create.html
- 互动事件响应: https://bot.q.qq.com/wiki/develop/api-v2/autogen/api/interactions_interaction_id.put.html
"""

from __future__ import annotations

from qbotsdk.module import HttpClient

__all__ = ["InteractionResource"]


class InteractionResource:
    """`PUT /interactions/{interaction_id}` 的薄封装。"""

    def __init__(self, http: HttpClient) -> None:
        self._http = http

    async def respond(self, interaction_id: str, *, code: int = 0) -> None:
        """回应互动事件, 让客户端停止 loading。

        官方只要求 type=11 与 type=12 回应,
        其余类型调用也不会报错, 同一个 interaction_id 只能回应一次。

        Args:
            interaction_id: INTERACTION_CREATE 事件的 d.id
            code: 0 成功 / 1 操作失败 / 2 操作频繁 / 3 重复操作 / 4 没有权限 / 5 仅管理员操作
        """

        if not 0 <= code <= 5:
            raise ValueError("interaction code must be between 0 and 5")
        path = f"/interactions/{interaction_id}"
        await self._http.put(path, json={"code": code})
