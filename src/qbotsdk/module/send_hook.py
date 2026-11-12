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

"""发送结果的旁路回调。

切面只做观察, 不参与限流、重试与消息内容: 每次发送结束(成功或被拒)后回调一次,
调用方据此记账、统计或写审计日志。回调抛出的异常只记日志, 不改变发送结果。
"""

from __future__ import annotations

from contextlib import suppress
from dataclasses import dataclass
from typing import Literal, Protocol

from qbotsdk.exceptions import QQBotError
from qbotsdk.model import ChannelMessageDraft, GroupMessageDraft, UserMessageDraft

__all__ = ["MessageDraft", "SendHook", "SendRecord", "notify_send"]

# 三条通道各自的出站消息模型, 记录里带上完整内容(markdown / 富媒体 / keyboard 等)
MessageDraft = GroupMessageDraft | UserMessageDraft | ChannelMessageDraft


@dataclass(frozen=True, slots=True)
class SendRecord:
    """一次发送尝试的最终结果。

    `scope` 是发送通道, 取 `"group"` / `"c2c"` / `"channel"`;
    `target` 对应群 openid、用户 openid 或子频道 id。
    `message_id` 与 `error` 二选一: 发送成功时前者有值, 失败时后者有值。
    """

    scope: Literal["group", "c2c", "channel"]
    target: str
    path: str
    # 主动消息为 True, 带 reply_to / event_id 的被动回复为 False
    proactive: bool
    # 真正发出去的消息: 群聊/单聊是各自的 Draft, 频道是 ChannelMessageDraft;
    # 本地限流在构造草稿前拦下时为 None。可读文本用 message.to_text() 取。
    message: MessageDraft | None = None
    message_id: str | None = None
    error: QQBotError | None = None


class SendHook(Protocol):
    """发送结果的回调协议。

    实现这个方法即可统一处理所有发出的消息, 例如写记录表或累计统计。
    """

    async def on_sent(self, record: SendRecord) -> None:
        """每次发送结束后调用, 无论成功还是失败。"""
        ...


async def notify_send(hook: SendHook | None, record: SendRecord) -> None:
    """把结果交给切面; 切面自身出错不影响发送。"""

    if hook is None:
        return
    with suppress(Exception):
        await hook.on_sent(record)
