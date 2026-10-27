# qq-bot-sdk

非官方 QQ 机器人 SDK。封装官方 API v2 的鉴权、频道与群组 REST 能力、消息发送/撤回以及事件接入，异步优先，全量类型标注。

> 官方文档：<https://bot.q.qq.com/wiki/develop/api-v2/>
> 当前版本 `0.5.0`，能力面为「鉴权 + 机器人自身信息 + 频道/子频道/成员/身份组只读查询 + 群组只读查询 + 频道/群/单聊消息发送与撤回 + 富媒体上传 + 表情表态 + 互动回调 + WebSocket / Webhook 事件接入」。变更见 [CHANGELOG.md](CHANGELOG.md)，后续规划见 [ROADMAP.md](ROADMAP.md)。

## 特性

| 能力 | 说明 |
| --- | --- |
| 凭证管理 | AppID + AppSecret 换取 `access_token`，自动缓存，到期前 60s 刷新，双检锁防并发重复请求，刷新失败时旧 token 未过期就继续用 |
| REST 资源层 | `bot.api.user` / `.guild` / `.group` / `.channel` / `.message` 分域，十二个只读接口开箱可用 |
| 错误体系 | 官方 `err_code` 映射为 `APIError.code`，附错误码枚举、`retryable` 判定与 `trace_id` |
| 容错 | 429 按 `Retry-After` 重试、5xx 与网络异常退避重试、401 自动刷新 token 后重试一次、204 与非 JSON 包体不抛异常 |
| 分页 | `iter_guilds` / `iter_members` / `bot.api.group.iter_members` 自动翻页，频道成员按 `user.id` 去重 |
| 消息发送 | 频道与群消息发送、撤回；`msg_type` 0/2/7 自动推断，支持 Markdown、键盘按钮与 `multipart` 图片直传 |
| 富媒体 | 群文件 URL 上传与 5MB 以内二进制直传，返回的 `file_info` 直接用于发送 |
| 事件接入 | WebSocket 长连接（心跳、Resume、关闭码驱动的重连）与 Webhook 两种方式，`bot.on()` 注册处理器；Webhook 自带 op 13 验证、验签与快速 ACK |
| 数据模型 | pydantic v2，字段别名钉住官方命名，未知字段不报错 |
| 类型 | `py.typed` 随包分发，`mypy --strict` 通过 |


## 环境要求

- Python >= 3.12
- 运行时依赖：aiohttp、pydantic v2、yarl、loguru

## 安装

尚未发布到 PyPI，从源码安装：

```bash
git clone <repo-url> qq-bot-sdk
cd qq-bot-sdk
pdm install
```

作为依赖引入本地项目：

```bash
pdm add --editable /path/to/qq-bot-sdk
```

## 快速开始

```python
import asyncio
import os

from qqbot import Bot


async def main() -> None:
    async with Bot(
        app_id=os.environ["QQ_BOT_APP_ID"],
        client_secret=os.environ["QQ_BOT_APP_SECRET"],
    ) as bot:
        me = await bot.api.user.me()
        print(f"登录成功：{me.username} (id={me.id})")

        async for guild in bot.api.user.iter_guilds():
            channels = await bot.api.guild.channels(guild.id)
            print(f"{guild.name}：{len(channels)} 个子频道")


if __name__ == "__main__":
    asyncio.run(main())
```

完整可运行版本见 [`examples/hello.py`](examples/hello.py)：除了频道与子频道，它还会在设置了
`QQ_BOT_GROUP_OPENID` 时列出该群的信息、机器人在群内的状态与全部成员。群 openid 只能从消息事件里拿到，
官方没有「群列表」接口，所以示例用一个环境变量指定群。

常用查询：

| 调用 | 说明 |
| --- | --- |
| `bot.api.user.me()` | 机器人自身信息 |
| `bot.api.user.guilds(limit=50)` | 频道列表，单页拉取 |
| `bot.api.guild.get(guild_id)` | 频道详情 |
| `bot.api.guild.channels(guild_id)` | 子频道列表 |
| `bot.api.guild.members(guild_id, limit=100)` | 成员列表，单页拉取 |
| `bot.api.guild.roles(guild_id)` | 身份组列表 |
| `bot.api.channel.get(channel_id)` | 子频道详情 |
| `bot.api.group.get(group_openid)` | 群基本信息 |
| `bot.api.group.bot_state(group_openid)` | 机器人在群内的状态 |
| `bot.api.group.members(group_openid, cursor=cursor)` | 群成员单页，每次最多 30 条 |
| `bot.api.group.member(group_openid, member_openid)` | 单个群成员 |
| `bot.api.group.mute_setting(group_openid)` | 群禁言状态，需机器人为群管理员 |
| `bot.api.channel.send_message(channel_id, content="hi")` | 发频道消息，返回 `Message` |
| `bot.api.channel.recall_message(channel_id, message_id)` | 撤回频道消息，2 分钟内有效 |
| `bot.api.group.send_message(group_openid, content="hi")` | 发群消息，返回 `GroupMessageReceipt` |
| `bot.api.group.upload_file(group_openid, FileType.IMAGE, url=...)` | 上传群富媒体，返回 `file_info` |
| `bot.api.reaction.add(channel_id, message_id, EmojiType.SYSTEM, "4")` | 给频道消息发表情表态 |
| `bot.api.reaction.remove(channel_id, message_id, EmojiType.SYSTEM, "4")` | 删除自己发的表态 |
| `bot.api.reaction.users(channel_id, message_id, EmojiType.SYSTEM, emoji_id="4")` | 表态用户列表单页，`limit` 1–100 |
| `iter_guilds` / `iter_members` / `bot.api.group.iter_members` / `bot.api.reaction.iter_users` | 自动翻页，频道成员与表态用户按 `id` 去重 |

频道与群组是两套 ID 体系，不能混用：频道的 `guild_id` / `channel_id` / `user.id` 与群组的 `group_openid` / `member_openid` 互不相通。群接口都在 `/v2` 前缀下，且多数要求白名单权限（错误码 `11253`）。

## 发消息

```python
from qqbot import Bot
from qqbot.model.media import FileType, MediaInfo

async with Bot(app_id=..., client_secret=...) as bot:
    # 频道：文本、Markdown、引用回复、本地图片直传
    message = await bot.api.channel.send_message(channel_id, content="hello")
    await bot.api.channel.send_message(channel_id, content="收到", reply_to=message.id)

    # 群：msg_type 由内容自动推断（文本 0 / Markdown 2 / 富媒体 7）
    uploaded = await bot.api.group.upload_file(
        group_openid, FileType.IMAGE, file_name="a.png", file_data=png_bytes
    )
    await bot.api.group.send_message(group_openid, media=MediaInfo(file_info=uploaded.file_info))

    # 单聊：多一个 msg_type 6（输入中状态），被动回复窗口 60 分钟
    await bot.api.user_message.send_message(user_openid, content="hi")
    await bot.api.user_message.notify_input(user_openid, seconds=30)
```

单聊与群聊的差别只有三处：`msg_type` 多一个 6、被动回复窗口是 60 分钟且每条消息最多回 4 次、多一个 `is_wakeup` 互动召回字段（与 `reply_to`、`event_id` 互斥）。

几处平台限制值得先知道：

1. **被动回复有窗口**：收到消息后 5 分钟内才算被动回复，每条消息最多回 5 次。超出窗口再发就是主动消息。
2. **`msg_seq` 决定去重**：同一个 `msg_id` + `msg_seq` 重复发送会被平台拒绝（`40054005`）。SDK 只在 `reply_to` 且未给 `msg_seq` 时补 `1`，要回第二次请显式传 `msg_seq=2`——进程重启后自增计数不共享，SDK 不做进程内计数。
3. **主动消息有配额**：子频道每天 20 条、每天最多 2 个子频道，主被动合计每秒 5 条；超限返回 `40034100`。
4. **撤回有时限**：发送后 2 分钟内可撤回，超过就失败。
5. **`image` 与 `file_image` 二选一**：前者是 URL 由服务端转存，后者是本地字节走 `multipart`，同时给会抛 `ValueError`。
6. **单聊富媒体只支持 URL**：`user_message.upload_file` 只实现 `url` 方式，官方未给单聊 `file_data` 的字段表，本地文件请先上传到可访问地址。
7. **本地配额默认开启**：`ClientOptions.respect_rate_limits=True`（默认）时，`send_message` 按 `openid` 做进程内令牌桶（群聊与单聊都是 20 条/分钟，可用 `rate_limits={"group": 30, "c2c": 10}` 覆盖），超限抛 `RateLimitExceededError`，请求不会发出去。令牌桶只在**本进程**有效，多实例部署仍会撞服务端 `40034100`，那条路径照常抛 `APIError`。关掉它：`ClientOptions(respect_rate_limits=False)`。

## 接收事件

```python
import asyncio

from async_event_bus import EventContext

from qqbot import Bot
from qqbot.model.event import (
    C2CMessageCreate,
    ChannelMessageCreate,
    GroupAtMessageCreate,
    InteractionCreate,
    UnknownEvent,
)


async def main() -> None:
    async with Bot(app_id=..., client_secret=...) as bot:

        @bot.on(GroupAtMessageCreate)
        async def on_group_at(ctx: EventContext[GroupAtMessageCreate]) -> None:
            await ctx.event.reply("收到: " + ctx.event.content)

        @bot.on(C2CMessageCreate)
        async def on_c2c(ctx: EventContext[C2CMessageCreate]) -> None:
            await ctx.event.reply("收到: " + ctx.event.content)

        @bot.on(ChannelMessageCreate)
        async def on_channel_at(ctx: EventContext[ChannelMessageCreate]) -> None:
            await ctx.event.reply("收到: " + ctx.event.content)

        @bot.on(InteractionCreate)
        async def on_interaction(ctx: EventContext[InteractionCreate]) -> None:
            await ctx.event.respond()  # 不回应客户端会一直 loading

        @bot.on_unknown()
        async def on_unknown(ctx: EventContext[UnknownEvent]) -> None:
            print("unhandled event:", ctx.event.t)

        await bot.start()  # 连上网关, 后台开始收事件, 立即返回
        await asyncio.sleep(3600)  # 换成你的主循环


asyncio.run(main())
```

几个要点：

1. **处理器只收 `async def`**，参数是 `EventContext`，事件对象在 `ctx.event`；同步函数注册时直接抛 `TypeError`。
2. **能不能回复看方法**：`GroupAtMessageCreate`、`C2CMessageCreate`、`ChannelMessageCreate` 上有 `reply()`，其它事件没有这个方法——类型检查与 IDE 提示会直接告诉你，不需要额外的能力查询。
3. **`ctx.event.reply()` 自动补 `msg_id`**，并在同一条事件上把 `msg_seq` 从 1 自增，避免撞上「重复消息」；群聊每条消息最多回 5 次、单聊 4 次，第 6 次（单聊第 5 次）在本地直接抛 `ValueError("passive reply limit reached")`，不用等服务端的 `40034128`。
4. **`Bot.start()` 不做阻塞**，`bot.stop()` / `async with` 退出时才断开网关；`stop()` 会清空订阅，再次 `start()` 需要重新注册。
5. **去重**：官方说明同一消息可能重复推送，分发器默认记住最近 512 条消息 ID 直接丢弃重复（`dedupe_size=0` 关闭）。
6. **互动回调必须回应**：`InteractionCreate` 的 `type` 为 11（消息按钮）或 12（快捷菜单）时要调 `respond()`，否则客户端一直 loading；`respond(InteractionCode.ADMIN_ONLY)` 可以把结果回给客户端，同一个 `id` 只能回应一次。
7. **`AT_MESSAGE_CREATE` 的字段出处**：官方 api-v2 没有这个事件的事件体页面，`ChannelMessageCreate` 直接继承「消息对象(Message)」表格建模，字段与频道发送接口的响应同源；`GUILD_MEMBERS` 不在默认 intents 里，频道成员相关事件需要显式传 `intents`。
8. **未建模事件**：没登记的事件（如 `GUILD_CREATE`、`MESSAGE_DELETE`）统一落到 `on_unknown`，`ctx.event.t` 是原始事件名。

可直接运行的完整版本见 [`examples/websocket.py`](examples/websocket.py)：群、单聊、频道、互动、未知事件五类处理器，带 Ctrl+C 优雅退出。

### Webhook 接入

不想维持长连接就换 Webhook：平台把事件推到你自己的地址，SDK 负责验签、回 ACK 与分发。

```python
import asyncio

from async_event_bus import EventContext

from qqbot import Bot
from qqbot.gateway import WebhookServer
from qqbot.model.event import GroupAtMessageCreate


async def main() -> None:
    async with Bot(app_id=..., client_secret=...) as bot:

        @bot.on(GroupAtMessageCreate)
        async def on_group_at(ctx: EventContext[GroupAtMessageCreate]) -> None:
            await ctx.event.reply("收到: " + ctx.event.content)

        server = WebhookServer(
            bot,
            bot_secret=...,
            port=8443,
            path="/qqbot",
            certfile="certs/fullchain.pem",
            keyfile="certs/privkey.pem",
        )
        await server.start()
        await asyncio.sleep(3600)  # 换成你的主循环
        await server.close()


asyncio.run(main())
```

1. **op 13 地址验证自动应答**：平台配置回调地址时会推一帧 `op 13`，服务器用 botSecret 签名后回 `plain_token` 与 `signature`，不需要自己写。
2. **先验签再解析**：普通回调校验 `X-Signature-Ed25519` 与 `X-Signature-Timestamp`，签名体是「时间戳 + 原始报文」，失败直接 `401`。
3. **先 ACK 再分发**：验签通过先回 `{"op": 12, "d": {}}`，再把事件丢给同一个分发器，处理器慢也不会被平台重推。
4. **TLS 三种用法**：`certfile` 与 `keyfile` 成对；或传现成的 `ssl_context`；都不传走明文，端口为 443/8443 时会打 warning。证书热更新不在本期，换证书要 `close()` 后重新 `start()`。
5. **反向代理**：代理层必须原样透传请求体与两个签名头，任何重压、转码或 JSON 重排都会让验签失败。
6. **自己接框架**：不想用这个服务器就从 `qqbot.gateway` 取 `build_validation_response`、`verify_webhook_signature`、`parse_webhook_event`，接 FastAPI / Flask 都行，它们是纯函数。

## 鉴权原理

1. 用 AppID 与 AppSecret 请求 `/app/getAppAccessToken`，拿到 `access_token` 与 `expires_in`，有效期通常 7200 秒。
2. 之后每个请求带上 `Authorization: QQBot <access_token>`。前缀是 `QQBot`，不是 `Bearer`。
3. SDK 缓存 token 并在到期前 60 秒触发刷新，并发调用由双检锁收敛成一次凭证请求。平台只在旧 token 临近到期时才签发新的，提前刷新是官方推荐做法。刷新失败时，只要旧 token 还没真正过期就继续用它，一次凭证抖动不会打断业务调用。

## 日志

SDK 基于 loguru，只写 TRACE 级别的网络与凭证日志，不安装 handler。输出到哪里、什么级别，完全由接入方决定：

```python
from loguru import logger

logger.add("qqbot.log", level="TRACE")
```

## 开发

```bash
pdm install -d
pdm run ruff check
pdm run ruff format --check
pdm run mypy
pdm run pytest -q
```

CI 在 Python 3.12 / 3.13 / 3.14 三个版本上跑同一套检查，见 [`.github/workflows/check.yml`](.github/workflows/check.yml)。

装了 GNU Make 的可以直接用根目录的 [`Makefile`](Makefile)：`make check` 一次跑完四项门禁，`make help` 列出全部快捷命令。

文案约定：异常消息与日志统一英文（例如 `GET /users/@me request failed: ...`），注释与文档保持中文。

## 发布

```bash
pdm build        # 产出 dist/ 下的 sdist 与 wheel
```

打 `v*` 标签或手动触发 [`.github/workflows/release.yml`](.github/workflows/release.yml) 后，CI 会先跑四项门禁，再构建并校验产物（wheel 必须带 `py.typed`、不能把 `tests/` 与 `docs/` 打进去），最后在 GitHub 上创建**草稿** Release 并挂上 `dist/*`。

当前**不发布到 PyPI**：等线上环境跑通后再接 Trusted Publishing（OIDC），复用同一个工作流末尾追加 `pdm publish` 即可。版本记录见 [CHANGELOG.md](CHANGELOG.md)。

## 许可证

Apache-2.0，见 [LICENSE](LICENSE)。
