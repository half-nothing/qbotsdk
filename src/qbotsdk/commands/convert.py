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

"""占位符转换器: 把原始 token 转成 handler 要的值。"""

from __future__ import annotations

from re import Pattern, compile
from typing import Any, Final, Protocol, runtime_checkable

__all__ = [
    "DEFAULT_CONVERTERS",
    "Converter",
    "FloatConverter",
    "IntConverter",
    "MentionConverter",
    "RestConverter",
    "StrConverter",
    "accepts_annotation",
]

# 频道与群聊消息里的 @ 标记: <@openid>、<@!openid>
_MENTION_TAG: Final[Pattern[str]] = compile(r"<@!?([^>]+)>")


@runtime_checkable
class Converter(Protocol):
    """转换器协议。"""

    annotation: type[Any]

    def parse(self, raw: str) -> Any:
        """把 token 转成目标类型, 失败时抛 `TypeError` 或 `ValueError`。"""


class StrConverter:
    """默认转换器: 原样返回, 引号已在分词阶段剥掉。"""

    annotation = str

    def parse(self, raw: str) -> str:
        return raw


class IntConverter:
    annotation = int

    def parse(self, raw: str) -> int:
        return int(raw)


class FloatConverter:
    annotation = float

    def parse(self, raw: str) -> float:
        return float(raw)


class MentionConverter:
    """取成员 openid;事件层已渲染成裸 openid, `<@openid>` 与 `@openid` 也兜底剥壳。"""

    annotation = str

    def parse(self, raw: str) -> str:
        token = raw.strip()
        match = _MENTION_TAG.fullmatch(token)
        if match is not None:
            return match.group(1)
        if token.startswith("@"):
            return token[1:]
        return token


class RestConverter:
    """吞掉剩余 token 的占位符;拼接在匹配阶段完成, 这里只做透传。"""

    annotation = str

    def parse(self, raw: str) -> str:
        return raw


DEFAULT_CONVERTERS: Final[dict[str, Converter]] = {
    "str": StrConverter(),
    "int": IntConverter(),
    "float": FloatConverter(),
    "mention": MentionConverter(),
    "rest": RestConverter(),
}


def accepts_annotation(converter: Converter, annotation: object) -> bool:
    """注解是否与转换器的产出类型一致;没有注解视为一致。"""

    if annotation is None:
        return True
    return annotation is converter.annotation
