# Copyright (c) 2026-present Half_nothing.

"""文本交互标记模型测试。"""

from __future__ import annotations

import pytest

from qbotsdk.model.markup import (
    AtEveryone,
    AtUser,
    ChannelLink,
    CommandEnter,
    CommandInput,
    EmojiMarkup,
    PlainText,
    TextChain,
)


def test_nodes_render_the_documented_markers() -> None:
    assert AtUser("member-1").render() == '<qqbot-at-user id="member-1" />'
    assert AtEveryone().render() == "<qqbot-at-everyone />"
    assert CommandEnter("/签到").render() == '<qqbot-cmd-enter text="%2F%E7%AD%BE%E5%88%B0" />'
    assert CommandInput("hi").render() == '<qqbot-cmd-input text="hi" />'
    assert ChannelLink("123").render() == "<#123>"
    assert EmojiMarkup("4").render() == "<emoji:4>"
    assert PlainText("hi").render() == "hi"


def test_command_input_renders_optional_attributes() -> None:
    node = CommandInput("hi there", show="点我", reference=True)

    assert node.render() == (
        '<qqbot-cmd-input text="hi%20there" show="%E7%82%B9%E6%88%91" reference="true" />'
    )


def test_chain_renders_in_order() -> None:
    chain = TextChain.of(AtUser("member-1"), " 你好 ", CommandEnter("/roll"))

    assert chain.render() == (
        '<qqbot-at-user id="member-1" /> 你好 <qqbot-cmd-enter text="%2Froll" />'
    )
    assert str(chain) == chain.render()
    assert len(chain) == 3


def test_chain_parse_splits_plain_text_and_markers() -> None:
    raw = 'hi <qqbot-at-user id="member-1" /> and <qqbot-cmd-enter text="%2Fping" /> tail'

    chain = TextChain.parse(raw)

    assert chain.nodes == (
        PlainText("hi "),
        AtUser("member-1"),
        PlainText(" and "),
        CommandEnter("/ping"),
        PlainText(" tail"),
    )
    assert chain.render() == raw


def test_chain_parse_reads_command_input_attributes() -> None:
    raw = '<qqbot-cmd-input text="hi%20there" show="%E7%82%B9%E6%88%91" reference="true" />'

    chain = TextChain.parse(raw)

    assert chain.nodes == (CommandInput("hi there", show="点我", reference=True),)


def test_chain_parse_keeps_unknown_markers_as_text() -> None:
    chain = TextChain.parse("<qqbot-cmd-input data-x />")

    assert chain.nodes == (PlainText("<qqbot-cmd-input data-x />"),)


def test_chain_parse_ignores_the_retired_protocol() -> None:
    chain = TextChain.parse("<@member-1> 你好")

    assert chain.nodes == (PlainText("<@member-1> 你好"),)


def test_empty_chain_renders_to_an_empty_string() -> None:
    assert TextChain().render() == ""
    assert len(TextChain()) == 0


def test_command_text_must_fit_the_documented_limit() -> None:
    with pytest.raises(ValueError, match="text must not be empty"):
        CommandEnter("")
    with pytest.raises(ValueError, match="text must be at most 100 characters"):
        CommandInput("x" * 101)
    with pytest.raises(ValueError, match="show must not be empty"):
        CommandInput("hi", show="")


def test_identifiers_must_not_be_empty() -> None:
    with pytest.raises(ValueError, match="openid must not be empty"):
        AtUser("")
    with pytest.raises(ValueError, match="channel_id must not be empty"):
        ChannelLink("")
    with pytest.raises(ValueError, match="emoji_id must not be empty"):
        EmojiMarkup("")
