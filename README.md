# qbotsdk

非官方 QQ 机器人 SDK

[![Python](https://img.shields.io/badge/Python-3.12%2B-blue)](https://www.python.org/)
[![License](https://img.shields.io/github/license/half-nothing/qbotsdk)](./LICENSE)
[![PyPI](https://img.shields.io/pypi/v/qbotsdk)](https://pypi.org/project/qbotsdk/)

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
        app_secret=os.environ["QQ_BOT_APP_SECRET"],
    ) as bot:
        me = await bot.api.user.me()
        print(f"登录成功：{me.username}")

        async for guild in bot.api.user.iter_guilds():
            channels = await bot.api.guild.channels(guild.id)
            print(f"{guild.name}：{len(channels)} 个子频道")


asyncio.run(main())
```

## 接收事件

默认走 WebSocket 长连接

```python
import asyncio

from async_event_bus import EventContext

from qbotsdk import Bot
from qbotsdk.model.event import C2CMessageCreate, GroupAtMessageCreate, InteractionCreate


async def main() -> None:
    # 认证信息的具体获取方式请查看“快速开始”章节
    async with Bot(app_id=..., app_secret=...) as bot:

        @bot.on(GroupAtMessageCreate)
        async def on_group_at(ctx: EventContext[GroupAtMessageCreate]) -> None:
            await ctx.event.reply("收到: " + ctx.event.content)

        @bot.on(C2CMessageCreate)
        async def on_c2c(ctx: EventContext[C2CMessageCreate]) -> None:
            await ctx.event.reply("收到: " + ctx.event.content)

        @bot.on(InteractionCreate)
        async def on_interaction(ctx: EventContext[InteractionCreate]) -> None:
            if ctx.event.needs_response:
                await ctx.event.respond()  # 不回应客户端会一直 loading

        await bot.start()
        await asyncio.sleep(3600)


asyncio.run(main())
```

bot的`adapter`参数默认为`WebSocketAdapter`，可以显式指定为`WebhookAdapter`  
也可以自行实现`Adapter`从而扩展更多接入方式，自行实现的`Adapter`需要继承`qbotsdk.adapter.Adapter`并实现两个抽象方法

`WebSocketAdapter`的会话状态默认存在内存里  
如果想关闭后自动续连，可以在构造`WebSocketAdapter`的时候传递参数`session_storage=`  
可选值为`MemorySessionStorage`, `FileSessionStorage`, `RedisSessionStorage`, 默认为`MemorySessionStorage`

```python
from qbotsdk import WebSocketAdapter
from qbotsdk.storage import FileSessionStorage

# 若不传存储路径，默认路径为软件运行目录下的.session.json文件
WebSocketAdapter(session_storage=FileSessionStorage())

# Redis 在可选依赖里, 使用前需要先安装qbotsdk[redis]
from qbotsdk.storage import RedisSessionStorage

# 给完整地址
WebSocketAdapter(session_storage=RedisSessionStorage.from_url("redis://:pwd@10.0.0.5:6379/2"))

# 或者只给零件, 地址由SDK拼
storage = RedisSessionStorage.from_url(host="10.0.0.5", port=6379, password="pwd", db=2)
WebSocketAdapter(session_storage=storage)

# Unix domain socket, 以及指定RESP协议版本
RedisSessionStorage.from_url(unix_socket="/var/run/redis/redis.sock", db=2, protocol=3)
```

也可以直接把现成的Redis客户端交给SDK

```python
# 特别注意，SDK需要的Redis实例全限定名是redis.asyncio.Redis
from redis.asyncio import Redis

from qbotsdk.storage import RedisSessionStorage

storage = RedisSessionStorage(Redis(host="10.0.0.5", port=6379))
```


### Webhook 接入

在[QQ机器人管理后台](https://q.qq.com/qqbot/dashboard/manage)填好回调地址并勾选要监听的事件后，
事件就改走 HTTP 推送，代码层面仅需把适配器换成 `WebhookAdapter`：

```python
from qbotsdk import Bot, WebhookAdapter

bot = Bot(
    # 认证信息的具体获取方式请查看“快速开始”章节
    app_id=...,
    app_secret=...,
    adapter=WebhookAdapter(
        "同app_secret",
        port=8443,
        path="/qbotsdk",
        certfile="certs/fullchain.pem",
        keyfile="certs/privkey.pem",
    ),
)
await bot.start()
```

没有公网地址时用反向代理或内网穿透把请求转到本机，务必原样透传 body 和两个签名头，任何改写都会导致验签失败。

如果事件要接进自己已有的aiohttp应用，不用起整套服务器，挂一个处理函数就行：

```python
from aiohttp import web

from qbotsdk import Bot, build_webhook_handler

bot = Bot(app_id=..., app_secret=...)
app = web.Application()
app.router.add_post("/qbotsdk", build_webhook_handler(bot.dispatcher, "机器人密钥"))
```

如果要使用flask等其他http框架，仿照该处理函数写一遍处理函数即可。

## 示例

具体示例请见[examples文件夹](examples/README.md)。

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
- 所有反馈过的使用者。

## 许可证

Apache-2.0，见 [LICENSE](LICENSE)。
