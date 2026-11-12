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

"""路径模板, 把一段命令文本编译成可以逐段入树的结构。"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from keyword import iskeyword

from .convert import DEFAULT_CONVERTERS, Converter

__all__ = ["PathTemplate", "Placeholder", "compile_template"]


@dataclass(frozen=True, slots=True)
class Placeholder:
    """模板里的一个占位符。"""

    name: str
    converter: str = "str"


@dataclass(frozen=True, slots=True)
class PathTemplate:
    """编译后的路径模板。"""

    source: str
    parts: tuple[str | Placeholder, ...]
    placeholders: tuple[Placeholder, ...]

    @property
    def rest(self) -> Placeholder | None:
        """末尾的 rest 占位符, 没有则返回 None。"""

        last = self.parts[-1] if self.parts else None
        if isinstance(last, Placeholder) and last.converter == "rest":
            return last
        return None

    @property
    def params(self) -> tuple[Placeholder, ...]:
        """除 rest 外的可变参数, 按出现顺序。"""

        return tuple(part for part in self.placeholders if part.converter != "rest")


def _parse_segment(segment: str, converters: Mapping[str, Converter]) -> str | Placeholder:
    """
    把一个 token 解析成字面段或占位符。

    支持的格式为
        - 纯字面值如: group, add, remove
        - 占位符如: <name>, <id:str>, <user_id:int>
        - 转换器写 rest 的占位符放在末尾, 会吃掉命令后面的全部 token, 如: <text:rest>

    注意如果使用占位符, ':'前面需要是一个合法的python变量名

    :param segment: 一个token元素, 可以是
    :param converters: 转换器字典, 用于校验声明的参数类型是否合法
    :return: 如果是纯字面量, 则返回字符串;如果是以<>包裹的占位符, 则返回 :class:`Placeholder`
    :raise ValueError: 如果token格式错误
    """

    if segment.startswith("<") != segment.endswith(">"):
        raise ValueError(f"malformed placeholder {segment!r}: brackets must wrap the segment")
    if not segment.startswith("<"):
        if segment.find("<") != -1 or segment.find(">") != -1:
            raise ValueError(f"literal segment {segment!r} must not contain '<' or '>'")
        return segment

    inner = segment[1:-1]
    if "=" in inner:
        raise ValueError(f"placeholder {segment!r} must not declare a default value")
    converter = "str"
    name = inner
    if ":" in inner:
        name, converter = inner.split(":", 1)
    if not name:
        raise ValueError(f"placeholder {segment!r} must have a name")
    if not name.isidentifier() or iskeyword(name):
        raise ValueError(f"placeholder name {name!r} is not a valid Python identifier")
    if converter not in converters:
        raise ValueError(f"unknown converter {converter!r} in placeholder {segment!r}")
    return Placeholder(name=name, converter=converter)


def compile_template(
    source: str, *, converters: Mapping[str, Converter] | None = None
) -> PathTemplate:
    """
    把模板文本编译成 :class:`PathTemplate`, 模版文件以空格分隔, 每部分中不允许出现空格。

    :param source: 待编译模板文本
    :param converters: 转换器字典, 用于校验声明的参数类型是否合法;
        如果未显式传递, 则默认为 `DEFAULT_CONVERTERS`
    :return: 编译后的 :class:`PathTemplate`
    :raise ValueError: 如果模板文本不符合规范
    """

    if converters is None:
        converters = DEFAULT_CONVERTERS
    tokens = source.split()
    if not tokens:
        raise ValueError("command template must not be empty")

    parts: list[str | Placeholder] = []
    placeholders: list[Placeholder] = []
    seen: set[str] = set()
    for token in tokens:
        part = _parse_segment(token, converters)
        if isinstance(part, Placeholder):
            if part.name in seen:
                raise ValueError(f"placeholder {part.name!r} is declared twice")
            seen.add(part.name)
            placeholders.append(part)
        parts.append(part)

    for index, part in enumerate(parts):
        if isinstance(part, Placeholder) and part.converter == "rest" and index != len(parts) - 1:
            raise ValueError("a rest placeholder must be the last segment")

    return PathTemplate(source=source, parts=tuple(parts), placeholders=tuple(placeholders))
