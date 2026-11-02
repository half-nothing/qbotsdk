# Copyright (c) 2026-present Half_nothing.

"""事件到调用参数的适配：文本、主体键、@ 列表与统一回复入口。"""

from __future__ import annotations

from dataclasses import dataclass
from re import compile
from typing import TYPE_CHECKING

from qbotsdk.model.event import (
    C2CMessageCreate,
    ChannelMessageCreate,
    EventModel,
    GroupAtMessageCreate,
    GroupMessageCreate,
    InteractionCreate,
)
from qbotsdk.model.user import MentionUser

from .context import Kind, Sender

if TYPE_CHECKING:
    from qbotsdk.model.draft import MessageMarkdown
    from qbotsdk.model.keyboard import Keyboard
    from qbotsdk.model.media import MediaInfo

    from .context import ReplyResult

# 频道消息正文开头的 @ 机器人标记, 平台不会剥
_LEADING_MENTION = compile(r"^<@!?[^>]+>\s*")


@dataclass(frozen=True, slots=True)
class Invocation:
    """事件适配后的一次待路由调用。"""

    kind: Kind
    event: EventModel
    text: str
    principal: str
    account: str | None
    mentions: tuple[MentionUser, ...]
    button_data: str | None
    sender: Sender | None


def _group_sender(event: GroupAtMessageCreate | GroupMessageCreate) -> Sender:
    async def send(
        content: str | None = None,
        *,
        markdown: MessageMarkdown | None = None,
        media: MediaInfo | None = None,
        image: str | None = None,
        keyboard: Keyboard | None = None,
        msg_seq: int | None = None,
    ) -> ReplyResult:
        if image is not None:
            raise ValueError("group messages do not accept image=; pass media= instead")
        return await event.reply(
            content or None,
            markdown=markdown,
            media=media,
            keyboard=keyboard,
            msg_seq=msg_seq,
        )

    return send


def _c2c_sender(event: C2CMessageCreate) -> Sender:
    async def send(
        content: str | None = None,
        *,
        markdown: MessageMarkdown | None = None,
        media: MediaInfo | None = None,
        image: str | None = None,
        keyboard: Keyboard | None = None,
        msg_seq: int | None = None,
    ) -> ReplyResult:
        if image is not None:
            raise ValueError("c2c messages do not accept image=; pass media= instead")
        return await event.reply(
            content or None,
            markdown=markdown,
            media=media,
            keyboard=keyboard,
            msg_seq=msg_seq,
        )

    return send


def _channel_sender(event: ChannelMessageCreate) -> Sender:
    async def send(
        content: str | None = None,
        *,
        markdown: MessageMarkdown | None = None,
        media: MediaInfo | None = None,
        image: str | None = None,
        keyboard: Keyboard | None = None,
        msg_seq: int | None = None,
    ) -> ReplyResult:
        if keyboard is not None:
            raise ValueError("channel messages do not support keyboards")
        if media is not None:
            raise ValueError("channel messages do not support media; pass image= instead")
        if msg_seq is not None:
            raise ValueError("channel messages do not support msg_seq")
        return await event.reply(content or None, markdown=markdown, image=image)

    return send


def adapt_event(event: EventModel) -> Invocation | None:
    """把事件适配成 `Invocation`, 不认识的类型返回 None。"""

    if isinstance(event, (GroupAtMessageCreate, GroupMessageCreate)):
        openid = event.author.member_openid
        # @ 标记在这里统一渲染成裸 openid, 命令层拿到就能直接当主体用
        rendered = event.render_mentions_openid(strip_me=True)
        return Invocation(
            kind="group",
            event=event,
            text=rendered.text,
            principal=f"group:{event.group_openid}:{openid}",
            account=f"user:{openid}",
            mentions=rendered.mentions,
            button_data=None,
            sender=_group_sender(event),
        )
    if isinstance(event, C2CMessageCreate):
        openid = event.author.user_openid
        return Invocation(
            kind="c2c",
            event=event,
            text=event.content,
            principal=f"c2c:{openid}",
            account=f"user:{openid}",
            mentions=(),
            button_data=None,
            sender=_c2c_sender(event),
        )
    if isinstance(event, ChannelMessageCreate):
        return Invocation(
            kind="channel",
            event=event,
            text=_LEADING_MENTION.sub("", event.content or ""),
            principal=f"guild:{event.guild_id}:{event.author.id}",
            account=None,
            mentions=(),
            button_data=None,
            sender=_channel_sender(event),
        )
    if isinstance(event, InteractionCreate):
        resolved = event.data.resolved if event.data is not None else None
        button_data = resolved.button_data if resolved is not None else None
        principal = f"interaction:{event.id}"
        account: str | None = None
        if event.group_openid and event.group_member_openid:
            principal = f"group:{event.group_openid}:{event.group_member_openid}"
            account = f"user:{event.group_member_openid}"
        elif event.user_openid:
            principal = f"c2c:{event.user_openid}"
            account = f"user:{event.user_openid}"
        return Invocation(
            kind="interaction",
            event=event,
            text="",
            principal=principal,
            account=account,
            mentions=(),
            button_data=button_data,
            sender=None,
        )
    return None
