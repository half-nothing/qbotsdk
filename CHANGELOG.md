# 更新日志

本项目遵循[语义化版本](https://semver.org/lang/zh-CN/)，格式参考
[Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)。

改动按版本号归档，尚未发版的改动记在「未发布」下。

## [未发布]

### 计划中

- 论坛 threads 与音频 actions 的接口（官方文档缺页，取证后再实现）。
- VitePress 文档站与 API 自动生成。
- PyPI 发布自动化：Trusted Publishing + OIDC，省掉手动令牌。

### 记录

- 新增会话存储抽象 `SessionStorage`：内置内存、文件、Redis 三种实现，
  `WebSocketAdapter(session_storage=...)` 可跨进程续连；默认内存存储，
  文件存储的会话 ID 一变就落盘、序号每秒最多写一次，另有定时兜底保证事件停下后待写的值也会落盘，
  `close()` 时强制刷盘；Redis 存储在 `qbotsdk[redis]` 可选依赖里。
- 新增 `FileSessionStorage` 与 `RedisSessionStorage`（`from_url` 既收完整地址，也能只给
  `host`/`port`/`db`/`username`/`password`/`ssl` 由 SDK 拼地址并转义密码，支持 Unix socket 路径
  与 `protocol=2|3`；也可以直接接手一个现成的 `Redis` 客户端，那种情况下 `load()` 对字节响应同样兼容），
  文件损坏或会话被平台作废时自动回到 Identify。Redis 实现在可选依赖 `qbotsdk[redis]` 里，
  没装时取 `RedisSessionStorage` 直接抛 `ImportError`，`qbotsdk.storage` 本身不依赖 redis。
- 会话存储从 `qbotsdk.gateway.storage` 移到顶层的 `qbotsdk.storage`，层级少一层、也不再从属于网关。
- 新增 `qbotsdk.__version__`（取自安装元数据，直接拿源码跑时退回 `0.0.0`）；
  `pyproject.toml` 补齐 `keywords`、`maintainers`、`project.urls` 与 `Typing :: Typed` 等分类，
  许可证改成 SPDX 表达式 `Apache-2.0` + `license-files`。
- **破坏性变更**：事件接入改为适配器模式，`Bot` 默认使用 `WebSocketAdapter()`。
  `WebhookAdapter(...)` 走回调模式，也可以自己实现 `Adapter` 接别的框架；
  `Bot` 的 `intents` 与 `shard` 参数移到 `WebSocketAdapter`，`WebhookServer` 的第一个参数从 `Bot` 改成 `Dispatcher`。
- 项目改名：发行名 `qq-bot-sdk` → `qbotsdk`，导入包 `qqbot` → `qbotsdk`。
  原因是 PyPI 上已有同词干的 `qqbot` 项目，原名被判为「过于相似」而无法发布。
- 当前能力范围（鉴权、REST 接口、消息收发、事件接入、Webhook）以 README 为准。
