# Phase 3 设计：事件接入（v0.4.0）

## 1. 范围与非目标

### 1.1 本期范围

把 SDK 从「只能主动调用」推进到「能收到消息并回应」：

| 能力 | 说明 | 依赖 |
| --- | --- | --- |
| 网关连接 | WebSocket 连接 `wss://api.bot.qq.com/websocket/`，Identify / 心跳 / Resume | `aiohttp` |
| 事件模型 | `GatewayPayload`、`ReadyEvent`、`ResumedEvent`、`GroupAtMessageCreate` | `pydantic` |
| 事件分发 | 按事件类型注册异步处理器，异常隔离，不阻塞心跳 | 标准库 `asyncio` |
| 被动回复 | 事件对象带 `reply()`，复用 Phase 2 的发送接口，自动带 `msg_id` | Phase 2 |
| Webhook 校验 | `op 13` 地址验证签名、`X-Signature-Ed25519` 请求验签 | `cryptography` |
| Webhook 服务 | 默认服务器 `WebhookServer`：自带 TLS 终结（`certfile`/`keyfile` 或 `ssl_context`）与启停；也可只取函数接自己的服务器 | `aiohttp` |

### 1.2 非目标

- 不做自动分片。`shard` 固定 `[0, 1]`，官方默认单连接即可，分片留给后续版本。
- 不做「只能二选一」的绑定：Webhook 既提供「验证 + 解析」的纯函数，也提供默认服务器 `WebhookServer`，用户自选（§7.4）。默认服务器**自带 TLS 终结与证书加载**，开箱即用；不做证书签发、Let's Encrypt 自动续期、HTTP/2 与反向代理配置。
- 不做 `AT_MESSAGE_CREATE` 与 `C2C_MESSAGE_CREATE` 的强类型模型，直到拿到官方响应示例。见 §5.4。
- 不做 INTERACTION_CREATE、FORUMS_EVENT、AUDIO_ACTION、MESSAGE_AUDIT。
- 不做事件持久化、不做跨进程分发、不做进程内重试队列。

## 2. 现状与差距

v0.3.0 的全部能力都是「客户端主动调用」：

- `src/qqbot/module/http_client.py` 只有请求-响应，没有长连接。
- 没有 `intents`、`session_id`、`seq` 这些概念。
- `src/qqbot/api/message.py` 的 `reply()` 目前抛 `NotImplementedError("message.reply is available from the event layer in phase 3")`，本期要兑现它。
- 依赖里没有 WebSocket 客户端（`aiohttp` 自带 `ClientSession.ws_connect`，不需要新依赖）与 Ed25519 实现（需要新增）。

差距按层列：

| 层 | 现状 | Phase 3 需要 |
| --- | --- | --- |
| 传输 | `HTTPClient` 单次请求 | 长连接 + 心跳 + 断线重连 |
| 模型 | REST 响应模型 | 网关 payload 与事件模型 |
| 资源 | `ApiClient` 四个域 | `event.reply()` 反向调用 `ApiClient` |
| 分发 | 无 | 处理器注册表 |

## 3. 分层与契约

```text
bot.py  ──  Bot（门面）
             ├─ gateway/            ← 本期新增
             │    ├─ payload.py     opcode、GatewayPayload
             │    ├─ session.py     连接状态：session_id / seq / 是否可 resume
             │    ├─ connection.py  WebSocket 生命周期、心跳、重连
             │    └─ dispatcher.py  事件到处理器的分派
             ├─ model/              事件模型（复用 QQModel）
             ├─ api/                主动调用（不变）
             └─ module/             HTTPClient 与 TokenManager（不变）
```

契约：

- `gateway/` 只能依赖 `model/`、`module/`、`options.py`，禁止 import `api/`；`event.reply()` 由 `Bot` 注入 `ApiClient` 实现。
- 处理器签名统一 `async def handler(event) -> None`，不接受位置参数。
- 分发层不吞掉异常以外的控制流：`asyncio.CancelledError` 必须原样抛出。

## 4. 网关连接层

### 4.1 连接流程

1. `GET /gateway/bot` 拿到 `url`、`shards`、`session_start_limit`（`total` / `remaining` / `reset_after` / `max_concurrency`）。同一 AppID 的 `remaining` 是硬上限，超了连不上。
2. `session.ws_connect(url)`，等服务端下发 `op 10 Hello`，取出 `heartbeat_interval`（毫秒）。
3. 发 `op 2 Identify`：

```python
await ws.send_str(
    IdentifyFrame(
        d=IdentifyData(
            token=f"QQBot {access_token}",
            intents=intents,
            shard=[0, 1],
            properties={"$os": "linux", "$browser": "qqbot-sdk", "$device": "qqbot-sdk"},
        )
    ).to_json()
)
```

进出网关的每一帧都由 `gateway/payload.py` 的 pydantic 模型承载：解析用 `GatewayPayload.model_validate_json(text)`，发送用 `Frame.to_json()`（即 `model_dump_json()`），不手工拼 dict，也不 `json.loads` 之后再 `model_validate`。`HelloFrame`、`IdentifyFrame`、`ResumeFrame`、`HeartbeatFrame` 分别对应 `op 10` / `2` / `6` / `1`。

4. 收到 `op 0` 且 `t == "READY"` 才算连上，从 `d` 里取 `session_id`、`user`、`shard`，同时记下 `s` 作为后续 `seq`。

`properties` 官方注明无实际作用，但仍要带，缺字段可能被拒。

### 4.2 心跳与 seq

- 每 `heartbeat_interval` 毫秒发一次 `op 1`，`d` 是「最近一次收到的 `s`」，一次都没收到时发 `null`。
- 服务端回 `op 11`。连续两个周期没回 `op 11` 视为连接已死，直接 close 后重连。
- 心跳用独立 task，不占分发层的协程；处理器卡住不影响心跳。

### 4.3 Resume 与重连

| 场景 | 动作 |
| --- | --- |
| 网络断开、`op 7 Reconnect`、`4009`、`4008` | 发 `op 6 Resume`：`{token, session_id, seq}` |
| Resume 成功 | 收到 `t == "RESUMED"`，继续用原 `session_id`，不重建处理器 |
| `4006`、`4007`、`4900`～`4913` | `session_id` 作废，重新 Identify |
| `4001`、`4002`、`4010`、`4011`、`4012`、`4013`、`4014`、`4914`、`4915` | 不重连，抛 `GatewayError`，让用户修配置或等权限 |

重连退避：`min(backoff_base * 2 ** (attempt - 1), backoff_max)`，默认 `0.5s` 起、上限 `8s`，加 0～25% 抖动。退避参数复用 `ClientOptions`，不新增配置项。

### 4.4 关闭码

| 码 | 含义 | 处理 |
| --- | --- | --- |
| 4006 | 无效 session id | 重新 Identify |
| 4007 | `seq` 错误 | 重新 Identify |
| 4008 | 发送过快 | Resume |
| 4009 | 会话已过期 | Resume 失败则 Identify |
| 4010 | 无效 shard | 抛错，不重连 |
| 4011 | guild 过多需分片 | 抛错，提示分片 |
| 4013 | 无效 intent | 抛错，提示权限 |
| 4014 | intent 无权限 | 抛错，提示申请 |
| 4914 | 已下架，仅沙箱 | 抛错，不重连 |
| 4915 | 已封禁 | 抛错，不重连 |

### 4.5 intents

| 常量 | 位移 | 用途 |
| --- | --- | --- |
| `GUILDS` | `1 << 0` | 频道增删改、频道信息 |
| `GUILD_MEMBERS` | `1 << 1` | 成员增删改 |
| `GUILD_MESSAGES` | `1 << 9` | 私域消息（需私域机器人） |
| `PUBLIC_GUILD_MESSAGES` | `1 << 30` | 公域频道 @ 消息 |
| `GROUP_AND_C2C_EVENT` | `1 << 25` | 群聊与单聊 @ 消息 |
| `INTERACTION` | `1 << 26` | 按钮回调（本期不用） |

默认值取「基础事件 + 群聊单聊」：`GUILDS | PUBLIC_GUILD_MESSAGES | GROUP_AND_C2C_EVENT`。传了没权限的 intent 会被直接断开（`4013`/`4014`），所以不默认开 `GUILD_MEMBERS`。

## 5. 事件模型

### 5.1 通用 payload

```python
class GatewayPayload(QQModel):
    id: str | None = None
    op: OpCode
    d: Any = None
    s: int | None = None
    t: str | None = None
```

`OpCode` 用 `IntEnum` 收全表：`DISPATCH=0`、`HEARTBEAT=1`、`IDENTIFY=2`、`RESUME=6`、`RECONNECT=7`、`INVALID_SESSION=9`、`HELLO=10`、`HEARTBEAT_ACK=11`、`HTTP_CALLBACK_ACK=12`、`CALLBACK_VALIDATION=13`。

### 5.2 事件类型

`t` 是字符串，本期只映射四类：

| `t` | 模型 | 备注 |
| --- | --- | --- |
| `READY` | `ReadyEvent` | 连接建立 |
| `RESUMED` | `ResumedEvent` | 恢复成功 |
| `GROUP_AT_MESSAGE_CREATE` | `GroupAtMessageCreate` | 群聊里 @ 机器人 |
| 其它 | `UnknownEvent`（`t` + 原始 `d`） | 不报错，交给「通配处理器」 |

未知事件降级成 `UnknownEvent` 而不是抛错，否则一上线遇到 `GUILD_CREATE` 就断连。

### 5.3 群聊消息事件

官方字段（`GROUP_AT_MESSAGE_CREATE`，Intent `1 << 25`）：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | `str` | 消息 ID，被动回复与撤回要用 |
| `author` | `User` | `member_openid` 有值 |
| `content` | `str` | 已去掉 @机器人 前缀 |
| `group_openid` | `str` | 群标识 |
| `timestamp` | `datetime` | RFC3339 |
| `message_scene` | `MessageScene` | `source` + `ext`（`msg_idx=` / `auth_token=` / `ref_msg_idx=`） |
| `attachments` | `list[Attachment]` | `url` / `filename` / `size` / `content_type` / `voice_wav_url` / `asr_refer_text` |
| `mentions` | `list[User]` | 被 @ 的用户 |
| `msg_elements` | `list[MessageElement]` | 卡片/聊天记录/引用等复合消息 |

`message_scene.ext` 官方是 `list[str]` 的 `k=v` 形式，模型在解析时按第一个等号切分成 `dict[str, str]`，调用方直接 `event.message_scene.ext["msg_idx"]` 取值；不带等号的条目丢弃，解析在 `field_validator(mode="before")` 里完成。

### 5.4 待取证的两个事件

`AT_MESSAGE_CREATE`（频道 @ 消息）与 `C2C_MESSAGE_CREATE`（单聊）的事件页在 wiki 上会跳到「启动接入」页，抓不到字段表。按 Phase 1 §6.0 的准则，**没有官方示例就不建模型**：

- 本期这两个事件走 `UnknownEvent`，用户可以用 `bot.on_unknown()` 拿到 `t` 与原始 `d`。
- 实现前必须补一次取证：从官方文档抓到响应示例，逐字存进 `tests/data/`，再补模型。

### 5.5 数据来源准则

沿用 Phase 1 §6.0：

- 字段必须有官方表格或示例出处，快照逐字拷贝。
- 示例里出现、表格里没有的字段也收，标 `| None = None`。
- 无出处的字段一律不进模型，宁可让用户读 `UnknownEvent.data`。

### 5.6 用户对象：按场景拆分

同一个「用户」在官方文档里有三套结构：频道消息作者、频道成员列表、群聊事件作者（`member_openid`）。把它们塞进一个类就会退化成「一半字段永远为空」的模型，调用方也得猜哪个字段才是这次的身份标识。

按场景拆成子类，基类只留所有场景都存在的 `id`：

| 类 | 场景 | 必填 | 场景相关字段 |
| --- | --- | --- | --- |
| `User` | 基类，不直接用于解析 | `id` | 无；`openid` 返回 `None` |
| `GuildUser` | 频道消息作者、成员列表的 `user`、`READY` 的机器人自身 | `id`、`username` | `avatar`、`bot`、`union_openid`、`union_user_account`、`public_flags`、`system` |
| `GroupUser` | 群聊事件 `author`、`mentions[]` | `id`、`member_openid` | `union_openid`、`user_openid`、`member_role` |

三条规则：

- **必填字段不给假默认**：`username`、`member_openid` 缺失就是接口变了，直接 `ValidationError`，不补空串掩盖。
- **场景不保证出现的字段一律 `| None = None`**：例如 `READY` 的示例里没有 `avatar`，成员列表示例里有。
- **调用方拿到的是子类**：`Message.author` / `Member.user` / `ReadyEvent.user` 是 `GuildUser`，`GroupAtMessageCreate.author` 是 `GroupUser`；跨场景定位人用 `user.openid`，它在 `GroupUser` 上返回 `member_openid`，在其它场景返回 `None`。

## 6. 分发层

### 6.1 注册（事件总线用 `async-event-bus`）

```python
bot = Bot(app_id=..., client_secret=...)


@bot.on(GroupAtMessageCreate)
async def on_group_at(ctx: EventContext[GroupAtMessageCreate]) -> None:
    await ctx.event.reply("收到: " + ctx.event.content)
```

- 事件总线用 `async-event-bus` 1.0.0（§14 D7），`Dispatcher` 只做三件事：帧 → 事件模型、按消息 `id` 去重、把事件 `emit` 进总线；订阅表、并发与异常策略都交给总线。
- 事件模型统一继承 `EventModel`（`QQModel` + `async_event_bus.AbstractEvent`），总线按 `type(event)` 精确匹配。**精确派发是设计意图**：事件类型就是订阅键，不做基类兜底，`@bot.on(GroupAtMessageCreate)` 只收这一类；想收多类就分别注册。
- 类型上不出现裸 `Any`：`Dispatcher` 里的总线是 `EventBus[EventContext[EventModel], None]`，每个处理器按注册的事件类型拿到 `EventContext[E]`（总线内部统一按 `EventContext[EventModel]` 存），只有 `QQModel`/`UnknownEvent.data` 这类真正「结构未知的 JSON」才保留 `Any`。
- **事件不依赖 `api/`**：`EventModel` 用两个 `Protocol` 描述它需要的接口面 —— `GroupSender`（只有 `send_message` 一个方法）与 `ApiProtocol`（只有 `group` 属性，声明成 `@property` 才能让普通属性满足、且不用 import `ApiClient`）。`ApiClient` 结构上就满足它们，不需要适配器；一旦 `GroupResource.send_message` 的签名漂移，`Dispatcher` 里 `event.bind(self._api)` 会在 mypy 报错。
- **`api` 是私有属性，不是字段**：`_api: ApiProtocol | None = PrivateAttr(default=None)`，配 `@property api` 只读暴露、`bind()` 供 `Dispatcher` 写入。私有属性不进字段校验、不进 `model_dump()`、不进 JSON Schema，所以既不需要 `arbitrary_types_allowed` 也不需要 `SkipJsonSchema`，更不需要 `model_rebuild`。
- **不做二次包装**：`bot.on(EventType)` 直接把处理器转给 `bus.on(...)`，处理器收到的就是总线的 `EventContext[E]`，事件本体在 `ctx.event`；只收协程函数，传普通函数抛 `TypeError`（§14 D3），这是门面唯一的额外校验。
- **事件不是 frozen 的**：与其它响应模型不同，`EventModel` 关掉了 frozen。`api` 在解析之后由 `Dispatcher.handle()` 注入（私有属性，不进序列化），`reply()` 的 `msg_seq` 也在事件上累计。理由：回复能力属于「这条消息」，挂在事件上用户一眼就能看到能不能回复——有 `reply()` 就是能，没有就是不能，不用再到别的对象上查能力表。代价是事件不再只读，跨处理器共享时要当成可变对象对待。
- `bot.on_unknown()` 等价于 `bot.on(UnknownEvent)`。
- 处理器用 `asyncio.create_task(self._bus.emit(event))` 跑，分发层不 `await`，避免慢处理器阻塞读循环；`set` 持有 task 引用防 GC。
- 并发语义：同步回调按 `weight` 降序先跑；异步回调由总线 `asyncio.gather` 并发跑，`max_concurrent_tasks`（默认 16）限流。**同一事件的多个异步处理器不保证顺序**，需要严格顺序就合并成一个处理器。

### 6.2 异常隔离

总线配 `ExceptionStrategy.IGNORE`：处理器抛异常只记日志，不影响同一事件的其它处理器，也不影响心跳与读循环；`bot.on()` 的包装层不额外 catch，唯一的例外是 `asyncio.CancelledError` 原样向上传播。

### 6.3 `event.reply()`

`GroupAtMessageCreate.reply(content, *, markdown=None, media=None, keyboard=None, msg_seq=None)` 的语义：

- 自动带 `msg_id=event.id`，`msg_seq` 不传时由 SDK 自增（每条事件从 1 开始），解决「同一 `msg_id` 重发被拒（`40054005`）」；显式传 `msg_seq` 时以调用方为准。
- 内部调用 `ApiClient.group.send_message(...)`，群 openid 从事件里取。
- **只在支持回复的事件类型上定义**：有没有 `reply()` 就是能不能回复，不需要能力查询接口；`ReadyEvent` 之类没有这个方法，IDE 与 mypy 直接报错。
- `api` 由 `Dispatcher.handle()` 在解析后注入；手动 `model_validate` 出来的事件没有它，`reply()` 抛 `ValueError("reply() needs an event dispatched by Bot; ...")`，不会静默失败。
- 频道消息事件同样提供 `reply()`，等 §5.4 取证后再实现（`AT_MESSAGE_CREATE` 目前落到 `UnknownEvent`）。

### 6.3.1 接线

`Bot.on(...)` / `Bot.on_unknown()` 直接转发给 `Dispatcher`，不额外包一层；
`Bot.start()` 建 `GatewayConnection` 与 `Dispatcher.run()` 两个后台任务，`Bot.stop()` 先 `connection.close()` 再取消任务并 `dispatcher.close()`（订阅随之清空，重新 `start()` 要重新注册）。
`api/message.py` 的 `reply(group_openid, *, msg_id=..., ...)` 是同一实现的非事件入口，资源层在 `reply_to` 有值时同样补 `msg_seq=1`。

### 6.4 去重

官方注明「相同 `msg_id` 可能重复推送」，且事件 payload 里没有 `msg_seq` 可用于去重。所以分发层维护一个有界集合：最近 N 条（默认 512）消息 `id`，命中即跳过。可配置关闭。

## 7. Webhook 方式

### 7.1 地址验证（`op 13`）

平台先推一条 `op 13`：

```json
{"op": 13, "d": {"plain_token": "...", "event_ts": "..."}}
```

应答 JSON：

```json
{"plain_token": "...", "signature": "<hex>"}
```

签名算法：`ed25519_sign(seed=botSecret 反复重复到 32 字节, message=event_ts + plain_token)`。SDK 提供 `build_validation_response(bot_secret, plain_token, event_ts) -> dict`。

官方给了一组完整的验证示例，直接当测试向量（`tests/test_webhook.py` 逐字用）：

| 项 | 值 |
| --- | --- |
| AppID | `11111111` |
| botSecret | `DG5g3B4j9X2KOErG` |
| `plain_token` | `Arq0D5A61EgUu4OxUvOp` |
| `event_ts` | `1725442341` |
| 期望 `signature` | `87befc99c42c651b3aac0278e71ada338433ae26fcb24307bdc5ad38c1adc2d01bcfcadc0842edac85e85205028a1132afe09280305f13aa6909ffc2d652c706` |

注意 seed 的生成方式是 `strings.Repeat(seed, 2)` 直到长度 ≥ 32 再截断，不是简单补零；`DG5g3B4j9X2KOErG`（16 字节）重复一次正好 32 字节，所以这组向量只能验证「刚好整除」的分支，函数实现要按循环重复写，不能写死 `secret * 2`。

### 7.2 请求验签

- 头：`X-Signature-Ed25519`（hex，64 字节）、`X-Signature-Timestamp`。
- 签名体：`timestamp + body`（UTF-8 原始字节，不要重新序列化 JSON）。
- 提供 `verify_webhook_signature(bot_secret, signature, timestamp, body) -> bool`，以及 `parse_webhook_event(body) -> 事件对象`。

### 7.3 op 12 应答

回调处理完要回 `op 12` HTTP Callback ACK，`d` 为空对象。SDK 提供 `build_ack_payload()`。

### 7.4 默认服务器（开箱即用，含 TLS）

函数层之外，再提供一个**开箱即用**的默认服务器：自带 TLS 终结与证书加载，用户填完证书路径就能直接对接平台，不需要再拉一个 nginx。不想用的人仍然只取 §7.1–§7.3 的函数，接自己的 FastAPI/Flask。

```python
server = WebhookServer(
    bot,
    bot_secret="...",
    host="0.0.0.0",
    port=8443,
    path="/qqbot",
    certfile="certs/fullchain.pem",  # 与 keyfile 成对出现
    keyfile="certs/privkey.pem",
)
await server.start()  # 内部 TCPSite，带 ssl_context 时即为 https
await server.close()
```

职责边界：

| 由服务器做 | 由 SDK 函数层做 | 不由 SDK 做 |
| --- | --- | --- |
| 建 `aiohttp.web.Application`、注册 POST 路由、启停生命周期；按 `certfile`/`keyfile` 或现成 `ssl_context` 启 TLS | 地址验证应答、请求验签、payload 解析、`op 12` ACK | 证书签发、Let's Encrypt 自动续期、HTTP/2、反向代理配置、鉴权白名单 |

实现要点：

- TLS 三种用法：`certfile` + `keyfile` 交给 `ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)` 并 `load_cert_chain`；或直接传现成的 `ssl_context`；都不传就是明文 HTTP，此时若端口是 443/8443 打一条 `logger.warning`（大概率忘了配证书）。
- 只给其中一个（只有 `certfile` 或只有 `keyfile`）直接 `ValueError("certfile and keyfile must be provided together")`，这种配置错误必须尽早暴露。
- `ssl_context` 与 `certfile`/`keyfile` 同时传也 `ValueError`，避免「到底用了哪个」的歧义。
- 证书热更新不在本期：换证书需要 `await server.close()` 后重新 `start()`，文档里写明。
- `aiohttp` 服务端只有 HTTP/1.1，够用（平台就是 POST JSON）；需要 HTTP/2 或自动续期的人走反向代理 + 函数模式。
- 端口：官方原文是「目前回调地址**允许配置**的端口号为：80、443、8080、8443」。这是管理端配置回调地址时的限制，不是服务器本身的技术限制——服务放在反向代理后面时，`WebhookServer` 监听 9000、nginx 对外 443，完全合法。所以**不做 `ValueError` 拦截**：不在四个端口里只打一条 `logger.warning`，说明「若平台直连本端口会被拒，走反向代理则忽略」。
- 端口 0 留给测试（让操作系统分配空闲端口），靠 `asyncio` 拿到实际端口，避免测试里抢端口。
- 走反向代理时，必须保证请求体与 `X-Signature-Ed25519` / `X-Signature-Timestamp` 两个头原样透传：代理若改写 body（gzip 重压、转码、重排 JSON）会导致验签失败，文档里提示用户代理层关闭改写。
- 第一件事是验签：`verify_webhook_signature(...)` 失败返回 `401`，不解析 body。
- body 先按原始字节读（`await request.read()`），**不能** 先 `request.json()` 再重新序列化，签名体是 `timestamp + body`，重排 JSON 会验签失败。
- `op 13` 直接回 §7.1 的应答，不进分发层。
- 普通事件：先回 `200 {op:12, d:{}}` 再异步分发。官方要求快速 Ack，处理慢会导致平台重推。
- 响应头带 `User-Agent: QQBot-Callback` 之外不需要额外头；返回体统一 UTF-8 JSON。
- 同一个 `Bot` 可以同时跑 Gateway 与 Webhook（官方支持两种方式并存），但推荐二选一，否则事件会收两遍（`dedupe_size` 只挡 `id` 相同的重复推送，不能跨通道去重）。

## 8. 配置

不新增顶层配置类，扩 `ClientOptions` 两个字段：

| 字段 | 默认 | 说明 |
| --- | --- | --- |
| `intents` | `GUILDS \| PUBLIC_GUILD_MESSAGES \| GROUP_AND_C2C_EVENT` | 连接时提交 |
| `dedupe_size` | `512` | 去重窗口，`0` 关闭 |

Webhook 的 `bot_secret` 走构造参数（`Bot(..., bot_secret=...)`），不放进 `ClientOptions`，因为它只给签名用，与 REST 无关。

默认服务器的参数全在自己的构造签名上，不进 `ClientOptions`：

| 参数 | 默认 | 说明 |
| --- | --- | --- |
| `host` | `"0.0.0.0"` | 监听地址 |
| `port` | `8443` | 端口；`0` 表示由系统分配（测试用），非 80/443/8080/8443 只告警 |
| `path` | `"/qqbot"` | 回调路径，需与平台配置一致 |
| `certfile` | `None` | PEM 证书链，必须与 `keyfile` 成对出现 |
| `keyfile` | `None` | PEM 私钥 |
| `ssl_context` | `None` | 现成的 `SSLContext`，与 `certfile`/`keyfile` 互斥 |

都不传 TLS 参数时是明文 HTTP，端口为 443/8443 时打 warning。三种配置错误（只给一个、两者同传、`ssl_context` 与 `certfile` 同传）都在构造时 `ValueError`，不等启动。

## 9. 目录结构（新增部分）

```text
src/qqbot/
  gateway/
    __init__.py
    payload.py        OpCode、GatewayPayload、intents 常量
    session.py        SessionState（session_id / seq / can_resume）
    connection.py     GatewayConnection：连接、心跳、重连
    dispatcher.py     Dispatcher：总线的薄门面（注册校验、去重、注入 api）
    webhook.py        op 13 签名、请求验签、parse（纯函数，不依赖 aiohttp 路由）
    webhook_server.py WebhookServer：开箱即用服务器（含 TLS 终结）
  model/
    event.py          ReadyEvent / ResumedEvent / GroupAtMessageCreate / UnknownEvent
    scene.py          MessageScene / Attachment / MessageElement
tests/
  test_gateway_payload.py
  test_gateway_connection.py     假 WebSocket 服务端
  test_dispatcher.py
  test_webhook.py                签名、验签、parse（纯函数）
  test_webhook_server.py         起 aiohttp 服务打真实 HTTP
  test_event_reply.py           Bot.on / event.reply / api.message.reply / start-stop
  data/
    gateway_hello.json
    gateway_ready.json
    gateway_resumed.json
    group_at_message_create.json
```

## 10. 测试策略

- 假网关：`tests/support.py` 加 `FakeGateway`，用 `aiohttp.web` 的 `WebSocketResponse` 起本地服务端，按脚本推送 `op 10` → 校验 `op 2` → 推 `READY`，可以断言 SDK 发的字节流。
- 心跳：把 `heartbeat_interval` 设成 50ms，测试里等 150ms 断言发了 2～3 次 `op 1`；不回 `op 11` 时断言触发了重连。
- Resume：先正常连接，再让服务端发 `4009`，断言 SDK 发的是 `op 6` 且带原 `session_id` 与 `seq`。
- 分发：注册两个处理器，一个抛异常，断言另一个仍执行且异常被记录。
- `reply()`：用已有的 `MockServer` 断言请求体带 `msg_id`、`msg_seq` 从 1 递增。
- Webhook 函数层：用固定 seed 与明文，断言签名 hex 与官方示例一致（取自文档示例）；错误签名、被篡改 body、缺头都要判无效。
- Webhook 服务器：`WebhookServer` 传 `port=0` 让系统分配空闲端口（见 §7.4），用 `aiohttp.ClientSession` 打真实 HTTP，断言 `op 13` 回签名、坏签名回 401、正常事件回 `op 12` 且处理器被调用；另加一条「端口不在 80/443/8080/8443 时只告警不抛错」的用例，用 `caplog` 断言 warning 存在。
- TLS：测试里用 `cryptography` 现场生成一张自签证书写进 `tmp_path`，`WebhookServer(certfile=..., keyfile=...)` 启动后用 `TCPConnector(ssl=False)` 连 `https://127.0.0.1:{port}` 走一遍 `op 13`，证明 TLS 链路通（自签证书只测链路，不测信任链）；三条配置错误（只给一个、两者同传、`ssl_context` 与 `certfile` 同传）各一条 `pytest.raises(ValueError)`。
- 门禁与 Phase 1/2 一致：`ruff check`、`ruff format --check`、`mypy`、`pytest`。

## 11. 切片

| 切片 | 内容 | 验收 | 依赖 |
| --- | --- | --- | --- |
| T1 | `gateway/payload.py` + `model/event.py`（含 `UnknownEvent`）+ intents 常量 + 用户对象按场景拆分 | `test_gateway_payload.py` 全绿 | 无（2026-10-26 完成） |
| T2 | `gateway/session.py` + `gateway/connection.py`：连接、Hello、Identify、READY、心跳、Resume、关闭码驱动的重连 | `test_gateway_connection.py` 全绿（5 用例） | T1（2026-10-27 完成） |
| T3 | Resume、关闭码表、退避重连 | 关闭码与 Resume 用例全绿 | T2（2026-10-27 与 T2 一并完成） |
| T4 | `dispatcher.py`（基于 `async-event-bus`）+ `bot.on()` + `event.reply()` | 分发与 reply 用例全绿 | T1、T3（2026-10-27 完成） |
| T5 | `webhook.py`：op 13 签名、验签、parse（纯函数） | `test_webhook.py` 全绿（10 用例，含官方向量） | T1（2026-10-27 完成） |
| T6 | `webhook_server.py`：开箱即用服务器（TLS 三种配置 + 明文告警）、端口告警、快速 ACK、优雅关闭 | `test_webhook_server.py` 全绿 | T5 |

顺序：T1 → T2 → T3 → T4 → T5 → T6，T5/T6 可与 T2/T3 并行。

进度：T1（2026-10-27）、T2 + T3（2026-10-27）、T4（2026-10-27，`bot.on()` 与 `event.reply()` 接线完成）、T5（2026-10-27）已完成；门禁 `129 passed` / `mypy` 57 files / `ruff format --check` 63 files。
下一步 T6（`WebhookServer` + 示例）。

## 12. 版本与兼容

- 版本 `0.4.0`，Phase 2 的公开接口全部不变。
- 依赖新增 `cryptography`（Ed25519 签名与验签）与 `async-event-bus`（事件总线）；`aiohttp` 已在依赖树里，默认服务器不引入新依赖；TLS 用标准库 `ssl`（`SSLContext` + `load_cert_chain`），也不需要新依赖。
- `Bot` 构造新增两个可选参数：`bot_secret: str | None = None`、`intents: int | None = None`。
- `bot.start()` / `bot.close()` 成为推荐用法；`Bot.get_me()` 继续保留（已标弃用）。
- `api/message.py` 的 `reply()` 从 `NotImplementedError` 改成真实实现，因为依赖 `event.reply()` 提供的 `msg_id`/`msg_seq`；无事件上下文的调用改为抛 `ValueError("reply() needs msg_id; use the event layer or send_message()")`。

## 13. 引用来源

- 网关连接：<https://bot.q.qq.com/wiki/develop/api-v2/dev-prepare/interface-framework/event-emit.html>
- 通用 payload 与 opcode：<https://bot.q.qq.com/wiki/develop/api-v2/dev-prepare/interface-framework/event-emit.html>
- 群聊 @ 消息事件：<https://bot.q.qq.com/wiki/develop/api-v2/server-inter/message/event/group_at_message_create.html>
- Webhook：<https://bot.q.qq.com/wiki/develop/api-v2/dev-prepare/interface-framework/event-webhook.html>
- 错误码：<https://bot.q.qq.com/wiki/develop/api-v2/dev-prepare/interface-framework/error-code.html>

## 14. 已拍板（2026-10-26）

| 编号 | 问题 | 结论 |
| --- | --- | --- |
| D1 | Ed25519 依赖选 `PyNaCl` 还是 `cryptography` | 已定：`cryptography`。理由：用本 SDK 的项目大概率已经因为别的依赖装了它，等于零增量；多装一个只做 NaCl 的原生库反而增加装包风险。对比记录见 §14.1 |
| D2 | webhook 是否内建服务器 | 已定：默认服务器 `WebhookServer` 要开箱即用，自带 TLS 终结与证书加载（`certfile`/`keyfile` 或 `ssl_context`），用户填证书路径即可对接平台；同时保留 `gateway/webhook.py` 的纯函数给想接 FastAPI/Flask 或自己终结 TLS 的人（§7.4） |
| D3 | 处理器是否支持同步函数 | 已定：不支持，只收 `async def`，注册时检测到非协程直接 `TypeError` |
| D4 | 默认 intents 是否带 `GUILD_MEMBERS` | 已定：不带，未申请权限时会直接断连 |
| D5 | `AT_MESSAGE_CREATE` / `C2C_MESSAGE_CREATE` 是否本期补齐 | 已定：本期只做 `UnknownEvent`，实现前先取证 |
| D6 | 用户对象一个类还是按场景拆 | 已定：按场景拆成 `User` / `GuildUser` / `GroupUser`，基类只有 `id`，跨场景用 `openid` 属性（§5.6） |
| D7 | 事件总线自研还是用现成库 | 已定：用 `async-event-bus` 1.0.0（用户指定）。不自研调度与并发控制；`Dispatcher` 只保留「帧 → 事件 → 去重 → emit」四步，处理器异常走 `ExceptionStrategy.IGNORE`（§6.1、§6.2） |

### 14.1 D1 的对比记录

| 维度 | `PyNaCl` | `cryptography` |
| --- | --- | --- |
| 底层 | libsodium 绑定，wheel 里自带 libsodium | OpenSSL 绑定（Rust 实现），wheel 里自带 |
| 安装体积 | win_amd64 wheel 约 1.4 MB | win_amd64 wheel 约 3.5 MB |
| API（本场景） | `SigningKey(seed).sign(msg).signature`；`VerifyingKey(pub).verify(...)` | `Ed25519PrivateKey.from_private_bytes(seed).sign(msg)`；`Ed25519PublicKey.from_public_bytes(pub).verify(...)` |
| 只做 Ed25519 | 是，API 面小 | 否，但只用到 `ed25519` 子模块 |
| 装的机会成本 | 新引入一个原生库 | 目标用户大概率已有 |
| 生态与维护 | 稳定，更新频率低 | 更新频繁，审计面更大 |

选择 `cryptography` 的取舍：多背约 2 MB 与更大的审计面，换「用户环境里通常已经有」。封装只需要 `Ed25519PrivateKey.from_private_bytes(seed)` 与 `.public_key().public_bytes_raw()` 两处，换库成本也就几行。
