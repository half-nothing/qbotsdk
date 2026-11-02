# Copyright (c) 2026-present Half_nothing.

"""单次命令执行的上下文, 按事件类型细分出可直接使用的回复签名。"""

from __future__ import annotations

from collections.abc import Awaitable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal, Protocol, cast

if TYPE_CHECKING:
    from qbotsdk.bot import Bot
    from qbotsdk.model.draft import MessageMarkdown
    from qbotsdk.model.event import ApiProtocol, EventModel
    from qbotsdk.model.keyboard import Keyboard
    from qbotsdk.model.media import MediaInfo
    from qbotsdk.model.message import GroupMessageReceipt, Message, UserMessageReceipt
    from qbotsdk.model.user import MentionUser

    # 各类事件回复后拿到的回执
    ReplyResult = GroupMessageReceipt | UserMessageReceipt | Message

Kind = Literal["group", "c2c", "channel", "interaction"]


class Sender(Protocol):
    """路由器注入的投递函数, 是整个命令层与外部世界之间唯一的出口。

    实现方按事件类型自行决定内容怎么送达, 消息事件发一条消息并返回回执,
    互动事件无法投递文本, 只回应客户端并返回 None。
    """

    def __call__(
        self,
        content: str | None = None,
        *,
        markdown: MessageMarkdown | None = None,
        media: MediaInfo | None = None,
        image: str | None = None,
        keyboard: Keyboard | None = None,
        msg_seq: int | None = None,
    ) -> Awaitable[ReplyResult | None]: ...


@dataclass(slots=True)
class Context:
    """一次调用的上下文, handler 的第一个形参就是它。

    principal 是场景主体键, account 是账号主体键, 两者都由适配器从事件里解析。"""

    event: EventModel
    kind: Kind
    principal: str
    account: str | None = None
    bot: Bot | None = None
    api: ApiProtocol | None = None
    mentions: tuple[MentionUser, ...] = ()
    command: str | None = None
    args: dict[str, object] = field(default_factory=dict)
    raw_args: tuple[str, ...] = ()
    text: str = ""
    state: dict[str, object] = field(default_factory=dict)
    _sender: Sender | None = field(default=None, repr=False)

    async def reply(self, content: str | None = None) -> ReplyResult | None:
        """把内容交给当前事件的投递通道。"""

        return await self._deliver(content)

    async def _deliver(
        self,
        content: str | None = None,
        *,
        markdown: MessageMarkdown | None = None,
        media: MediaInfo | None = None,
        image: str | None = None,
        keyboard: Keyboard | None = None,
        msg_seq: int | None = None,
    ) -> ReplyResult | None:
        if self._sender is None:
            raise RuntimeError("context is not bound to an event sender")
        return await self._sender(
            content,
            markdown=markdown,
            media=media,
            image=image,
            keyboard=keyboard,
            msg_seq=msg_seq,
        )

    def mention(self, openid: str) -> MentionUser | None:
        """按 openid 找被 @ 的成员, 没有则返回 None。"""

        for user in self.mentions:
            if user.member_openid == openid:
                return user
        return None


class GroupContext(Context):
    """群消息里的上下文。"""

    async def reply(
        self,
        content: str | None = None,
        *,
        markdown: MessageMarkdown | None = None,
        media: MediaInfo | None = None,
        keyboard: Keyboard | None = None,
        msg_seq: int | None = None,
    ) -> GroupMessageReceipt:
        return cast(
            "GroupMessageReceipt",
            await self._deliver(
                content,
                markdown=markdown,
                media=media,
                keyboard=keyboard,
                msg_seq=msg_seq,
            ),
        )


class C2CContext(Context):
    """单聊里的上下文。"""

    async def reply(
        self,
        content: str | None = None,
        *,
        markdown: MessageMarkdown | None = None,
        media: MediaInfo | None = None,
        keyboard: Keyboard | None = None,
        msg_seq: int | None = None,
    ) -> UserMessageReceipt:
        return cast(
            "UserMessageReceipt",
            await self._deliver(
                content,
                markdown=markdown,
                media=media,
                keyboard=keyboard,
                msg_seq=msg_seq,
            ),
        )


class ChannelContext(Context):
    """频道消息里的上下文。"""

    async def reply(
        self,
        content: str | None = None,
        *,
        markdown: MessageMarkdown | None = None,
        image: str | None = None,
    ) -> Message:
        return cast("Message", await self._deliver(content, markdown=markdown, image=image))


class InteractionContext(Context):
    """按钮、快捷菜单等互动事件的上下文。"""

    async def reply(self, content: str | None = None) -> None:
        await self._deliver(content)
