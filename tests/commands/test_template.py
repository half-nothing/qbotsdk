# Copyright (c) 2026-present Half_nothing.

"""路径模板与转换器的单元测试。"""

from __future__ import annotations

import pytest

from qbotsdk.commands.convert import (
    DEFAULT_CONVERTERS,
    MentionConverter,
    accepts_annotation,
)
from qbotsdk.commands.template import (
    Placeholder,
    alias_friendly,
    compile_template,
    literal_prefix,
)


def test_compile_splits_literals_and_placeholders() -> None:
    template = compile_template("server <name:int=3>")

    assert template.literals == 1
    assert template.placeholders == (Placeholder("name", "int", "3"),)
    assert template.rest is None


def test_placeholder_render_round_trips() -> None:
    assert Placeholder("name").render() == "<name>"
    assert Placeholder("name", "int").render() == "<name:int>"
    assert Placeholder("name", "int", "3").render() == "<name:int=3>"


def test_match_returns_raw_tokens_without_converting() -> None:
    shape = compile_template("server <name:int>").match(["server", "7"])

    assert shape is not None
    assert shape.values == {"name": "7"}
    assert shape.segments["name"] == ("7",)


def test_match_rejects_literal_mismatch_and_length_mismatch() -> None:
    template = compile_template("server <name>")

    assert template.match(["client", "x"]) is None
    assert template.match(["server", "x", "y"]) is None
    assert template.match(["server"]) is None


def test_trailing_defaults_fill_from_the_right() -> None:
    template = compile_template("server <name:str=main> <port:int=8080>")

    filled = template.match(["server"])
    partial = template.match(["server", "backup"])

    assert filled is not None and filled.values == {"name": "main", "port": "8080"}
    assert partial is not None and partial.values == {"name": "backup", "port": "8080"}


def test_rest_placeholder_swallows_the_tail() -> None:
    template = compile_template("broadcast <text:rest>")

    shape = template.match(["broadcast", "hello", "world"])

    assert shape is not None
    assert shape.values == {"text": "hello world"}
    assert shape.segments["text"] == ("hello", "world")
    assert template.match(["broadcast"]) is None


def test_score_prefers_more_literals_then_narrower_converters() -> None:
    literals = compile_template("server stop")
    wide = compile_template("server <name>")
    narrow = compile_template("server <name:int>")

    assert literals.score() > wide.score()
    assert narrow.score() > wide.score()


def test_score_prefers_fewer_defaults() -> None:
    required = compile_template("server <name>")
    optional = compile_template("server <name=str>")

    assert required.score() > optional.score()


@pytest.mark.parametrize(
    ("source", "message"),
    [
        ("", "must not be empty"),
        ("<name", "brackets must wrap the segment"),
        ("a>b", "must not contain"),
        ("<name:unknown>", "unknown converter"),
        ("<name> <name>", "declared twice"),
        ("<name:rest> tail", "must be the last segment"),
        ("<name:rest=3>", "must not have a default value"),
        ("<name:int=abc>", "is not a valid int"),
        ("<1name>", "not a valid Python identifier"),
        ("<class>", "not a valid Python identifier"),
    ],
)
def test_compile_rejects_invalid_templates(source: str, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        compile_template(source)


def test_alias_friendly_only_accepts_literals_before_placeholders() -> None:
    assert alias_friendly(compile_template("server <name>").parts) is True
    assert alias_friendly(compile_template("server <name> stop").parts) is False


def test_literal_prefix_stops_at_the_first_placeholder() -> None:
    parts = compile_template("server group <name>").parts

    assert literal_prefix(parts) == ["server", "group"]


def test_converters_parse_expected_shapes() -> None:
    assert DEFAULT_CONVERTERS["int"].parse("12") == 12
    assert DEFAULT_CONVERTERS["float"].parse("1.5") == 1.5
    assert DEFAULT_CONVERTERS["mention"].parse("<@!abc>") == "abc"
    assert DEFAULT_CONVERTERS["mention"].parse("<@abc>") == "abc"
    assert DEFAULT_CONVERTERS["mention"].parse("abc") == "abc"
    assert DEFAULT_CONVERTERS["rest"].parse("a b") == "a b"


def test_converters_reject_bad_values() -> None:
    with pytest.raises(ValueError):
        DEFAULT_CONVERTERS["int"].parse("abc")


def test_accepts_annotation_requires_exact_match() -> None:
    assert accepts_annotation(MentionConverter(), str) is True
    assert accepts_annotation(MentionConverter(), int) is False
    assert accepts_annotation(MentionConverter(), None) is True
