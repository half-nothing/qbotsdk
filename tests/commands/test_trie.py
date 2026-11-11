# Copyright (c) 2026-present Half_nothing.

"""命令树的单元测试: 插入、回溯匹配、死节点 usage 与选项扫描。"""

from __future__ import annotations

import pytest

from qbotsdk.commands.reply import Reply
from qbotsdk.commands.route import Binding, Route, TextTrigger
from qbotsdk.commands.template import compile_template
from qbotsdk.commands.trie import Node, Partial, TextMatch, insert, resolve, usage_for


def make_route(source: str, *, usage: str | None = None) -> Route:
    async def handler() -> Reply:
        return Reply.ok()

    template = compile_template(source)
    return Route(
        on=frozenset(),
        trigger=TextTrigger(template, bind_args=True),
        handler=handler,
        binding=Binding(ctx_param=None, kwargs=()),
        usage=usage,
    )


def build(*sources: str) -> Node:
    root = Node()
    for source in sources:
        insert(root, compile_template(source), make_route(source))
    return root


def test_literal_path_matches_leaf_route() -> None:
    root = build("server start")

    match = resolve(root, ["server", "start"])

    assert isinstance(match, TextMatch)
    assert match.values == ()
    assert match.rest == ()


def test_unknown_literal_returns_none() -> None:
    assert resolve(build("server start"), ["server", "reboot"]) is None


def test_wildcard_takes_one_token() -> None:
    match = resolve(build("kick <member>"), ["kick", "member-2"])

    assert isinstance(match, TextMatch)
    assert match.values == ("member-2",)


def test_literal_child_wins_over_wildcard() -> None:
    root = build("role add <name>", "role <name> show")

    assert resolve(root, ["role", "add", "x"]) is not None
    match = resolve(root, ["role", "bob", "show"])

    assert isinstance(match, TextMatch)
    assert match.values == ("bob",)


def test_failed_literal_branch_backtracks_to_the_wildcard() -> None:
    root = build("role add <name>", "role <name> add <key>")

    match = resolve(root, ["role", "bob", "add", "demo.stop"])

    assert isinstance(match, TextMatch)
    assert match.values == ("bob", "demo.stop")


def test_rest_collects_every_remaining_token() -> None:
    match = resolve(build("echo <text:rest>"), ["echo", "--not-a-flag", "hello"])

    assert isinstance(match, TextMatch)
    assert match.rest == ("--not-a-flag", "hello")


def test_rest_matches_an_empty_tail() -> None:
    match = resolve(build("echo <text:rest>"), ["echo"])

    assert isinstance(match, TextMatch)
    assert match.rest == ()


def test_options_are_collected_before_the_literals() -> None:
    root = build("roll <sides:int>")

    match = resolve(root, ["roll", "6", "--loud"])

    assert isinstance(match, TextMatch)
    assert match.options == {"loud": True}
    assert match.values == ("6",)


def test_option_values_are_split_on_the_first_equals_sign() -> None:
    match = resolve(build("roll <sides:int>"), ["roll", "--note=a=b", "6"])

    assert isinstance(match, TextMatch)
    assert match.options == {"note": "a=b"}


def test_double_dash_stops_option_scanning() -> None:
    match = resolve(build("kick <member>"), ["kick", "--", "--member"])

    assert isinstance(match, TextMatch)
    assert match.options == {}
    assert match.values == ("--member",)


def test_dead_node_without_children_returns_partial() -> None:
    partial = resolve(build("server start"), ["server"])

    assert isinstance(partial, Partial)
    assert usage_for(partial, prefix="/") == "/server start"


def test_dead_node_lists_every_literal_child() -> None:
    root = build(
        "permission show",
        "permission grant <key> <text:rest>",
        "permission role add <name>",
    )

    partial = resolve(root, ["permission"])

    assert isinstance(partial, Partial)
    assert usage_for(partial, prefix="/") == "/permission <grant|role|show>"


def test_dead_node_marks_wildcards_with_an_asterisk() -> None:
    root = build("permission role add <name>", "permission role <name> show")

    partial = resolve(root, ["permission", "role"])

    assert isinstance(partial, Partial)
    assert usage_for(partial, prefix="/") == "/permission role <add|*name>"


def test_single_routed_child_contributes_its_usage() -> None:
    root = Node()
    route = make_route("roll <sides:int>", usage="/roll <sides:int>")
    insert(root, compile_template("roll <sides:int>"), route)

    partial = resolve(root, ["roll"])

    assert isinstance(partial, Partial)
    assert usage_for(partial, prefix="/") == "/roll <sides:int>"


def test_duplicate_path_is_rejected() -> None:
    root = Node()
    insert(root, compile_template("server start"), make_route("server start"))

    with pytest.raises(ValueError, match="already registered"):
        insert(root, compile_template("server start"), make_route("server start"))


def test_two_placeholders_on_the_same_node_share_one_child() -> None:
    root = build("role <name> show", "role <other> watch")

    assert root.literals["role"].wildcard is not None
    assert root.literals["role"].wildcard.child_count == 2
