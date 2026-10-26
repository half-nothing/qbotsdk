# qq-bot-sdk Roadmap

> 非官方 QQ 机器人 SDK · 目标：覆盖官方 API v2 的鉴权、REST、消息与事件层。
> 官方文档：<https://bot.q.qq.com/wiki/develop/api-v2/>

## 现状（2025，v0.1.0）

已实现：

- `constant.py`：API 根地址、token 接口地址、`QQBot` 鉴权头前缀
- `module/token_manager.py`：access_token 缓存、双检锁防并发踩踏、提前 60s 刷新
- `module/http_client.py`：aiohttp 会话管理、yarl URL 拼接、TraceConfig 全链路 trace 日志、`APIError`
- `bot.py`：Bot 门面，async context manager，仅 `get_me()`
- `model/`：`Token`、`User`（pydantic v2）

已知技术债：

- [ ] `resp.json()` 遇到空响应体/非 JSON 会抛原生异常，需要容错
- [ ] `ClientSession` 未配置超时
- [ ] token 刷新失败时应回退使用旧 token（旧 token 在到期前 60s 内仍有效）
- [ ] `model/__init__.py`、`module/__init__.py` 为空，导出未整理

---

## Phase 0 · 工程底座（≈1~2 天）

- [x] 提交当前未提交的改动（trace 日志、loguru 依赖、User 模型微调）· `72355bd`
- [x] 恢复 `tests/test_hello_route.py`（本地 aiohttp mock server 验证鉴权头注入 + token 缓存/刷新）· 抽成 `conftest.py` fixture 并入 Phase 1 的 T1
- [x] 引入 ruff（lint + format），保持 `mypy --strict` 通过 · ruff 0.17.2，line-length 100，ignore RUF001-003
- [x] GitHub Actions CI：Python 3.12 / 3.13 / 3.14 × pytest + mypy + ruff · `.github/workflows/check.yml`，`aac0d27`
- [x] README 充实：安装、鉴权原理（`QQBot <token>`）、快速开始

## Phase 1 · v0.2 REST 架构定型（≈1 周）

设计先行：[docs/design/phase1-rest-architecture.md](docs/design/phase1-rest-architecture.md)，六个实施切片 T1–T6。

进度：T1 传输层（`APIError`/`TransportError`/`ClientOptions`/超时/429/401）、T2 模型层（`QQModel` + 六个模型 + 官方示例快照）、T3 凭证生命周期（`refresh_at` / `hard_expire_at` 拆分 + 刷新失败回退）、T4 资源层（`bot.api.*` 四个域 + 六个只读接口 + 8 个端到端用例）已完成。

- [x] Resource 分层：`Bot.api.user` / `bot.api.guild` / `bot.api.channel` / `bot.api.message`，`bot.py` 退化为薄门面 · T4
- [x] `APIError` 完善：官方错误码体系、429 限流（`Retry-After`）自动重试、网络层超时与可配置重试 · T1
- [x] 频道基础接口：频道列表/详情、子频道列表/详情、成员列表、身份组 · T4
- [ ] 分页 helper（`limit`/`after` 模式统一封装）· T5
- [x] 每个接口配 mock-server 测试 · T4

## Phase 2 · v0.3 消息收发（≈1~2 周）

- [ ] 频道消息：发送、回复、撤回、分页拉取历史消息
- [ ] 富媒体上传 API（图片/语音/视频/文件，`/v2/users/@me/...`）
- [ ] 私信（Direct Message）与表情表态（Reactions）
- [ ] Ark / Markdown / Keyboard 模板消息模型
- [ ] 客户端限频器（平台限制：如频道消息 5s/条）

## Phase 3 · v0.4 事件接入（≈2~3 周，SDK 核心价值）

架构决策：以 [async-event-bus](https://github.com/half-nothing/async-event-bus) 为统一事件骨干，
Bot 门面提供装饰器语法糖（`@bot.on(...)` 委托 `bus.on(...)`），二者是分层关系而非二选一：

- 所有消息事件与系统事件（限频命中、重连、token 刷新、HTTP 错误）emit 到同一总线
- 事件载体：`AbstractEvent` 子类组合包裹 pydantic 模型（不直接继承 BaseModel），如 `AtMessageCreate` 携带 `AtMessage`
- SDK 内部机制用总线实现：高 weight 全局 filter 做事件去重（msgId/msgSeq），injector 注入 `bot` 引用
- 默认 `raise_exception=False` 隔离单个 handler 异常；`max_concurrent_tasks` 可配置
- 公开 API 不泄漏 `EventContext`/bus 内部类型，`bot.bus` 仅作进阶逃生口
- 前置条件：总线库补 `py.typed`（SDK 为 mypy strict）；文档注明 handler 优先 async（同步回调串行先执行）

- [ ] WebSocket Gateway：鉴权、心跳、断线 resume、多分片连接
- [ ] 事件模型映射到总线（`AT_MESSAGE_CREATE`、`DIRECT_MESSAGE_CREATE`、`GUILD_MEMBER_ADD` 等）
- [ ] `@bot.on(...)` 装饰器 API；echo-bot、群聊机器人示例
- [ ] WebHook 回调模式：Ed25519 签名校验、事件去重、快速 Ack（官方当前主推的事件通道）
- [ ] 群聊/单聊事件：`GROUP_AT_MESSAGE_CREATE`、`C2C_MESSAGE_CREATE`

## Phase 4 · v0.5+ 补全与发布

- [ ] 群聊/单聊主动消息发送 API
- [ ] 论坛、音频等长尾接口
- [ ] 发布到 PyPI；语义化版本策略；`CHANGELOG.md`
