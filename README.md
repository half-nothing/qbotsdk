# qbotsdk

非官方 QQ 机器人 SDK

[![Python](https://img.shields.io/badge/Python-3.12%2B-blue)](https://www.python.org/)
[![License](https://img.shields.io/github/license/half-nothing/qbotsdk)](./LICENSE)
[![PyPI](https://img.shields.io/pypi/v/qbotsdk)](https://pypi.org/project/qbotsdk/)
> QQ官方文档：https://bot.q.qq.com/wiki/develop/api-v2

## 特性

- **全异步**：基于 `asyncio` 与 `aiohttp`，所有接口均为异步接口。
- **登录态自动维护**：`access_token` 自动换取、缓存、到期前刷新。
- **连接与重连**：WebSocket 适配器自动心跳、断线重连与 Resume。
- **接入方式可插拔**：默认走 WebSocket 长连接，也可以换成 Webhook 回调，或自己实现 `Adapter`。
- **消息即对象**：收到的事件可以直接 `await event.reply(...)`。
- **容错内置**：429 按 `Retry-After` 重试，幂等请求遇 5xx 与网络异常退避重试，本地令牌桶限流，错误统一成 `QQBotError` 体系。
- **类型完整**：pydantic v2 模型、全量类型标注、随包分发 `py.typed`。

## 安装

包名与导入名均为 `qbotsdk`，要求 Python 版本 >= 3.12。

```bash
pip install qbotsdk
uv add qbotsdk           # uv 项目里加依赖
uv pip install qbotsdk   # 或直接装进当前环境
```

要从源码安装

```bash
git clone https://github.com/half-nothing/qbotsdk.git
cd qbotsdk

pip install -e .         # 可编辑模式，改完立刻生效
uv pip install -e .      # uv 同理
```

## 快速开始

```python
import asyncio
import os

from qbotsdk import Bot


async def main() -> None:
    # https://q.qq.com/qqbot/dashboard/manage
    # 进入上方网站管理机器人，在开发设置中找到“AppID 接入凭证”卡片
    # 将环境变量QQ_BOT_APP_ID设为获取到的AppID
    # 将环境变量QQ_BOT_APP_SECRET设为获取到的AppSecret
    # 如果您选择直接替换对应内容，请不要将携带敏感信息的文件提交到仓库
    async with Bot(
        app_id=os.environ["QQ_BOT_APP_ID"],
        client_secret=os.environ["QQ_BOT_APP_SECRET"],
    ) as bot:
        me = await bot.api.user.me()
        print(f"登录成功：{me.username}")

        async for guild in bot.api.user.iter_guilds():
            channels = await bot.api.guild.channels(guild.id)
            print(f"{guild.name}：{len(channels)} 个子频道")


asyncio.run(main())
```

## 接收事件

默认走 WebSocket 长连接，换接入方式就传 `adapter=`，`start()` 的用法不变。下面是长连接：

```python
import asyncio

from async_event_bus import EventContext

from qbotsdk import Bot
from qbotsdk.model.event import C2CMessageCreate, GroupAtMessageCreate, InteractionCreate


async def main() -> None:
    # 认证信息的具体获取方式请查看“快速开始”章节
    async with Bot(app_id=..., client_secret=...) as bot:

        @bot.on(GroupAtMessageCreate)
        async def on_group_at(ctx: EventContext[GroupAtMessageCreate]) -> None:
            await ctx.event.reply("收到: " + ctx.event.content)

        @bot.on(C2CMessageCreate)
        async def on_c2c(ctx: EventContext[C2CMessageCreate]) -> None:
            await ctx.event.reply("收到: " + ctx.event.content)

        @bot.on(InteractionCreate)
        async def on_interaction(ctx: EventContext[InteractionCreate]) -> None:
            await ctx.event.respond()  # 不回应客户端会一直 loading

        await bot.start()
        await asyncio.sleep(3600)


asyncio.run(main())
```

不传 `adapter` 等价于 `adapter=WebSocketAdapter()`；自己实现接入方式只需两个方法：
`start(context)` 里把事件塞进 `context.dispatcher.handle(payload)`，`stop()` 里收摊。

会话状态默认存在内存里（进程重启就从 Identify 重来）。想跨进程续连，换成文件或 Redis 存储：
会话 ID 一变就立刻落盘，序号合并成每秒最多一次，而且有定时兜底——即使之后没有新事件，
待写的值最迟 `flush_interval`（默认 1 秒）后也会写进去；`close()` 时再强制刷一次。
下次启动直接 Resume，停机期间平台暂存的事件会被补发；文件读不出来或会话被平台作废时自动回到 Identify。

```python
from qbotsdk import WebSocketAdapter
from qbotsdk.storage import FileSessionStorage

WebSocketAdapter(session_storage=FileSessionStorage(".qbotsdk-session.json"))

# Redis 在可选依赖里, 没装时连类都取不到
from qbotsdk.storage import RedisSessionStorage

# 给完整地址
WebSocketAdapter(session_storage=RedisSessionStorage.from_url("redis://:pwd@10.0.0.5:6379/2"))

# 或者只给零件, 地址由 SDK 拼（密码里的 @ / : 不用自己转义）
storage = RedisSessionStorage.from_url(host="10.0.0.5", port=6379, password="pwd", db=2)
WebSocketAdapter(session_storage=storage)

# Unix domain socket, 以及指定 RESP 协议版本
RedisSessionStorage.from_url(unix_socket="/var/run/redis/redis.sock", db=2, protocol=3)
```

也可以直接把现成的客户端交给 SDK，配置（连接池、集群、代理）都按你自己的来：

```python
from redis.asyncio import Redis

from qbotsdk.storage import RedisSessionStorage

storage = RedisSessionStorage(Redis(host="10.0.0.5", port=6379))
```

这种情形 `decode_responses` 不一定开着，`load()` 对返回的字节和字符串都能处理。

Redis 存储要先装 `pip install qbotsdk[redis]`；没装时 `RedisSessionStorage` 会抛 `ImportError`
并提示装哪个额外依赖，而 `qbotsdk.storage` 本身照常导入、不拉起 redis。

### Webhook 接入

在[管理端](https://q.qq.com/qqbot/#/developer/webhook-setting)填好回调地址并勾选要监听的事件后，
事件就改走 HTTP 推送，把适配器换成 `WebhookAdapter` 就行，`start()` 的用法不变：

```python
from qbotsdk import Bot, WebhookAdapter

bot = Bot(
    app_id=...,
    client_secret=...,
    adapter=WebhookAdapter(
        "机器人密钥",
        port=8443,
        path="/qbotsdk",
        certfile="certs/fullchain.pem",
        keyfile="certs/privkey.pem",
    ),
)
await bot.start()
```
    bot_secret=...,
    port=8443,
    path="/qbotsdk",
    certfile="certs/fullchain.pem",
    keyfile="certs/privkey.pem",
)
await server.start()
```

长连接与回调建议只选一种：两边同时开会收到重复推送，分发器虽然按事件 `id` 做了去重，但没必要浪费一次请求。  
没有公网地址时用反向代理或内网穿透把请求转到本机，务必原样透传 body 和两个签名头，任何改写都会导致验签失败。

## 第三方依赖

| 依赖                                                                 | 用途                      | 许可                         |
|--------------------------------------------------------------------|-------------------------|----------------------------|
| [aiohttp](https://github.com/aio-libs/aiohttp)                     | HTTP 与 WebSocket 客户端    | Apache-2.0 AND MIT         |
| [pydantic](https://github.com/pydantic/pydantic)                   | 数据模型与校验                 | MIT                        |
| [loguru](https://github.com/Delgan/loguru)                         | 日志                      | MIT                        |
| [cryptography](https://github.com/pyca/cryptography)               | Webhook 的 ed25519 签名与验签 | Apache-2.0 OR BSD-3-Clause |
| [async-event-bus](https://github.com/half-nothing/async-event-bus) | 事件总线                    | MIT                        |
| [yarl](https://github.com/aio-libs/yarl)                           | URL 拼接                  | Apache-2.0                 |

## 致谢

- [QQ 机器人官方文档](https://bot.q.qq.com/wiki/develop/api-v2)：字段、错误码与协议细节都以它为准。
- [async-event-bus](https://github.com/half-nothing/async-event-bus)：事件总线。
- [aiohttp](https://github.com/aio-libs/aiohttp)：HTTP 与 WebSocket 客户端。
- [pydantic](https://github.com/pydantic/pydantic)：数据模型与校验。
- [loguru](https://github.com/Delgan/loguru)：日志。
- [cryptography](https://github.com/pyca/cryptography)：ed25519 签名与验签。
- [yarl](https://github.com/aio-libs/yarl)：URL 拼接。
- 腾讯官方 Python SDK 文档与社区实现：心跳、Resume、关闭码语义对照过。
- 所有反馈过的使用者：错误码与平台行为变化靠实际运行对齐。

## 许可证

Apache-2.0，见 [LICENSE](LICENSE)。
