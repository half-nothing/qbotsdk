# Copyright (c) 2026-present Half_nothing.

"""命令树, 按事件类型各一棵, 字面量、可变参数与 rest 三类边。"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from .route import Route
from .template import PathTemplate, Placeholder


@dataclass(slots=True)
class Node:
    """树上的一个节点。"""

    literals: dict[str, Node] = field(default_factory=dict)  # 字面量子节点
    wildcard: Node | None = None  # 可变参数子节点
    wildcard_name: str = "arg"  # 可变参数名称
    rest: Node | None = None  # rest 参数子节点
    rest_name: str = "rest"  # rest 参数名称
    route: Route | None = None  # 该节点注册的路由
    template: PathTemplate | None = None  # 该节点对应的路径模板

    @property
    def children(self) -> tuple[str, ...]:
        """用于推导 usage 的子节点名, 字面量按字母序, 随后是可变参与 rest。"""

        names = sorted(self.literals)
        if self.wildcard is not None:
            names.append(f"*{self.wildcard_name}")
        if self.rest is not None:
            names.append(f"<{self.rest_name}:rest>")
        return tuple(names)

    @property
    def child_count(self) -> int:
        """直接子边数量, 用于判断 usage 是否只有一个候选。"""

        return len(self.literals) + (self.wildcard is not None) + (self.rest is not None)


@dataclass(frozen=True, slots=True)
class TextMatch:
    """一次成功的文本匹配。"""

    route: Route  # 命中的路由
    template: PathTemplate  # 命中的路径模板
    values: tuple[str, ...]  # 可变参数捕获值
    rest: tuple[str, ...] = ()  # rest 参数捕获值
    options: Mapping[str, object] = field(default_factory=dict)  # 解析出的选项


@dataclass(frozen=True, slots=True)
class Partial:
    """token 用完但没有 route 的节点, 需要回 usage。"""

    path: tuple[str, ...]  # 已消费的路径片段
    node: Node  # 停下的节点


def insert(root: Node, template: PathTemplate, route: Route) -> None:
    """
    把一条模板插进树。

    :param root: 要插入的命令解析树的根节点
    :param template: 命令编译后的路径模板
    :param route: 叶子节点挂载的路由结构
    :raise ValueError: 当同一路径已被注册时抛出
    """

    node = root
    for part in template.parts:
        if isinstance(part, str):
            node = node.literals.setdefault(part, Node())
            continue
        if _is_rest(part):
            if node.rest is None:
                node.rest = Node()
                node.rest.rest_name = part.name
            node = node.rest
            break
        if node.wildcard is None:
            node.wildcard = Node()
            node.wildcard_name = part.name
        node = node.wildcard

    if node.route is not None:
        raise ValueError(f"{template.source!r} is already registered")
    node.route = route
    node.template = template


def resolve(root: Node, tokens: Sequence[str]) -> TextMatch | Partial | None:
    """从根开始匹配 token 列表。

    :param root: 待查找的解析树的根节点
    :param tokens: 待匹配的token列表
    :return: 返回 :class:`TextMatch` 表示完整命中；
        返回 :class:`Partial` 表示 token 已耗尽但节点还可继续；
        返回 ``None`` 表示没有匹配。
    """

    return _walk(root, tokens, 0, (), {}, False, ())


def _walk(
    node: Node,
    tokens: Sequence[str],
    index: int,
    values: tuple[str, ...],
    options: Mapping[str, object],
    literal_mode: bool,
    path: tuple[str, ...],
) -> TextMatch | Partial | None:
    """
    从某个节点开始往下查找匹配的路径, 使用递归查询配合回溯剪枝。

    :param node: 开始节点
    :param tokens: 待匹配的 token 列表
    :param index: 当前正在匹配的 token 下标
    :param values: 已捕获的可变参数值, 按出现顺序保存
    :param options: 已扫描到的选项, 键为选项名, 值为字符串或 True
    :param literal_mode: 是否已遇到 ``--``, 进入纯字面量模式
    :param path: 已走过的路径片段, 用于推导 usage
    :return: 命中返回 TextMatch, 未完成返回 Partial, 失败返回 None
    """
    if (
        node.rest is not None
        and node.rest.route is not None
        and node.rest.template is not None
        and index < len(tokens)
    ):
        return TextMatch(
            node.rest.route, node.rest.template, values, tuple(tokens[index:]), options
        )
    index, options, literal_mode = _scan_options(tokens, index, options, literal_mode)
    if index >= len(tokens):
        if node.route is not None and node.template is not None:
            return TextMatch(node.route, node.template, values, (), options)
        if node.rest is not None and node.rest.route is not None and node.rest.template is not None:
            return TextMatch(node.rest.route, node.rest.template, values, (), options)
        return Partial(path=path, node=node)

    token = tokens[index]
    child = node.literals.get(token)
    if child is not None:
        found = _walk(child, tokens, index + 1, values, options, literal_mode, (*path, token))
        if found is not None:
            return found

    if node.wildcard is not None:
        found = _walk(
            node.wildcard,
            tokens,
            index + 1,
            (*values, token),
            options,
            literal_mode,
            (*path, f"<{node.wildcard_name}>"),
        )
        if found is not None:
            return found

    if node.rest is not None and node.rest.route is not None and node.rest.template is not None:
        return TextMatch(
            node.rest.route, node.rest.template, values, tuple(tokens[index:]), options
        )
    return None


def _scan_options(
    tokens: Sequence[str],
    index: int,
    options: Mapping[str, object],
    literal_mode: bool,
) -> tuple[int, Mapping[str, object], bool]:
    """跳过并收集 --name / --name=value, -- 之后不再解析。

    :param tokens: 待匹配的 token 列表
    :param index: 当前 token 下标
    :param options: 已收集的选项
    :param literal_mode: 是否已进入纯字面量模式
    :return: 新的下标、合并后的选项、新的 literal_mode
    """

    merged = dict(options)
    while index < len(tokens) and not literal_mode:
        token = tokens[index]
        if token == "--":
            literal_mode = True
            index += 1
            continue
        if not token.startswith("--") or len(token) == 2:
            break
        name, separator, value = token[2:].partition("=")
        if not name:
            break
        merged[name] = value if separator else True
        index += 1
    return index, merged, literal_mode


def usage_for(partial: Partial, *, prefix: str) -> str | None:
    """为停在死节点上的匹配推导 usage。"""

    node = partial.node
    if node.child_count == 0:
        return None

    base = f"{prefix}{' '.join(partial.path)}".strip()

    if node.child_count == 1:
        if node.wildcard is not None and node.wildcard.route is not None:
            return _route_usage(node.wildcard, fallback=f"{base} <{node.wildcard_name}>")
        if node.rest is not None and node.rest.route is not None:
            return _route_usage(node.rest, fallback=f"{base} <{node.rest_name}:rest>")
        if len(node.literals) == 1:
            literal = next(iter(node.literals))
            return f"{base} {literal}"

    names = "|".join(node.children)
    return f"{base} <{names}>"


def _route_usage(node: Node, *, fallback: str) -> str:
    """优先返回路由自带的 usage, 否则使用推导出的 fallback。"""

    route = node.route
    if route is not None and route.usage is not None:
        return route.usage
    return fallback


def _is_rest(part: Placeholder) -> bool:
    """判断占位符是否为 rest 类型。"""

    return part.converter == "rest"


__all__ = ["Node", "Partial", "TextMatch", "insert", "resolve", "usage_for"]
