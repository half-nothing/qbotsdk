# Copyright (c) 2026-present Half_nothing.

"""命令与权限：模板命令、别名、参数绑定、权限判定、内置 /permission 与按钮回调

环境变量：
    QQ_BOT_APP_ID / QQ_BOT_APP_SECRET  机器人凭证，必填
    QQ_BOT_PERMISSION_FILE             可选，权限落盘路径；不设置就只存在内存里
    QQ_BOT_OWNER                       可选，启动时就给这个人授 permission.*，
                                       写完整主体，如 group:group-openid:member-openid
                                       或 user:openid（群里先发 /permission whoami 拿到）

群里发这些指令：
    /ping                    无权限要求，回 pong
    /echo 随便 什么 文本       bind_args=False，原样拿 argv 自己拼
    /roll 20                 带默认值的整型占位符，缺省 6
    /me                      打印自己的场景键与账号键
    /button                  回一条带回调按钮的消息
    /permission show         查看自己的权限
    /permission grant @某人 demo.admin   给被 @ 的人授权（见下方说明）
    /admin ban <@某人>        只认 demo.admin，由子路由器 include 进来

注意事件选择：`/permission grant @某人` 依赖 mentions，只能挂在 GROUP_MESSAGE_CREATE 上，
所以示例订阅的是全量群消息；机器人要先把「接收全部群消息」打开。
"""

import asyncio
import contextlib
import os
import random
import signal
import sys
import time
from collections.abc import Awaitable, Callable
from typing import Literal

from async_event_bus import EventContext
from loguru import logger
from pydantic import BaseModel

from qbotsdk import (
    Bot,
    CachedPermissionStorage,
    Context,
    Grant,
    GroupContext,
    InteractionContext,
    Permission,
    PermissionChecker,
    PermissionGroup,
    Reply,
    Router,
    UsageError,
    WebSocketAdapter,
    install_permission_commands,
)
from qbotsdk.model.event import GroupMessageCreate, InteractionCreate
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
from qbotsdk.permissions.store import RedisPermissionStorage
from qbotsdk.storage import RedisSessionStorage

logger.remove()
logger.add(sys.stderr, level="TRACE")


class Demo(PermissionGroup, namespace="demo"):
    """示例权限键：demo.ping、demo.admin，声明在类体里，导入即注册。"""

    PING = Permission("ping", "回 pong 这类基础命令")
    ADMIN = Permission("admin", "管理命令，可继承")


class ClickPayload(BaseModel):
    """按钮载荷；`action` 用 Literal 声明，路由器靠它把回调分给本模型。"""

    action: Literal["demo.click"]
    note: str = ""


def build_store() -> CachedPermissionStorage:
    """默认内存存储；给了路径就落盘，外层再套一层缓存。"""

    path = os.environ.get("QQ_BOT_PERMISSION_FILE")
    # store = FilePermissionStorage(path) if path else MemoryPermissionStorage()
    return CachedPermissionStorage(RedisPermissionStorage("redis://127.0.0.1:6379/15"))


def build_keyboard() -> Keyboard:
    """一个回调按钮，点击后走 INTERACTION_CREATE。"""

    button = Button(
        id="click",
        render_data=ButtonRenderData(label="点我", visited_label="点过了", style=ButtonStyle.BLUE),
        action=ButtonAction(
            type=ButtonActionType.CALLBACK,
            data=ClickPayload(action="demo.click", note="按钮示例").model_dump_json(),
            permission=ButtonPermission(type=ButtonPermissionType.EVERYONE),
        ),
    )
    return Keyboard(content=KeyboardContent(rows=[KeyboardRow(buttons=[button])]))


async def timing(ctx: Context, call_next: Callable[[Context], Awaitable[Reply]]) -> Reply:
    """中间件：包住匹配之后的整条管线，异常照常往上抛。"""

    started = time.perf_counter()
    reply = await call_next(ctx)
    logger.info(
        "command {} took {:.1f}ms",
        ctx.command or "?",
        (time.perf_counter() - started) * 1000,
    )
    return reply


def build_router(store: CachedPermissionStorage) -> Router:
    router = Router(checker=PermissionChecker(store), reply_unknown=True)
    router.use(timing)
    install_permission_commands(router, store)

    @router.command("ping", on=GroupMessageCreate, description="回 pong")
    async def ping(ctx: GroupContext) -> Reply:
        return Reply(text="pong")

    @router.command(
        "echo <text:rest>",
        on=GroupMessageCreate,
        bind_args=False,
        usage="echo <text:rest>",
        description="原样回显",
    )
    async def echo(ctx: GroupContext, argv: list[str]) -> Reply:
        # bind_args=False：<text:rest> 收到的 token 原样进 argv，转换与关键字绑定都跳过
        return Reply(text=" ".join(argv) or "(空)")

    @router.command("roll", on=GroupMessageCreate, usage="roll [<sides:int>]", description="掷骰子")
    async def roll(ctx: GroupContext) -> Reply:
        # 可选参数靠注册第二条命令表达，不在模板里写默认值
        return Reply(text=f"掷出了 {random.randint(1, 6)}")

    @router.command(
        "roll <sides:int>",
        on=GroupMessageCreate,
        usage="roll [<sides:int>]",
        description="掷指定面数的骰子",
    )
    async def roll_sides(ctx: GroupContext, sides: int) -> Reply:
        if sides < 2:
            # UsageError 回用法行，其它异常统一回 internal_error
            raise UsageError("sides must be at least 2")
        return Reply(text=f"掷出了 {random.randint(1, sides)}")

    @router.command("me", on=GroupMessageCreate, description="看看自己的权限主体")
    async def me(ctx: GroupContext) -> Reply:
        account = ctx.account or "(频道不参与账号级)"
        return Reply(text=f"场景键 `{ctx.principal}`\n账号键 `{account}`", markdown=True)

    @router.command("button", on=GroupMessageCreate, description="发一条带按钮的消息")
    async def button(ctx: GroupContext) -> Reply:
        return Reply(text="点一下按钮", keyboard=build_keyboard())

    @router.button(ClickPayload, ack="pre")
    async def on_click(ctx: InteractionContext, payload: ClickPayload) -> Reply:
        # 互动事件发不出消息，换成分派就自动回应客户端；ack="pre" 已经替我们回了 OK
        await store.grant(ctx.principal, Grant(Demo.PING.key))
        logger.info("button clicked by {} note={}", ctx.principal, payload.note)
        return Reply.ok()

    # 子路由器：默认继承父级的 checker 和中间件，include 时前缀叠加
    admin = Router()

    @admin.command(
        "ban <member:mention>",
        on=GroupMessageCreate,
        permission=Demo.ADMIN,
        description="踢人",
    )
    async def ban(ctx: Context, member: str) -> Reply:
        return Reply(text=f"ban {member}")

    router.include(admin, prefix="admin")
    return router


async def main() -> None:
    store = build_store()
    router = build_router(store)

    # 第一个管理员：/permission grant 要 permission.grant，没有这一行就只能用内存/文件手动塞；
    # 授 permission.* 等于把 show / grant / revoke / role 四个键一起给
    owner = os.environ.get("QQ_BOT_OWNER", "user:D19DC0D6BAC8CAF24784306B2022F7D7").strip()
    if owner:
        await store.grant(owner, Grant("permission.*"))
        logger.info("bootstrapped permission.* for {}", owner)

    async with Bot(
        app_id=os.environ["QQ_BOT_APP_ID"],
        app_secret=os.environ["QQ_BOT_APP_SECRET"],
        adapter=WebSocketAdapter(
            session_storage=RedisSessionStorage.from_url("redis://127.0.0.1:6379/15")
        ),
    ) as bot:
        # 命令层不自己订阅事件：在自己的回调里决定要不要交给它，
        # 这样同一个事件还能先做记录、过滤或别的处理。
        @bot.on(GroupMessageCreate)
        async def on_group_message(ctx: EventContext[GroupMessageCreate]) -> None:
            result = await router.handle(ctx.event)
            if not result.handled:
                logger.debug("not a command: {}", ctx.event.content)

        @bot.on(InteractionCreate)
        async def on_interaction(ctx: EventContext[InteractionCreate]) -> None:
            result = await router.handle(ctx.event)
            if not result.handled:
                logger.debug("unclaimed button: {}", ctx.event.data)

        await bot.start()
        print("已连接，群里试 /ping、/roll 20、/echo 你好、/button、/me")
        print("  /permission grant @某人 demo.admin   # 需要机器人开启接收全部群消息")

        stopped = asyncio.Event()
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            # Windows 的 ProactorEventLoop 不支持信号处理，靠 Ctrl+C 抛 KeyboardInterrupt
            with contextlib.suppress(NotImplementedError):
                loop.add_signal_handler(sig, stopped.set)
        with contextlib.suppress(KeyboardInterrupt, asyncio.CancelledError):
            await stopped.wait()


if __name__ == "__main__":
    asyncio.run(main())
