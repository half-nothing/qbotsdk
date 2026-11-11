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

"""文本交互标记模型。

参考文档: https://bot.q.qq.com/wiki/develop/api-v2/server-inter/message/trans/text-chain.html
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from typing import Final, override
from urllib.parse import quote, unquote

__all__ = [
    "AtEveryone",
    "AtUser",
    "ChannelLink",
    "CommandEnter",
    "CommandInput",
    "EmojiMarkup",
    "PlainText",
    "TextChain",
    "TextNode",
]

_MAX_TEXT: Final[int] = 100


def _check_text(value: str, *, name: str = "text") -> None:
    """指令文本的长度限制来自官方: 必填项最多 100 字符。"""

    if not value:
        raise ValueError(f"{name} must not be empty")
    if len(value) > _MAX_TEXT:
        raise ValueError(f"{name} must be at most {_MAX_TEXT} characters")


class TextNode:
    """标记节点, 子类实现 `render()`。"""

    def render(self) -> str:
        raise NotImplementedError


@dataclass(frozen=True, slots=True)
class PlainText(TextNode):
    """原样写入的普通文本。"""

    text: str

    @override
    def render(self) -> str:
        return self.text


@dataclass(frozen=True, slots=True)
class AtUser(TextNode):
    """@ 单个成员, 群聊填 `member_openid`, 频道填 `user_openid`。"""

    openid: str

    def __post_init__(self) -> None:
        if not self.openid:
            raise ValueError("openid must not be empty")

    @override
    def render(self) -> str:
        return f'<qqbot-at-user id="{self.openid}" />'


@dataclass(frozen=True, slots=True)
class AtEveryone(TextNode):
    """@ 全部成员。"""

    @override
    def render(self) -> str:
        return "<qqbot-at-everyone />"


@dataclass(frozen=True, slots=True)
class CommandEnter(TextNode):
    """回车指令: 点击后把 `text` 直接发出。"""

    text: str

    def __post_init__(self) -> None:
        _check_text(self.text)

    @override
    def render(self) -> str:
        return f'<qqbot-cmd-enter text="{quote(self.text, safe="")}" />'


@dataclass(frozen=True, slots=True)
class CommandInput(TextNode):
    """参数指令: 点击后把 `text` 插进输入框, 由用户自己编辑发送。"""

    text: str
    show: str | None = None
    reference: bool = False

    def __post_init__(self) -> None:
        _check_text(self.text)
        if self.show is not None:
            _check_text(self.show, name="show")

    @override
    def render(self) -> str:
        parts = [f'text="{quote(self.text, safe="")}"']
        if self.show is not None:
            parts.append(f'show="{quote(self.show, safe="")}"')
        if self.reference:
            parts.append('reference="true"')
        return f"<qqbot-cmd-input {' '.join(parts)} />"


@dataclass(frozen=True, slots=True)
class ChannelLink(TextNode):
    """跳转子频道, 仅频道可用。"""

    channel_id: str

    def __post_init__(self) -> None:
        if not self.channel_id:
            raise ValueError("channel_id must not be empty")

    @override
    def render(self) -> str:
        return f"<#{self.channel_id}>"


@dataclass(frozen=True, slots=True)
class EmojiMarkup(TextNode):
    """系统表情, 仅支持 `type = 1` 的表情 id。

    与 `qbotsdk.model.reaction.Emoji` 区分: 那个是请求体里的表情对象, 这个是正文里的表情标记。
    """

    emoji_id: str

    def __post_init__(self) -> None:
        if not self.emoji_id:
            raise ValueError("emoji_id must not be empty")

    @override
    def render(self) -> str:
        return f"<emoji:{self.emoji_id}>"


_AT_USER = re.compile(r'<qqbot-at-user\s+id="(?P<openid>[^"]*)"\s*/>')
_AT_EVERYONE = re.compile(r"<qqbot-at-everyone\s*/>")
_CMD_ENTER = re.compile(r'<qqbot-cmd-enter\s+text="(?P<text>[^"]*)"\s*/>')
_CMD_INPUT = re.compile(r"<qqbot-cmd-input(?P<attrs>(?:\s+[a-z]+=\"[^\"]*\")*)\s*/>")
_CHANNEL = re.compile(r"<#(?P<channel_id>\d+)>")
_EMOJI = re.compile(r"<emoji:(?P<emoji_id>\d+)>")
_ATTR = re.compile(r'([a-z]+)="([^"]*)"')


_Builder = Callable[[re.Match[str]], TextNode | None]


def _build_input(match: re.Match[str]) -> TextNode | None:
    attrs = dict(_ATTR.findall(match.group("attrs")))
    if "text" not in attrs:
        return None
    return CommandInput(
        text=unquote(attrs["text"]),
        show=unquote(attrs["show"]) if "show" in attrs else None,
        reference=attrs.get("reference") == "true",
    )


_BUILDERS: Final[tuple[tuple[re.Pattern[str], _Builder], ...]] = (
    (_CMD_INPUT, _build_input),
    (_CMD_ENTER, lambda match: CommandEnter(unquote(match["text"]))),
    (_AT_USER, lambda match: AtUser(match["openid"])),
    (_AT_EVERYONE, lambda match: AtEveryone()),
    (_CHANNEL, lambda match: ChannelLink(match["channel_id"])),
    (_EMOJI, lambda match: EmojiMarkup(match["emoji_id"])),
)


@dataclass(frozen=True, slots=True)
class TextChain:
    """一串标记节点, `render()` 得到可直接放进正文的字符串。"""

    nodes: tuple[TextNode, ...] = field(default_factory=tuple)

    @classmethod
    def of(cls, *nodes: TextNode | str) -> TextChain:
        """用节点或裸字符串拼一条链, 字符串按普通文本处理。"""

        return cls(tuple(PlainText(node) if isinstance(node, str) else node for node in nodes))

    @classmethod
    def parse(cls, text: str) -> TextChain:
        """把正文拆回节点, 认不出的片段原样留在 `PlainText` 里。"""

        nodes: list[TextNode] = []
        position = 0
        while position < len(text):
            hit = cls._search(text, position)
            if hit is None:
                break
            match, builder = hit
            if match.start() > position:
                nodes.append(PlainText(text[position : match.start()]))
            node = builder(match)
            if node is None:
                nodes.append(PlainText(match.group(0)))
            else:
                nodes.append(node)
            position = match.end()
        if position < len(text):
            nodes.append(PlainText(text[position:]))
        return cls(tuple(nodes))

    @staticmethod
    def _search(text: str, position: int) -> tuple[re.Match[str], _Builder] | None:
        best: tuple[re.Match[str], _Builder] | None = None
        for pattern, builder in _BUILDERS:
            match = pattern.search(text, position)
            if match is None:
                continue
            if best is None or match.start() < best[0].start():
                best = (match, builder)
        return best

    def render(self) -> str:
        """渲染成官方标记字符串。"""

        return "".join(node.render() for node in self.nodes)

    def __str__(self) -> str:
        return self.render()

    def __len__(self) -> int:
        return len(self.nodes)

    def __iter__(self) -> Iterator[TextNode]:
        return iter(self.nodes)
