# Copyright (c) 2026-present Half_nothing.

"""发送请求体的可读文本。"""

from __future__ import annotations

from qbotsdk.model.draft import (
    ChannelMessageDraft,
    GroupMessageDraft,
    InputNotify,
    MessageMarkdown,
    UserMessageDraft,
)
from qbotsdk.model.media import MediaInfo


def test_group_text_uses_content() -> None:
    assert GroupMessageDraft(content="hello").to_text() == "hello"


def test_group_markdown_and_media_fall_back() -> None:
    markdown = MessageMarkdown(content="# title")
    assert GroupMessageDraft(markdown=markdown).to_text() == "# title"
    assert GroupMessageDraft(media=MediaInfo(file_info="abc")).to_text() == "[media]"


def test_user_input_notify_has_placeholder() -> None:
    draft = UserMessageDraft(input_notify=InputNotify(input_second=30))
    assert draft.to_text() == "[input notify]"


def test_channel_text_and_image_are_joined() -> None:
    draft = ChannelMessageDraft(content="hi", image="https://example.com/a.png")
    assert draft.to_text() == "hi\n[image] https://example.com/a.png"
