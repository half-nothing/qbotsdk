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
    compile_template,
)


def test_compile_splits_literals_and_placeholders() -> None:
    template = compile_template("server <name:int>")

    assert template.parts == ("server", Placeholder("name", "int"))
    assert template.placeholders == (Placeholder("name", "int"),)
    assert template.rest is None


def test_rest_segment_compiles_into_a_placeholder() -> None:
    template = compile_template("broadcast <text:rest>")

    assert template.rest == Placeholder("text", "rest")
    assert template.params == ()
    assert template.parts[-1] == Placeholder("text", "rest")


def test_rest_is_only_a_converter_not_a_segment_syntax() -> None:
    template = compile_template("echo +rest")

    assert template.parts == ("echo", "+rest")


def test_params_skip_the_rest_placeholder() -> None:
    template = compile_template("kick <member:mention> <reason> <text:rest>")

    assert [param.name for param in template.params] == ["member", "reason"]


@pytest.mark.parametrize(
    ("source", "message"),
    [
        ("", "must not be empty"),
        ("<name", "brackets must wrap the segment"),
        ("a>b", "must not contain"),
        ("<name:unknown>", "unknown converter"),
        ("<name> <name>", "declared twice"),
        ("<name:rest> tail", "must be the last segment"),
        ("<name:int=3>", "must not declare a default value"),
        ("<1name>", "not a valid Python identifier"),
        ("<class>", "not a valid Python identifier"),
    ],
)
def test_compile_rejects_invalid_templates(source: str, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        compile_template(source)


def test_compile_allows_literals_after_placeholders() -> None:
    template = compile_template("server <name> stop")

    assert template.params == (Placeholder("name"),)


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
    assert accepts_annotation(MentionConverter, str) is True
    assert accepts_annotation(MentionConverter, int) is False
    assert accepts_annotation(MentionConverter, None) is True
