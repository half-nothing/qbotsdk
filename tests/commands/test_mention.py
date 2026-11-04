# Copyright (c) 2026-present Half_nothing.

"""回复前的 @ 发送者：默认开启、三种关闭方式，以及 @ 只在 markdown 里生效。"""

from __future__ import annotations

from qbotsdk.commands import Context, Reply, Router, Status
from qbotsdk.model.event import C2CMessageCreate, ChannelMessageCreate, GroupMessageCreate
from tests.commands.support import FakeApi, c2c_event, channel_event, group_event

ON = GroupMessageCreate
TAG = '<qqbot-at-user id="member-1" />'


async def test_group_reply_mentions_the_sender_by_default() -> None:
    router = Router()

    @router.command("ping", on=ON)
    async def ping(ctx: Context) -> Reply:
        return Reply(text="pong")

    event = group_event("/ping")
    await router.handle(event)

    assert isinstance(event.api, FakeApi)
    call = event.api.group.calls[0]
    assert call["content"] is None
    assert call["markdown"].content == f"{TAG}\npong"


async def test_markdown_reply_uses_the_markup_tag() -> None:
    router = Router()

    @router.command("me", on=ON)
    async def me(ctx: Context) -> Reply:
        return Reply(text="**hi**", markdown=True)

    event = group_event("/me")
    await router.handle(event)

    assert isinstance(event.api, FakeApi)
    call = event.api.group.calls[0]
    assert call["content"] is None
    assert call["markdown"].content == f"{TAG}\n**hi**"


async def test_router_can_turn_the_mention_off() -> None:
    router = Router(reply_mention=False)

    @router.command("ping", on=ON)
    async def ping(ctx: Context) -> Reply:
        return Reply(text="pong")

    event = group_event("/ping")
    await router.handle(event)

    assert isinstance(event.api, FakeApi)
    call = event.api.group.calls[0]
    assert call["content"] == "pong"
    assert call["markdown"] is None


async def test_a_command_can_override_the_router_default() -> None:
    router = Router()

    @router.command("quiet", on=ON, mention=False)
    async def quiet(ctx: Context) -> Reply:
        return Reply(text="pong")

    event = group_event("/quiet")
    await router.handle(event)

    assert isinstance(event.api, FakeApi)
    assert event.api.group.calls[0]["content"] == "pong"


async def test_a_reply_can_override_the_command_setting() -> None:
    router = Router()

    @router.command("ping", on=ON)
    async def ping(ctx: Context) -> Reply:
        return Reply(text="pong", mention=False)

    event = group_event("/ping")
    await router.handle(event)

    assert isinstance(event.api, FakeApi)
    assert event.api.group.calls[0]["content"] == "pong"


async def test_direct_messages_are_not_mentioned() -> None:
    router = Router()

    @router.command("ping", on=(ON, C2CMessageCreate))
    async def ping(ctx: Context) -> Reply:
        return Reply(text="pong")

    event = c2c_event("/ping")
    result = await router.handle(event)

    assert result.status is Status.HANDLED
    assert isinstance(event.api, FakeApi)
    assert event.api.user_message.calls[0]["content"] == "pong"


async def test_channel_markdown_mentions_the_author() -> None:
    router = Router()

    @router.command("say", on=ChannelMessageCreate)
    async def say(ctx: Context) -> Reply:
        return Reply(text="hi", markdown=True)

    event = channel_event("/say")
    await router.handle(event)

    assert isinstance(event.api, FakeApi)
    call = event.api.channel.calls[0]
    assert call["markdown"].content == '<qqbot-at-user id="user-9" />\nhi'


async def test_channel_text_reply_is_promoted_to_markdown() -> None:
    router = Router()

    @router.command("say", on=ChannelMessageCreate)
    async def say(ctx: Context) -> Reply:
        return Reply(text="hi")

    event = channel_event("/say")
    await router.handle(event)

    assert isinstance(event.api, FakeApi)
    call = event.api.channel.calls[0]
    assert call["markdown"].content == '<qqbot-at-user id="user-9" />\nhi'


async def test_the_legacy_mention_form_is_not_used() -> None:
    router = Router()

    @router.command("ping", on=ON)
    async def ping(ctx: Context) -> Reply:
        return Reply(text="pong")

    event = group_event("/ping")
    await router.handle(event)

    assert isinstance(event.api, FakeApi)
    call = event.api.group.calls[0]
    sent = str(call["content"] or "") + str(
        call["markdown"].content if call["markdown"] is not None else "",
    )
    assert "<@member-1>" not in sent
