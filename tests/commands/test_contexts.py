# Copyright (c) 2026-present Half_nothing.

"""按事件类型细分的上下文与各自的发送能力。"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any, cast

import pytest

from qbotsdk.commands import (
    C2CContext,
    ChannelContext,
    Context,
    GroupContext,
    InteractionContext,
    Reply,
    Router,
)
from qbotsdk.commands.adapters import adapt_event
from qbotsdk.model.event import C2CMessageCreate, ChannelMessageCreate, GroupMessageCreate
from qbotsdk.model.keyboard import (
    Button,
    ButtonAction,
    ButtonActionType,
    ButtonPermission,
    ButtonPermissionType,
    ButtonRenderData,
    ButtonStyle,
    Keyboard,
    KeyboardContent,
    KeyboardRow,
)
from qbotsdk.model.media import MediaInfo
from tests.commands.support import FakeApi, c2c_event, channel_event, group_event, interaction_event

ON = GroupMessageCreate


def build_keyboard() -> Keyboard:
    button = Button(
        id="b",
        render_data=ButtonRenderData(label="b", visited_label="b", style=ButtonStyle.BLUE),
        action=ButtonAction(
            type=ButtonActionType.CALLBACK,
            data="demo.literal",
            permission=ButtonPermission(type=ButtonPermissionType.EVERYONE),
        ),
    )
    return Keyboard(content=KeyboardContent(rows=[KeyboardRow(buttons=[button])]))


async def test_channel_command_replies_through_channel_sender() -> None:
    router = Router(reply_mention=False)

    @router.command("ping", on=ChannelMessageCreate)
    async def ping(ctx: Context) -> Reply:
        return Reply(text="pong")

    event = channel_event("/ping")
    assert (await router.handle(event)).replied is True
    assert isinstance(event.api, FakeApi)
    assert event.api.channel.calls[0]["content"] == "pong"


async def test_channel_keyboard_is_rejected() -> None:
    invocation = adapt_event(channel_event("/keys"))
    assert invocation is not None
    assert invocation.sender is not None
    with pytest.raises(ValueError, match="channel messages do not support keyboards"):
        await invocation.sender("hi", keyboard=build_keyboard())


async def test_channel_media_is_rejected() -> None:
    invocation = adapt_event(channel_event("/media"))
    assert invocation is not None
    assert invocation.sender is not None
    with pytest.raises(ValueError, match="channel messages do not support media"):
        await invocation.sender("hi", media=MediaInfo(file_info="f"))


async def test_group_image_is_rejected() -> None:
    invocation = adapt_event(group_event("/image"))
    assert invocation is not None
    assert invocation.sender is not None
    with pytest.raises(ValueError, match="group messages do not accept image="):
        await invocation.sender("hi", image="https://example.com/a.png")


async def test_interaction_reply_acknowledges_the_client() -> None:
    router = Router(reply_mention=False)

    @router.button("demo.literal", ack="none")
    async def on_literal(ctx: InteractionContext, payload: str) -> Reply:
        await ctx.reply("done")
        return Reply.ok()

    event = interaction_event("demo.literal")
    assert (await router.handle(event)).replied is True
    assert isinstance(event.api, FakeApi)
    assert event.api.interaction.calls == [0]
    assert event.api.group.calls == []


async def test_group_context_returns_a_group_receipt() -> None:
    router = Router(reply_mention=False)
    contexts: list[Context] = []

    @router.command("hello", on=ON)
    async def hello(ctx: GroupContext) -> Reply:
        contexts.append(ctx)
        receipt = await ctx.reply("hi there")
        assert receipt is not None
        return Reply(text="done")

    event = group_event("/hello")
    await router.handle(event)

    assert isinstance(contexts[0], GroupContext)
    assert isinstance(event.api, FakeApi)
    assert [call["content"] for call in event.api.group.calls] == ["hi there"]


async def test_c2c_context_is_bound_to_direct_messages() -> None:
    router = Router(reply_mention=False)
    contexts: list[Context] = []

    @router.command("hi", on=C2CMessageCreate)
    async def hi(ctx: C2CContext) -> Reply:
        contexts.append(ctx)
        await ctx.reply("pong")
        return Reply.ok()

    event = c2c_event("/hi")
    await router.handle(event)

    assert isinstance(contexts[0], C2CContext)
    assert isinstance(event.api, FakeApi)
    assert event.api.user_message.calls[0]["content"] == "pong"


async def test_channel_context_does_not_accept_keyboard() -> None:
    router = Router(reply_mention=False)
    rejected: list[str] = []

    @router.command("fanout", on=ChannelMessageCreate)
    async def fanout(ctx: ChannelContext) -> Reply:
        reply_any = cast("Any", ctx.reply)
        with pytest.raises(TypeError):
            await reply_any("hi", keyboard=build_keyboard())
        rejected.append("ok")
        return Reply(text="done")

    event = channel_event("/fanout")
    await router.handle(event)

    assert rejected == ["ok"]
    assert isinstance(event.api, FakeApi)
    assert event.api.channel.calls[0]["content"] == "done"


async def test_interaction_context_acknowledges_without_a_body() -> None:
    router = Router(reply_mention=False)
    results: list[object] = []

    @router.button("demo.literal")
    async def on_literal(ctx: InteractionContext, payload: str) -> Reply:
        reply_any = cast("Callable[[str], Awaitable[object]]", ctx.reply)
        results.append(await reply_any("anything"))
        return Reply.ok()

    event = interaction_event("demo.literal")
    await router.handle(event)

    assert results == [None]
    assert isinstance(event.api, FakeApi)
    assert event.api.interaction.calls == [0]
