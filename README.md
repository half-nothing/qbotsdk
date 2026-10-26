# qq-bot-sdk

非官方 QQ 机器人 SDK。封装官方 API v2 的鉴权与频道域 REST 能力，异步优先，全量类型标注。

> 官方文档：<https://bot.q.qq.com/wiki/develop/api-v2/>
> 当前版本 `0.2.0`，能力面为「鉴权 + 机器人自身信息 + 频道/子频道/成员/身份组只读查询 + 群组只读查询」。后续规划见 [ROADMAP.md](ROADMAP.md)。

## 特性

| 能力 | 说明 |
| --- | --- |
| 凭证管理 | AppID + AppSecret 换取 `access_token`，自动缓存，到期前 60s 刷新，双检锁防并发重复请求，刷新失败时旧 token 未过期就继续用 |
| REST 资源层 | `bot.api.user` / `.guild` / `.group` / `.channel` / `.message` 分域，十二个只读接口开箱可用 |
| 错误体系 | 官方 `err_code` 映射为 `APIError.code`，附错误码枚举、`retryable` 判定与 `trace_id` |
| 容错 | 429 按 `Retry-After` 重试、5xx 与网络异常退避重试、401 自动刷新 token 后重试一次、204 与非 JSON 包体不抛异常 |
| 分页 | `iter_guilds` / `iter_members` / `bot.api.group.iter_members` 自动翻页，频道成员按 `user.id` 去重 |
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
| `iter_guilds` / `iter_members` / `bot.api.group.iter_members` | 自动翻页，频道成员按 `user.id` 去重 |

频道与群组是两套 ID 体系，不能混用：频道的 `guild_id` / `channel_id` / `user.id` 与群组的 `group_openid` / `member_openid` 互不相通。群接口都在 `/v2` 前缀下，且多数要求白名单权限（错误码 `11253`）。

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

## 许可证

Apache-2.0，见 [LICENSE](LICENSE)。
