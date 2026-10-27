# 更新日志

## [0.6.0] - 2026-10-28

首个发布到 PyPI 的版本。

### 新增

- 事件接入改为适配器模式，默认提供`WebSocketAdapter`与`WebhookAdapter`，默认使用 `WebSocketAdapter()`
- 会话存储抽象 `SessionStorage`
- 新增 `build_webhook_handler(dispatcher, app_secret)`
- 群聊与单聊消息带 `keyboard` 时自动升成 Markdown 消息
- 新增 `qbotsdk.__version__`
- 新增六个示例以及`examples/README.md`。

### 变更

- 会话存储从 `qbotsdk.gateway.storage` 移到顶层的 `qbotsdk.storage`。
- Redis 支持抽成可选依赖 `qbotsdk[redis]`
- 全仓导入统一为绝对导入，由 `ruff` 的 `TID` 规则约束。

### 破坏性变更

- `Bot` 默认使用 `WebSocketAdapter()`；`Bot` 的 `intents` 与 `shard` 参数移到 `WebSocketAdapter`。
- `WebhookServer` 的第一个参数从 `Bot` 改成 `Dispatcher`。

[0.6.0]: https://github.com/half-nothing/qbotsdk/releases/tag/v0.6.0
