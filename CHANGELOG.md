# 更新日志

## [0.8.0] - 2026-11-05

### 新增

- 上下文带命中的路由：`ctx.route` 是这次命中路径背后的完整 `Route`，`ExecutionResult.handler` 是真正执行的处理器。同一个 handler 注册成多条路径时它们指向同一个函数对象，按处理器限速或埋点时用 `ctx.route.handler` 做键，不会再按命令名漏算。
- 三层本地限流：会话速率（`rate_limits`，条/分钟）、会话日配额（`daily_limits`，条/天，默认每群/每单聊 1000）、机器人总速率（`global_rate_limit`，只统计主动消息）。`RateLimitExceededError` 新增 `window`，用来区分 `minute` / `day` / `bot`；被动回复不占机器人总速率。
- 发送记录：`ClientOptions(send_hook=...)` 注入 `SendHook`，每次发送结束后回调一次 `SendRecord`（通道、目标、是否主动消息、消息 id 或异常，另带 `message` 完整出站消息，Markdown、富媒体与 keyboard 都在上面），群聊、单聊与频道都覆盖，`event.reply()` 也走同一路径；草稿模型的 `to_text()` 把消息还原成可读文本，富媒体、keyboard 等用占位符表示；切面只观察，回调异常不影响发送结果。

### 修复

- 会话存档记录建立时的 `intents`（整数，缺省 0）。换过 intents 后重启不再 Resume 旧会话，存档与当前配置不一致时丢弃并重新 Identify，新订阅立即生效；旧版本写下的存档没有该字段，按 0 处理，升级后首次启动通常会重建一次会话。

## [0.7.2] - 2026-11-04

### 修复

- 群富媒体上传的二进制分支改为 JSON 携带 base64 字符串，不再发 `multipart/form-data`，与官方接口当前行为一致

## [0.7.1] - 2026-11-04

### 新增

- 群成员事件：`GroupMemberAdd`（`GROUP_MEMBER_ADD`）与 `GroupJoinRequest`（`GROUP_JOIN_REQUEST`），后者带申请原因、邀请人、校验信息与自动审批策略；两者走 `Intents.GROUP_MEMBER`
- 入群申请接口：`api.group.join_requests()` 拉取申请列表，`review_join_request()` 同意或拒绝，另附 `approve_join_request()`/`decline_join_request()` 两个便捷方法
- 频道事件：`GuildCreate`/`GuildUpdate`/`GuildDelete` 与 `ChannelCreate`/`ChannelUpdate`/`ChannelDelete`，字段按官方事件表建模，删除事件允许只带 `id` 与 `op_user_id`
- 群与单聊开关事件：`GroupAddRobot`/`GroupDelRobot`/`GroupMsgReceive`/`GroupMsgReject`/`GroupMemberRemove`/`FriendAdd`/`FriendDel`/`C2CMsgReceive`/`C2CMsgReject`，时间戳统一解析成带时区的 `datetime`
- 频道消息与审核事件：`GuildMessageCreate`（`MESSAGE_CREATE`）、`DirectMessageCreate`（`DIRECT_MESSAGE_CREATE`）沿用频道消息的 `reply()`，另有 `MessageAuditPass`/`MessageAuditReject`
- 退出信号：`Bot.run()` 一次做完 start、等 `SIGINT`/`SIGTERM`、stop；`Bot.wait_for_exit()` 只等信号，适合自己管理适配器或 HTTP 服务器的场景。Windows 的 ProactorEventLoop 不支持 `add_signal_handler`，内部回退到 `signal.signal`。
- 文本交互标记：`qbotsdk.model.markup` 提供 `AtUser`、`AtEveryone`、`CommandEnter`、`CommandInput`、`ChannelLink`、`EmojiMarkup` 与 `PlainText` 六种节点，`TextChain.of()` 拼装、`TextChain.parse()` 反向解析，渲染出来的就是官方要求的 `<qqbot-at-user id="" />` 一类字符串
- 命令回复默认在正文前 @ 发送者：@ 标记只在 markdown 消息里生效，所以带 @ 的回复会自动按 markdown 发送，正文形如 `<qqbot-at-user id="" /> pong`；可以按 `Reply(mention=...)`、`router.command(..., mention=...)`、`Router(reply_mention=False)` 三层逐级关掉，单聊不带，频道会把正文换成 markdown 消息再带 @

### 变更

- `/permission show` 输出更详细：按场景主体与账号主体分段，列作用域、直接授予、被分配的角色，以及每个角色自身的授予与父角色

- 群成员事件（入群、退群、加群申请）要在开放平台勾选后才会下发；`Intents.GROUP_MEMBER`（`1 << 24`）没有并进 `Intents.DEFAULT`，需要显式加进 intents，避免没开权限的机器人 Identify 被断开。

### 破坏性变更

- 顶层 `qbotsdk` 只再导出与它同目录的模块：`Bot`、`ClientOptions`、异常族（`QQBotError`/`TransportError`/`APIError`/`RateLimitExceededError`/`ErrorCode`）与 `__version__`。子包内容改写子包导入，例如 `from qbotsdk.adapter import WebSocketAdapter`、`from qbotsdk.commands import Router, Reply`、`from qbotsdk.permissions import Grant, PermissionChecker`。

## [0.7.0] - 2026-10-29

### 新增

- 命令层：`Router` 支持模板路径（`server <name:int>`、`echo <text:rest>`）、`include` 组合、中间件与守卫；同一个 handler 可以多次注册，用它代替别名
- 命令树：每条事件类型一棵前缀树，字面量优先、整棵子树走不通才回溯到 `<name>`，最后才是 `<text:rest>`；停在无处理器的节点时按子项推导并回 usage
- `--` 选项：注册时 `options={"global": bool}` 声明类型，匹配阶段收集 `--name`/`--name=value`，转换后按名字绑到形参；`--` 之后不再解析，进入 `<text:rest>` 后原样打包
- 事件一等公民：命令在注册时用 `on=` 声明响应哪些事件，用户在自己的 `bot.on(...)` 回调里调用 `router.handle(event)`，同一个事件还能先做记录、过滤再决定是否交给命令层
- 执行结果：`Router.handle()` 返回 `ExecutionResult`（`Status.NOT_FOUND`/`HANDLED`/`DENIED`/`FAILED`，含 `command`/`reply`/`replied`/`error`），handler 已自行回复时不会重复发送
- 参数绑定：默认按注解把参数转成 `str`/`int`/`float`/提及 openid，`<text:rest>` 绑成 `tuple[str, ...]`；`bind_args=False` 时把原始 token 依次交给 `argv`
- 按钮层：`Router.button`/`button_prefix` 按 pydantic 载荷的 `action` 路由、字符串兜底、`ack=pre|post|none`；`on` 默认 `InteractionCreate`
- 上下文按事件类型细分：`GroupContext`/`C2CContext`/`ChannelContext`/`InteractionContext` 各自只声明本场景 `reply()` 支持的参数与回执类型，`ctx` 的类型就是参数文档；一条命令挂在多个事件上时仍可用基类 `Context`
- 权限层：`Permission`/`PermissionGroup(namespace=...)`、`Permission.wildcard()`、`Grant`/`Role` 继承、`PermissionChecker`
- 权限存储：`MemoryPermissionStorage`/`FilePermissionStorage`/`RedisPermissionStorage`，关系库按方言拆成 `SqlitePermissionStorage`/`MysqlPermissionStorage`/`PostgresPermissionStorage`（共用 `SqlPermissionStorage` 基类与 `PermissionSchema`，方言由 `SqlBackend` 枚举描述），以及 `CachedPermissionStorage`；落盘与库列统一由 pydantic 记录（`GrantList`/`NameList`/`RoleRecord`/`PendingRecord`）序列化
- 内置命令：`install_permission_commands()` 提供 `show [target]`/`grant`/`claim`/`revoke`/`whoami`/`role`，自带权限键按操作拆成 `permission.show`/`permission.grant`/`permission.revoke`/`permission.role`，看自己、`claim` 与 `whoami` 不需要权限
- 按会话场景的权限主体：`group:{群}:{成员}`、`c2c:{用户}`、`guild:{频道}:{用户}`，外加账号级 `user:{openid}`

### 变更

- 新增可选依赖 `qbotsdk[sqlite]`/`[mysql]`/`[postgres]`，基于 SQLAlchemy 2.0 async；三个存储类按方言拆分，构造时只给连接参数（SQLite 给路径，MySQL/PostgreSQL 给 host/port/user/password/database），不再接受完整 URL；引擎延迟到首次使用才创建，构造存储本身不需要驱动。
- 未知命令默认静默（同一条消息可能被多个 Router 处理），需要提示时用 `Router(reply_unknown=True)`。
- 权限存储的落盘格式改为模型序列化：Redis 的主体授予从 hash 变为一个 JSON 字符串键，SQL 的 `permissions`/`roles`/`parents` 列从分号分隔改为 JSON 数组；升级后旧数据需重新授予。
- 命令层不再绑定 `Bot`：`Router` 没有 `bind()`，`Context.api` 直接取 `event.api`。
- 测试按 src 分层为 `tests/{client,api,model,gateway,commands,permissions}/`，命令层测试拆成 `test_router.py`/`test_execution.py`/`test_callbacks.py`/`test_contexts.py`。

### 修复

- `Router.include()` 不再把子路由器的中间件与守卫并进父路由器：钩子跟着被包含的路由走，只作用于它自己的命令；执行时父级钩子在外、路由级钩子在内。之前给子路由器挂守卫会让父路由器所有命令一起被拒。
- @ 标记不再由命令层各自解析：适配器统一调用事件层的 `render_mentions_openid(strip_me=True)`，正文里的 `<@openid>` / `<@!openid>` 变成 `@openid`（保留 `@` 便于识别），`Context.mentions` 是按出现顺序去重的成员元组，`mention` 转换器与 `/permission` 的目标解析都只剥掉 `@`。之前 `/permission grant <@openid> key` 会把标记直接拼进主体键，得到 `group:{gid}:<@openid>`；`@all` 与空目标会明确报错。

### 破坏性变更

- 删除 `Bot.include()`：命令层不订阅事件，改由用户监听器显式调用 `router.handle(event)`。
- `Router.command()` 的 `on=` 必填，且一条命令只响应声明过的事件类型。
- `Router.callback`/`callback_prefix` 更名为 `Router.button`/`button_prefix`。
- 内置权限命令的 `permission.manage` 拆分为 `permission.show`/`permission.grant`/`permission.revoke`/`permission.role`；原来授 `permission.manage` 的部署改成授 `permission.*`。
- `Outcome` 更名为 `Reply`；`Router.handle()` 的返回值从 `bool` 改为 `ExecutionResult`。
- handler 返回值只接受 `Reply`（`Reply.ok()` 表示静默成功）；返回 `str` / `None` 会抛 `TypeError` 并回 `internal_error`，参数错误需 `raise UsageError(...)`。
- 模板不再支持默认值（`<name:int=3>` 直接 `ValueError`），rest 段统一写成 `<text:rest>`；可选参数用注册多条路由或 `--` 选项表达。
- 移除 `Router.command(aliases=...)`：同一个 handler 再注册一条路径即可，两条路径各自编译模板、各自校验形参与选项。
- 命令匹配不再按「具体度评分」排序，改由前缀树的字面边优先与回溯决定。

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

[0.8.0]: https://github.com/half-nothing/qbotsdk/releases/tag/v0.8.0
[0.7.2]: https://github.com/half-nothing/qbotsdk/releases/tag/v0.7.2
[0.7.1]: https://github.com/half-nothing/qbotsdk/releases/tag/v0.7.1
[0.7.0]: https://github.com/half-nothing/qbotsdk/releases/tag/v0.7.0
[0.6.0]: https://github.com/half-nothing/qbotsdk/releases/tag/v0.6.0
