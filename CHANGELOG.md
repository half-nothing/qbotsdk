# 更新日志

本项目的版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)，格式参考
[Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)。

## [未发布]

### 计划中

- 论坛 threads 与音频 actions 的接口（官方文档缺页，取证后再实现）。
- VitePress 文档站与 API 自动生成。
- PyPI 发布链路：等线上环境跑通后再接（当前版本不发布到 PyPI）。

## [0.5.0] - 2026-10-27

Phase 4 P1–P5 的补全。**未发布到 PyPI**，仅供仓库内使用与线上测试。

### 新增

- 单聊：`api/user_message.py` 的 `send_message` / `notify_input` / `recall_message` / `upload_file`；
  草稿模型 `UserMessageDraft` 支持 `msg_type` 0 文本、2 Markdown、6 输入中、7 富媒体，
  `is_wakeup` 互动召回与 `msg_id` / `event_id` 互斥。
- 单聊事件 `C2CMessageCreate`，带 `reply()`（60 分钟被动窗口、最多 4 次，自动自增 `msg_seq`）。
- 本地配额层：`module/rate_limit.py` 的 `TokenBucket` 与 `RateLimiter`，
  `ClientOptions.respect_rate_limits`（默认开）与 `rate_limits`（键 `group` / `c2c`），
  超限抛 `RateLimitExceededError`。
- 频道事件 `ChannelMessageCreate`（`reply()` 走 `channel.send_message(..., reply_to=id, event_id=id)`）。
- 互动事件 `InteractionCreate`：`InteractionType` / `InteractionCode`、`needs_response`、
  `respond(code)` → `PUT /interactions/{id}`。
- 表情表态：`api/reaction.py` 的 `add` / `remove` / `users` / `iter_users`，以及
  `model/reaction.py` 的 `Emoji` / `MessageReaction` / `ReactionUsers`。
- `HTTPClient.put`；`HTTPClient.options` 只读属性。

### 变更

- `Intents.DEFAULT` 追加 `INTERACTION`：不带上这个 intent 收不到按钮与快捷菜单回调。
  自定义 `intents` 的项目需要自行确认是否包含它。
- `Message` 补齐 `edited_timestamp` / `attachments` / `mentions` / `member` / `ark` /
  `seq` / `seq_in_channel` / `message_reference` 八个可选字段。
- `Member` 的 `nick` / `deaf` / `mute` / `pending` 改为可缺省：消息对象里的 `member`
  只带部分字段。
- `GroupMessageReceipt` 与 `UserMessageReceipt` 改为共用 `MessageReceipt` 基类。

## [0.4.0] - 2026-10-27

Phase 3：事件接入。

### 新增

- WebSocket 网关：`gateway/payload.py`（`OpCode`、`Intents`、关闭码表、`Frame` 系列模型）、
  `gateway/session.py`、`gateway/connection.py`（Hello / Identify / READY / 心跳 / Resume / 退避重连）。
- 分发层：`gateway/dispatcher.py` 基于 `async-event-bus` 的薄门面，支持 `bot.on(...)`、
  `bot.on_unknown(...)`、按消息 `id` 的去重窗口。
- 事件模型：`ReadyEvent`、`ResumedEvent`、`GroupAtMessageCreate`、`UnknownEvent`，
  以及群聊事件上的 `reply()`（5 分钟窗口、最多 5 次）。
- Webhook：`gateway/webhook.py` 的 op 13 签名、请求验签、事件解析；
  `gateway/webhook_server.py` 的开箱即用服务器（快速 ACK、TLS 终结、优雅关闭）。
- `Bot.start()` / `Bot.stop()` 与 `Bot.api` / `Bot.dispatcher` 属性。

### 变更

- `User` 拆成 `User`（只有 `id`）、`GuildUser`、`GroupUser`、`C2CUser`，
  避免一个类里堆满各场景才有的空字段。

## [0.3.0] - 2026-10-26

Phase 2：消息发送与撤回。

### 新增

- 频道消息：`channel.send_message`（文本 / Markdown / `embed` / `ark` / 引用 / 图片 URL 转存 /
  `file_image` multipart 直传）与 `channel.recall_message`。
- 群消息：`group.send_message`（文本 / Markdown / 富媒体 / 键盘 / 引用）与 `group.recall_message`。
- 群富媒体上传 `group.upload_file`：`url` 与 `file_data`（5 MB 以内）两种方式。
- 消息模型：`Message`、`GroupMessageReceipt`、`MediaInfo`、`UploadedFile`、
  键盘模型（`Keyboard` / `Button` 等）与请求侧草稿模型。
- `HTTPClient` 支持 `multipart/form-data`；`ClientOptions.retry_post`（默认关）。

## [0.2.0] - 2026-10-26

Phase 1：REST 架构定型。

### 新增

- 错误体系：`QQBotError`、`TransportError`、`APIError`、`ErrorCode`、`error_code_of`。
- `ClientOptions`：超时、重试次数、退避参数、`Retry-After` 上限。
- `HTTPClient` 重写：超时、429 按 `Retry-After` 重试、5xx 与网络异常的幂等重试、
  401 刷新凭证后重试一次、204 与非 JSON 包体容错。
- 凭证管理：`_refresh_at` / `_hard_expire_at` 两个时间点，刷新失败时回退旧凭证。
- 只读资源：`user.me` / `user.guilds`、`guild.get` / `channels` / `members` / `roles`、
  `channel.get`、`group.get` / `bot_state` / `members` / `member` / `mute_setting`。
- 分页：`iter_guilds`、`iter_members`、`group.iter_members`（游标推进、去重、防死循环）。
- 模型：`Guild`、`Channel`、`Member`、`Role`、`User`、`Group`、`GroupMember` 等。

### 修复

- `HTTPClient.get` / `post` 漏 `await`，`bot.get_me()` 会把协程对象塞给 pydantic。
- 凭证接口返回 HTTP 200 + `err_code` 时被直接送进模型，抛 `ValidationError` 而不是 `APIError`。

## [0.1.0] - 2025

初始骨架：`Bot` 门面、凭证缓存、`HTTPClient` 与 `User` 模型，只有 `get_me` 一个接口。
