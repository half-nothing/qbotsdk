# qq-bot-sdk

非官方 QQ 机器人 SDK。封装官方 API v2 的鉴权与 REST 能力，异步优先，全量类型标注。

> 官方文档：<https://bot.q.qq.com/wiki/develop/api-v2/>
> 当前版本 `0.1.0`，能力面为「鉴权 + 机器人自身信息」。后续规划见 [ROADMAP.md](ROADMAP.md)。

## 特性

| 能力 | 说明 |
| --- | --- |
| 凭证管理 | AppID + AppSecret 换取 `access_token`，自动缓存，到期前 60s 刷新，双检锁防并发重复请求 |
| HTTP 层 | aiohttp 会话复用，yarl 拼接 URL，TraceConfig 输出全链路日志 |
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
        me = await bot.get_me()
        print(f"登录成功：{me.username} (id={me.id}, bot={me.bot})")


if __name__ == "__main__":
    asyncio.run(main())
```

完整可运行版本见 [`examples/hello.py`](examples/hello.py)。

## 鉴权原理

1. 用 AppID 与 AppSecret 请求 `/app/getAppAccessToken`，拿到 `access_token` 与 `expires_in`，有效期通常 7200 秒。
2. 之后每个请求带上 `Authorization: QQBot <access_token>`。前缀是 `QQBot`，不是 `Bearer`。
3. SDK 缓存 token 并在到期前 60 秒触发刷新，并发调用由双检锁收敛成一次凭证请求。平台只在旧 token 临近到期时才签发新的，提前刷新是官方推荐做法。

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
