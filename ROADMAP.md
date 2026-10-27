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

## Phase 1 · v0.2 REST 架构定型（≈1 周）· 已关账 2026-10-26

设计先行：[docs/design/phase1-rest-architecture.md](docs/design/phase1-rest-architecture.md)，六个实施切片 T1–T6，另加增补片 T7（群组只读）。

进度：T1 传输层（`APIError`/`TransportError`/`ClientOptions`/超时/429/401）、T2 模型层（`QQModel` + 六个模型 + 官方示例快照）、T3 凭证生命周期（`refresh_at` / `hard_expire_at` 拆分 + 刷新失败回退）、T4 资源层（`bot.api.*` 四个域 + 七个只读接口 + 8 个端到端用例）、T5 分页（`paginate` 生成器 + `iter_guilds` / `iter_members`）、T6 收尾（README 快速开始、`examples/hello.py` 频道列表、版本号 `0.2.0`）、T7 群组只读（`bot.api.group` 五个接口 + `next_cursor` 翻页）已完成，Phase 1 关账。

- [x] Resource 分层：`Bot.api.user` / `bot.api.guild` / `bot.api.group` / `bot.api.channel` / `bot.api.message`，`bot.py` 退化为薄门面 · T4
- [x] `APIError` 完善：官方错误码体系、429 限流（`Retry-After`）自动重试、网络层超时与可配置重试 · T1
- [x] 频道基础接口：频道列表/详情、子频道列表/详情、成员列表、身份组 · T4
- [x] 群组只读接口：群基本信息、机器人群内状态、群成员列表/详情、群禁言状态 · T7
- [x] 分页 helper（`limit`/`after` 模式统一封装）· T5
- [x] 每个接口配 mock-server 测试 · T4

## Phase 2 · v0.3 消息发送与撤回（≈1 周）· 已关账 2026-10-26

设计先行：[docs/design/phase2-message-send.md](docs/design/phase2-message-send.md)，六个实施切片 T1–T6，六项拍板 D1–D6 均已在设计文档 §14 落定。

范围收窄为「只发与只撤，不收」：事件与 WebSocket 仍在 Phase 3，单聊（C2C）、频道私信、表情表态、历史消息分页、客户端限流器与群分片上传一并顺延。

进度：T1 消息模型（`Message` / `GroupMessageReceipt` / `UploadedFile` / 键盘 / 草稿 + 官方示例快照）、T2 传输层 multipart（`post_form` + `ClientOptions.retry_post`）、T3 频道发送与撤回（JSON + `file_image` 直传）、T4 群发送与撤回（`msg_type` 推断 + `msg_seq`）、T5 群富媒体上传（URL 与 ≤5MB 二进制）、T6 收尾（README、示例、版本号 `0.3.0`）已完成，Phase 2 关账。

- [x] 频道消息发送：文本 / Markdown / 引用回复（`POST /channels/{channel_id}/messages`）· T3
- [x] 频道消息撤回：`DELETE /channels/{channel_id}/messages/{message_id}?hidetip=` · T3
- [x] 群消息发送：`msg_type` 0/2/7 自动推断、`msg_seq` 去重语义、引用回复（`POST /v2/groups/{group_openid}/messages`）· T4
- [x] 群消息撤回：`DELETE /v2/groups/{group_openid}/messages/{message_id}`，2 分钟时限 · T4
- [x] 群富媒体上传：URL 上传 + 5MB 以内二进制直传（`POST /v2/groups/{group_openid}/files`）· T5
- [x] 消息模型：频道 `Message`（官方示例 12 字段）、群 `GroupMessageReceipt`、`UploadedFile` · T1
- [x] `HTTPClient` 支持 `multipart/form-data`，新增 `ClientOptions.retry_post`（默认关）· T2

## Phase 3 · v0.4 事件接入（≈2~3 周，SDK 核心价值）

设计文档：[`docs/design/phase3-events.md`](docs/design/phase3-events.md)（14 节，含 D1–D5 拍板记录）。
架构决策：事件总线用 [`async-event-bus`](https://pypi.org/project/async-event-bus/)，`gateway/` 自己做连接、心跳、Resume 与帧到事件的转换，`Dispatcher` 是总线的薄门面；处理器统一 `async def handler(ctx: EventContext[E])`，事件对象在 `ctx.event`，支持回复的事件类型自己带 `reply()` 方法（`EventModel` 因此不 frozen，`api` 由分发器注入）。

- [x] T1 `gateway/payload.py`（OpCode / Intents / 关闭码表 / 错误类）+ `model/event.py` · 2026-10-27
- [x] T2 WebSocket Gateway：Hello、Identify、READY、心跳 · 2026-10-27
- [x] T3 Resume、关闭码处理、退避重连 · 2026-10-27（与 T2 一并完成）
- [x] T4 分发层 + `bot.on(...)` + `event.reply()` · 2026-10-27（总线 `async-event-bus`，`Bot.start()` 接网关，`event.reply()` 自动带 `msg_id` 与递增 `msg_seq`）
- [x] T5 WebHook 函数层：op 13 签名、请求验签、parse · 2026-10-27（`gateway/webhook.py`，官方向量入测）
- [x] T6 `WebhookServer`：开箱即用服务器（TLS 终结、快速 ACK、优雅关闭）· 2026-10-27（`gateway/webhook_server.py`，8 用例含自签证书 TLS 链路）

进度：T1–T6 全部完成，Phase 3 关账，版本 `0.4.0`（`Bot` 可 WebSocket 长连接或 Webhook 两种方式收事件）。


## Phase 4 · v0.5+ 补全与发布

- [ ] 群聊/单聊主动消息发送 API
- [ ] 论坛、音频等长尾接口
- [ ] 发布到 PyPI；语义化版本策略；`CHANGELOG.md`
