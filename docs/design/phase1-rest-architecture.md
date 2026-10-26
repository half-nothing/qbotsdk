# Phase 1 设计 · v0.2 REST 架构定型

- 状态：草案，待第 13 节拍板后转实施
- 日期：2026-10-26
- 上游：[ROADMAP.md](../../ROADMAP.md) Phase 1
- 事实来源：[API 调用指南](https://bot.q.qq.com/wiki/develop/api-v2/dev-prepare/api-call-guide.html)、[错误与调试](https://bot.q.qq.com/wiki/develop/api-v2/openapi/error/error.html)、[获取用户频道列表](https://bot.q.qq.com/wiki/develop/api-v2/openapi/user/guilds.html)、[获取频道详情](https://bot.q.qq.com/wiki/develop/api-v2/autogen/api/guilds_guild_id.get.html)、[获取子频道列表](https://bot.q.qq.com/wiki/develop/api-v2/autogen/api/guilds_guild_id_channels.get.html)、[获取频道成员列表](https://bot.q.qq.com/wiki/develop/api-v2/server-inter/channel/role/member/get_members.html)、[获取频道身份组列表](https://bot.q.qq.com/wiki/develop/api-v2/server-inter/channel/role-group/get_guild_roles.html)

---

## 1 范围

### 1.1 本阶段交付

1. 分层：`Bot` → `ApiClient` → `Resource` → `HTTPClient` → `TokenManager`，`bot.py` 退化为薄门面。
2. 传输层：超时、指数退避重试、429 与 `Retry-After`、错误码映射、空包体与非 JSON 容错、trace_id 透传。
3. 只读频道域接口：频道列表/详情、子频道列表/详情、成员列表、身份组列表。
4. 分页：`iter_*` 异步生成器，两种游标模式统一封装。
5. 每个接口配 mock-server 测试，`_server` 抽成 `conftest.py` fixture。

### 1.2 明确不做

| 项 | 原因 | 归属 |
| --- | --- | --- |
| 消息发送/撤回、富媒体上传 | 依赖本阶段定型的传输层 | Phase 2 |
| WebSocket / WebHook | 事件层整体设计尚未开始 | Phase 3 |
| 客户端 QPS 限频器 | 平台 50 QPS/接口，先靠 429 兜底 | Phase 2 |
| `module/` 包改名 `transport/` | 纯 churn，等接口面稳定再评估 | Phase 4 前 |
| 写操作接口（创建/修改/删除子频道、身份组） | 出错面大，先保证读路径正确 | Phase 1.5 |

---

## 2 现状与差距

| 能力 | v0.1 现状 | Phase 1 要求 | 差距 |
| --- | --- | --- | --- |
| 分层 | `Bot` 直接持有 `HTTPClient` | Resource 四层 | 无 `api/` 层 |
| 超时 | 未设置 | 连接/读取可配 | 缺失 |
| 重试 | 无 | 429 + 5xx + 幂等方法 | 缺失 |
| 错误码 | `data.get("code")` | 读 `err_code` | **读错字段** |
| 空包体 | `.json()` 先执行 | 204/空串返回 `None` | 抛 `ContentTypeError` |
| trace | 未采集 | `X-Tps-trace-ID` 与 `trace_id` | 缺失 |
| token | 单字段过期 | 刷新窗口与硬过期分离 | 无法回退旧 token |
| 接口面 | `get_me` | 频道域六个只读接口 | 缺 6 个 |
| 测试基建 | `_server` 内联在首个测试文件 | `conftest.py` 共享 | 未抽 |

### 2.1 已确认的缺陷，附代码位置

1. **错误码字段名错误**：官方返回体为 `{"err_code": 40034005, "message": "...", "trace_id": "..."}`，`src/qqbot/module/http_client.py:30` 读的是 `data.get("code")`，`APIError.code` 恒为 `None`。
2. **204 无法返回**：`src/qqbot/module/http_client.py:111` 的 `await resp.json()` 排在状态判断之前。删除类接口返回 204 且无包体，直接抛 `aiohttp.ContentTypeError`，调用方拿不到 `APIError`。
3. **无超时**：`src/qqbot/module/http_client.py:85` 的 `ClientSession(trace_configs=[...])` 未传 `timeout`，DNS 或对端挂死时只能等 TCP 层。
4. **无重试**：429 与 5xx 一律直抛。
5. **token 无法回退**：`src/qqbot/module/token_manager.py:45` 把 60s buffer 烘进 `_expire_at`，到点后 `_get_cached()` 返回 `None`，刷新失败时旧 token 明明还有效却用不上；`expires_in <= 60` 时 `_expire_at` 落到过去，每个请求都会刷一次。
6. **能力面**：只有 `get_me()`，频道域六个接口全缺。

---

## 3 分层架构

```
用户代码
   │
   ▼
┌───────────────────────────────┐
│ Bot        门面 / 生命周期     │  ← Phase 3 事件总线挂载于此
└──────────────┬────────────────┘
               │ .api
┌──────────────▼────────────────┐
│ ApiClient                     │
│  .user  .guild  .channel  .message │  ← .message 本阶段仅占位
└──────────────┬────────────────┘
               │ 只有 Resource 知道 URL 与响应形状
┌──────────────▼────────────────┐
│ HTTPClient   传输层            │
│ 超时 / 重试 / 429 / 错误映射    │
└──────────────┬────────────────┘
┌──────────────▼────────────────┐
│ TokenManager 凭证              │
└───────────────────────────────┘
```

分层契约，违反即算设计缺陷：

- **Resource 只做三件事**：拼路径、调 `http.request`、把返回值转模型。不得 `import aiohttp`。
- **HTTPClient 不认识业务模型**，只处理 `dict` / `list` / `None` / `str`。
- **Bot 不含业务逻辑**，只做装配与生命周期，并作为事件总线的挂载点。
- 依赖单向：`api → http_client → token_manager`，反向引用一律禁止。
- 测试只需要在传输层打桩，模型层与资源层可用假 dict 驱动。

---

## 4 传输层

### 4.1 客户端配置

```python
@dataclass(frozen=True, slots=True)
class ClientOptions:
    timeout_total: float = 30.0
    timeout_connect: float = 10.0
    max_attempts: int = 3  # 含首次请求
    backoff_base: float = 0.5
    backoff_max: float = 8.0
    max_retry_after: float = 30.0  # 平台要求等待超过此值就放弃重试
```

`Bot(app_id, client_secret, *, options: ClientOptions | None = None)`，默认值开箱可用。

### 4.2 单次请求流程

顺序是设计的一部分，不能调换：

1. 取 token，`TokenManager.get_token(session)`。
2. 组 header：`Authorization: QQBot {token}`，`json=` 存在时由 aiohttp 自动补 `Content-Type`。
3. yarl 拼接：`URL(BASE_URL) / path.lstrip("/")`，保持现状。
4. `session.request(...)`，捕获 `aiohttp.ClientError` 与 `asyncio.TimeoutError`。
5. **先按状态分流，再解析包体**：
   - `429`：解析 `Retry-After`，未超上限则 sleep 后重试，超上限或次数用尽则抛 `APIError`。
   - `401`：强制 `TokenManager.invalidate()` 后重试一次，仍 401 则抛。
   - 其他 `>= 400`：解析错误体，抛 `APIError`。
   - `204`：返回 `None`。
6. `await resp.text()` 取原始文本，不要直接 `.json()`。
7. 空串 → `None`；能 `json.loads` 则用解析结果，否则原样返回文本。
8. 包体里出现非 0 `err_code` 时，即使状态是 201/202 也按错误处理：官方明确 201/202 是「异步成功但可能返回 error body」。

### 4.3 重试矩阵

| 情形 | GET / HEAD / PUT / DELETE | POST / PATCH |
| --- | --- | --- |
| 429 | 重试，按 `Retry-After` | 重试，按 `Retry-After` |
| 500 / 502 / 503 / 504 | 指数退避重试 | 不重试 |
| 连接错误、读超时 | 指数退避重试 | 不重试 |
| 401 | 刷新 token 后重试 1 次 | 同左 |
| 其他 4xx | 不重试 | 不重试 |

两条规则的依据：

- 429 表示请求被拒、服务端未处理，任何方法都可安全重试；这是平台限频的主要表现。
- 5xx 与网络异常无法确认服务端是否已处理，POST 重试有重复副作用风险。消息发送类接口在 Phase 2 会显式声明 `idempotent=False`。

### 4.4 Retry-After 解析

- 两种格式都要支持：整数秒，以及 HTTP-date（`email.utils.parsedate_to_datetime`）。
- 超过 `max_retry_after` 时不再等待，直接抛 `APIError`，避免阻塞调用方几十秒。
- 缺该头时退化为 `min(backoff_base * 2 ** (attempt - 1), backoff_max)` 加 0~25% 抖动，避免多实例同时重试。

### 4.5 日志与 trace

- 现有三条 TRACE 钩子保留：`-->`、`<--`、`!!`。
- 响应头 `X-Tps-trace-ID` 与响应体 `trace_id` 取其一写入 `APIError.trace_id`，并在 ERROR 级日志打印，便于直接贴给平台排障。

### 4.6 凭证生命周期

`TokenManager` 记两个时间点，都用 `time.monotonic()`（不随系统时钟跳变）：

| 字段 | 含义 | 取值 |
| --- | --- | --- |
| `refresh_at` | 到点后主动换新 | `now + expires_in - refresh_buffer`，`refresh_buffer` 默认 60s |
| `hard_expire_at` | 到点后旧 token 确定不可用 | `now + expires_in` |

- `get_token`：`now < refresh_at` 直接返回缓存；否则进锁，双检锁后再查一次，仍需要才刷新。
- 刷新失败（`APIError` / `TransportError` / 响应结构不符等任何异常）：只要 `now < hard_expire_at`，打一条 WARNING 后继续用旧 token；否则原样抛出。
- `expires_in <= refresh_buffer`（平台给的有效期比预留窗口还短）时退化为半程刷新 `expires_in / 2`，否则每次调用都会打凭证接口。
- 凭证接口自身的错误统一成 `APIError` 或 `TransportError`，不再向上冒 aiohttp 原生异常。
- 凭证接口会用 **HTTP 200 + `err_code`** 表示失败，也有包体不是凭证结构的情况：两者都先经 `error_code_of()` 判定，再由 `APIError.from_response()` 包装，绝不让 `pydantic.ValidationError` 泄漏给调用方；`trace_id` 优先取响应头 `X-Tps-trace-ID`。
- `invalidate()` 三个字段一起清零，401 路径靠它强制换 token。

---

## 5 错误体系

### 5.1 异常树

```python
class QQBotError(Exception): ...


class TransportError(QQBotError):  # 没有 HTTP 响应：连接失败、超时
    cause: BaseException


class APIError(QQBotError):  # 有 HTTP 响应但业务失败
    status: int  # HTTP 状态码
    code: int  # 官方 err_code，缺省 0
    message: str
    trace_id: str | None
    method: str
    path: str
    body: object  # 已解析的错误体，截断到 2KB

    @property
    def retryable(self) -> bool: ...  # 系统类错误码或 5xx
```

`TransportError` 的意义是让调用方不必 `import aiohttp` 才能写 `except`。对外只暴露 `QQBotError` 及其两个子类。

### 5.2 本阶段收录的错误码

官方公共错误码按用途分三组，不是全量照抄 200 多条：

| 码 | 名称 | 处理建议 |
| --- | --- | --- |
| 10001 | UnknownAccount | 账号异常，不可重试 |
| 10003 | UnknownChannel | 子频道不存在，检查 channel_id |
| 10004 | UnknownGuild | 频道不存在，检查 guild_id |
| 11241 | ErrorWrongToken | 缺 token，属 SDK 内部问题 |
| 11243 | ErrorCheckTokenNotPass | token 无效，触发刷新后重试一次 |
| 11251 / 11261 / 11275 | ErrorWrongAppid | appid 配置错误 |
| 11252 / 11262 / 11263 / 11281 | 系统检查类失败 | **可重试一次**，官方明确说明 |
| 11253 | ErrorCheckAppPrivilegeNotPass | 应用未获接口权限，需平台申请 |
| 11264 | ErrorGuildAuthNotPass | 频道级未授权，提示用户重新授权 |
| 11265 | ErrorRobotHasBaned | 机器人被封禁，终态 |
| 11282 | ErrorCheckAdminNotPass | 非管理员，属逻辑错误 |
| 12002 | RequestInvalid | 请求体非法，不可重试 |
| 20028 | ChannelHitWriteRateLimit | 子频道消息限频，Phase 2 用 |

用 `IntEnum` 表达，同时保留区间常量（如 `301000~301099` 子频道权限错误）用于归类。未知码保留原值不报错，`ErrorCode` 只是便利集合而非白名单。

**判定原则**：一律看 `err_code`，不看 `message`，官方明确 message 会变。

### 5.3 兼容

`APIError` 现有三个属性 `status` / `code` / `message` 保留原义，新增字段全部有默认值，v0.1 用户代码不需要改。

---

## 6 模型层

### 6.0 数据结构来源准则

用户明确要求：**所有数据结构直接来源于 API 返回值**。这决定模型层是「抄」而不是「设计」：

1. **字段必须有出处**。每个字段要么出现在官方接口文档的「响应体」表格里，要么出现在官方给出的响应示例 JSON 里。找不到出处就不加，宁缺毋造。
2. **文档与示例冲突时以示例为准**，并在代码注释里记一句冲突点。示例是跑过的真实返回，表格是人工维护的。
3. **官方示例里有、表格里没列的字段也要收**。例如成员列表里 `user` 对象带 `public_flags` 与 `system`，`User` 模型必须容纳它们，标为可选。
4. **只做类型收窄与别名钉住，不做业务推导**。`Role.hoist` 官方是 `integer` 就保持 `int`，不转 `bool`；`member_limit` 保持 `int`；`role_num_limit` 官方给的是字符串 `"30"`，就保持 `str`。
5. **平台多给字段不报错**：`extra="ignore"`，模型不承担校验响应完整性的职责。
6. **形状以官方 SDK 契约为准，不写兜底解析器**：同一接口出现两种说法时，以「返回说明 + 返回示例」一致的文档为准，并尽量用实测响应确认，见 6.4。
7. **测试 fixture 用官方示例 JSON 原文**，逐字拷进 `tests/data/`，不手搓字段。这样模型一旦脱离 API 真实形状，测试立刻红。

推论：模型层不追求「完整覆盖官方所有字段」，只覆盖本阶段六个接口实际返回的字段；新增接口时同步补模型与示例快照。

### 6.1 基类

```python
class QQModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore", frozen=True)
```

- `populate_by_name=True`：字段名与 alias 双通道可用。
- `extra="ignore"`：官方会加字段，不能因未知字段炸掉。
- `frozen=True`：模型是响应的快照，避免用户误改后回传。
- alias 继续用显式 `Field(alias=...)`，不引入 `alias_generator`。官方字段本身就是下划线风格，生成器反而增加心智负担。

### 6.2 枚举

| 枚举 | 取值 |
| --- | --- |
| `ChannelType` | 0 文字、2 语音、4 分组、10005 直播、10006 应用、10007 论坛 |
| `ChannelSubType` | 0 闲聊、1 公告、2 攻略、3 开黑 |
| `PrivateType` | 0 公开、1 群主管理员可见、2 群主管理员+指定成员 |
| `SpeakPermission` | 0 无效、1 所有人、2 群主管理员+指定成员 |

官方字段是 `integer`，用 `IntEnum` 可以同时接受整数与枚举成员。

### 6.3 模型清单

| 模型 | 字段要点 |
| --- | --- |
| `Guild` | `id`、`name`、`icon`、`owner_id`、`owner: bool`、`member_count`、`max_members`、`description`、`joined_at: datetime` |
| `Channel` | `id`、`guild_id`、`name`、`type: ChannelType`、`sub_type`、`position`、`parent_id`、`owner_id`、`private_type`、`speak_permission`、`application_id`、`permissions` |
| `Member` | `user: User`、`nick`、`roles: list[str]`、`joined_at`、`deaf`、`mute`、`pending` |
| `Role` | `id`、`name`、`color: int`、`hoist: int`、`number: int`、`member_limit: int` |
| `RolesResult` | `guild_id`、`roles: list[Role]`、`role_num_limit: str` |
| `User` | 保持现状，补 `public_flags`、`system` 两个可选字段 |

### 6.4 响应形状：原始证据与待定结论

这一节先前写过一个「双形状兜底解析器」，那是从文档表格与示例的差异反推的，**没有实测依据，已作废**。下面只列原始数据，结论等真实返回后再定。

#### 证据一：子频道列表 `GET /guilds/{guild_id}/channels`

来源：[获取子频道列表](https://bot.q.qq.com/wiki/develop/api-v2/autogen/api/guilds_guild_id_channels.get.html)

响应体表格原文：

```
| 名称 | 类型 | 描述 |
| channels | [][Channel](#schema-channel) | |
```

响应示例原文：

```json
[
  {
    "id": "123456",
    "guild_id": "123456789012345678",
    "name": "文字交流区",
    "type": 0,
    "sub_type": 0,
    "position": 1,
    "parent_id": "0",
    "owner_id": "123456789012345678",
    "private_type": 0,
    "speak_permission": 1
  },
  {
    "id": "123457",
    "guild_id": "123456789012345678",
    "name": "语音聊天室",
    "type": 2,
    "sub_type": 0,
    "position": 2,
    "parent_id": "0",
    "owner_id": "123456789012345678",
    "private_type": 0,
    "speak_permission": 1
  }
]
```

表格说返回对象、字段名为 `channels`，示例给的是裸数组。**同一页面内自相矛盾**，两种读法都能自圆其说，只看文档无法判定。

#### 证据二：机器人频道列表 `GET /users/@me/guilds`

来源：[获取用户频道列表](https://bot.q.qq.com/wiki/develop/api-v2/openapi/user/guilds.html)

表格写「返回 Guild 对象数组」，示例是裸数组，两者一致。这个接口语义确定：**裸数组**。

#### 证据三：身份组列表 `GET /guilds/{guild_id}/roles`

来源：[获取频道身份组列表](https://bot.q.qq.com/wiki/develop/api-v2/server-inter/channel/role-group/get_guild_roles.html)

表格字段与示例一致，都是对象：

```json
{
  "guild_id": "123456",
  "roles": [
    {"id": "4", "name": "创建者", "color": 4294927682, "hoist": 1, "number": 1, "member_limit": 1},
    {"id": "2", "name": "管理员", "color": 4280276644, "hoist": 1, "number": 5, "member_limit": 50}
  ],
  "role_num_limit": "30"
}
```

#### 证据四：官方 Python SDK 文档（同一个接口）

来源：[获取子频道列表 · Python SDK](https://bot.q.qq.com/wiki/develop/pythonsdk/api/channel/get_channels.html)

返回说明原文：

```
## 返回说明

返回 [Channel](#channel) 数组。
```

返回示例原文，字段名是 `data`，值是数组本身：

```json
[
  {
    "id": "channel_id",
    "guild_id": "guild_id",
    "name": "子频道名",
    "type": 4,
    "position": 2,
    "parent_id": "0",
    "owner_id": "0",
    "sub_type": 0
  },
  {
    "id": "channel_id",
    "guild_id": "guild_id",
    "name": "子频道名",
    "type": 4,
    "position": 3,
    "parent_id": "0",
    "owner_id": "0",
    "sub_type": 0
  }
]
```

#### 证据五：官方 Node SDK 文档（同一个接口）

来源：[获取子频道列表 · Node SDK](https://bot.q.qq.com/wiki/develop/nodesdk/channel/get_channels.html)

同样是「返回 [Channel](#channel) 数组」，示例 `data` 也是裸数组，结构同上，只是 id 用了 `'xxxxxx'` 占位。

#### 现有证据小结

| 证据 | 来源 | 对形状的说法 |
| --- | --- | --- |
| 一 | api-v2 autogen 响应体表格 | 对象，字段 `channels` |
| 一 | api-v2 autogen 响应示例 | 裸数组 |
| 二 | `/users/@me/guilds` 表格与示例 | 裸数组，两处一致 |
| 三 | `/guilds/{id}/roles` 表格与示例 | 对象，两处一致 |
| 四 | Python SDK 返回说明与示例 | 裸数组 |
| 五 | Node SDK 返回说明与示例 | 裸数组 |

**五条里四条指向裸数组**，且指向对象的那一条是 autogen 页面的表格单元格，而同一页面的示例自身就是数组。autogen 表格的 `channels` 行更像是从 OpenAPI schema 生成时留下的字段名，而不是真实响应结构。

#### 结论（2026-10-26 已定）

**按裸数组设计**：`GET /guilds/{id}/channels` 的响应体就是 `[Channel, ...]`，`Channel.list` 直接把 `payload` 当数组解析，不写兜底解析器，不猜 `channels` 字段。

依据：五条证据里四条指向裸数组，两条官方 SDK 的「返回说明」是给开发者写代码用的契约。autogen 表格的 `channels` 行按 OpenAPI schema 生成残留处理。

#### 实测不符时的修复范围

这条结论允许出错，出错时改动面很小：

| 若实测是 | 改哪里 | 工作量 |
| --- | --- | --- |
| `{"channels": [...]}` 对象 | `Channel.list` 里取 `payload["channels"]` 一行 | 1 行 + 快照 |
| 两种都会出现 | 解析层加一次形状判断 | 3 行 + 两个快照 |

`tests/data/` 里子频道列表的快照是从官方示例逐字拷的，实测形状一旦不同，`test_models.py` 会先红，不会静默错。所以这里可以先按裸数组走，不必现在就把兼容写进去。

#### 校准途径

有真实响应时贴一条，或从 TRACE 日志里取，`examples/hello.py` 已经把 loguru 开到 TRACE：

```
响应 GET https://api.bot.qq.com/guilds/<guild_id>/channels status=200 body=...
```

### 6.5 测试快照清单

`tests/data/` 里的 JSON 全部逐字拷自官方文档「响应示例」，不手工增删字段：

| 文件 | 对应接口 | 官方来源 |
| --- | --- | --- |
| `guilds.json` | `GET /users/@me/guilds` | [获取用户频道列表](https://bot.q.qq.com/wiki/develop/api-v2/openapi/user/guilds.html) |
| `guild.json` | `GET /guilds/{guild_id}` | [获取频道详情](https://bot.q.qq.com/wiki/develop/api-v2/autogen/api/guilds_guild_id.get.html) |
| `channels.json` | `GET /guilds/{guild_id}/channels` | [获取子频道列表](https://bot.q.qq.com/wiki/develop/api-v2/autogen/api/guilds_guild_id_channels.get.html) |
| `channel.json` | `GET /channels/{channel_id}` | [获取子频道详情](https://bot.q.qq.com/wiki/develop/api-v2/autogen/api/channels_channel_id.get.html) |
| `members.json` | `GET /guilds/{guild_id}/members` | [获取频道成员列表](https://bot.q.qq.com/wiki/develop/api-v2/server-inter/channel/role/member/get_members.html) |
| `roles.json` | `GET /guilds/{guild_id}/roles` | [获取频道身份组列表](https://bot.q.qq.com/wiki/develop/api-v2/server-inter/channel/role-group/get_guild_roles.html) |
| `group.json` | `GET /v2/groups/{group_openid}/info` | [获取群基本信息](https://bot.qq.com/wiki/develop/api-v2/autogen/api/v2_groups_group_openid_info.get.html) |
| `group_members.json` | `GET /v2/groups/{group_openid}/members` | [获取群成员列表](https://bot.qq.com/wiki/develop/api-v2/autogen/api/v2_groups_group_openid_members.get.html) |
| `group_member.json` | `GET /v2/groups/{group_openid}/members/{member_openid}` | [获取群成员信息](https://bot.qq.com/wiki/develop/api-v2/autogen/api/v2_groups_group_openid_members_member_openid.get.html) |
| `group_bot_state.json` | `GET /v2/groups/{group_openid}/bot_state` | [获取机器人群内状态](https://bot.qq.com/wiki/develop/api-v2/autogen/api/v2_groups_group_openid_bot_state.get.html) |
| `group_mute.json` | `GET /v2/groups/{group_openid}/restrict_chat_setting` | [查询群禁言状态](https://bot.qq.com/wiki/develop/api-v2/autogen/api/v2_groups_group_openid_restrict_chat_setting.get.html) |

`group_bot_state.json` 是唯一带修正的快照：官方示例末尾 `"member_role": "member` 少了收尾引号，照抄无法解析，补上引号后其余内容逐字保留。

`tests/test_models.py` 对每个频道快照做两件事：解析成模型并断言关键字段语义（枚举、时区、字符串型 `role_num_limit`），以及用 `missing_fields()` 检查「快照里出现但模型里没有」的字段集合为空。官方改了返回字段而模型没跟上时，这里先红。群组快照由 `tests/test_group_api.py` 覆盖，同样对比 `member_openid`、枚举与时间字段。

---

## 7 资源层 API

| 资源 | 方法 | 接口 | 返回 |
| --- | --- | --- | --- |
| `bot.api.user` | `me()` | `GET /users/@me` | `User` |
| `bot.api.user` | `guilds(*, before=None, after=None, limit=100)` | `GET /users/@me/guilds` | `list[Guild]` |
| `bot.api.user` | `iter_guilds(*, limit=100)` | 同上，自动翻页 | `AsyncIterator[Guild]` |
| `bot.api.guild` | `get(guild_id)` | `GET /guilds/{guild_id}` | `Guild` |
| `bot.api.guild` | `channels(guild_id)` | `GET /guilds/{guild_id}/channels` | `list[Channel]` |
| `bot.api.guild` | `members(guild_id, *, after="0", limit=100)` | `GET /guilds/{guild_id}/members` | `list[Member]` |
| `bot.api.guild` | `iter_members(guild_id, *, limit=100)` | 同上，自动翻页并去重 | `AsyncIterator[Member]` |
| `bot.api.guild` | `roles(guild_id)` | `GET /guilds/{guild_id}/roles` | `RolesResult` |
| `bot.api.channel` | `get(channel_id)` | `GET /channels/{channel_id}` | `Channel` |
| `bot.api.group` | `get(group_openid)` | `GET /v2/groups/{group_openid}/info` | `Group` |
| `bot.api.group` | `bot_state(group_openid)` | `GET /v2/groups/{group_openid}/bot_state` | `GroupBotState` |
| `bot.api.group` | `members(group_openid, *, cursor="")` | `GET /v2/groups/{group_openid}/members` | `GroupMembersPage` |
| `bot.api.group` | `iter_members(group_openid)` | 同上，按 `next_cursor` 翻页 | `AsyncIterator[GroupMember]` |
| `bot.api.group` | `member(group_openid, member_openid)` | `GET /v2/groups/{group_openid}/members/{member_openid}` | `GroupMember` |
| `bot.api.group` | `mute_setting(group_openid)` | `GET /v2/groups/{group_openid}/restrict_chat_setting` | `GroupMuteState` |
| `bot.api.message` | 本阶段空实现 | — | — |

命名约定：

- 取单个对象用 `get(x_id)`，取集合用复数名词，翻页用 `iter_` 前缀。
- 参数一律显式 `guild_id: str` / `group_openid: str`，不做「从 Channel 反推 guild」这种隐式推导。
- 所有资源方法都是 `async def`，返回已解析的模型，不返回原始 dict。

群组与频道是两套独立的数据模型，不复用：频道的 `Guild`/`Member` 基于 `guild_id` + `user.id`，群组的 `Group`/`GroupMember` 基于 `group_openid` + `member_openid`，两者的 ID 体系不互通。群接口全部在 `/v2` 前缀下，路径常量集中在 `src/qqbot/api/group.py` 的 `_GROUPS`。

本阶段 `bot.api.group` 只做只读，写操作（群成员批量移除、禁言设置、入群审批）随消息收发一起进 Phase 2。

`Bot.get_me()` 保留为 `bot.api.user.me()` 的转发，docstring 标 deprecated，v0.3 移除。

---

## 8 分页

两类游标语义不同，不能硬合成一个抽象：

| 场景 | 游标 | 上限 | 终止条件 | 额外约束 |
| --- | --- | --- | --- | --- |
| 频道列表 | `after=<最后一条 guild id>` | `limit` 默认 100、最大 100 | 返回空页，或不足 `limit` | `before` 与 `after` 同给时 `after` 失效 |
| 频道成员列表 | `after=<最后一个 member 的 user.id>` | `limit` 默认 1、最大 400 | 返回空页 | **可能重复返回已给过的成员，需按 user.id 去重** |
| 群成员列表 | `cursor=<上一页的 next_cursor>` | 固定每页 30 条，无 `limit` 参数 | `next_cursor` 为空串，或返回空数组 | 游标是不透明字符串，不能自己拼 |

统一实现在 `src/qqbot/module/pagination.py`，参数化成三个回调：

```python
async def paginate[T](
    fetch_page: Callable[[str | None], Awaitable[list[T]]],
    *,
    cursor_of: Callable[[list[T]], str | None],
    key_of: Callable[[T], str] | None = None,  # 提供则去重
    page_size: int | None = None,  # 提供则「不足一页即结束」
) -> AsyncIterator[T]: ...
```

- `fetch_page(cursor)` 由资源方法闭包出具体请求；首次调用游标为 `None`。
- 成员列表传 `key_of=lambda m: m.user.id` 去重，`page_size` 留空 —— 官方只承诺「空数组表示结束」；频道列表传 `page_size=limit`，少一页即可停。
- 群成员列表返回的是「整页对象」而不是列表，`next_cursor` 与 `members` 同级，所以 `iter_members` 在 `fetch_page` 闭包里记下 `next_cursor`，`cursor_of` 再把它读出来；这不改变 `paginate` 的签名。
- 防御性上限：游标未推进或页数超过 1000 时中断并 `logger.warning`，避免平台异常导致死循环。`cursor_of` 返回 `None` 表示「没有下一页」，属正常结束，不打告警 —— 群成员列表就靠这个标志收尾。

不引入独立的 `Paginator` 类。两个调用点，一个函数足够，加一层类只是多一次跳转。

---

## 9 目录结构变更

```
src/qqbot/
├── __init__.py              # 改：导出 Bot, User, Guild, Channel, Member, Role, APIError, ErrorCode
├── bot.py                   # 改：薄门面 + options + .api 属性
├── constant.py              # 不动
├── exceptions.py            # 新：QQBotError / TransportError / APIError / ErrorCode
├── options.py               # 新：ClientOptions
├── api/
│   ├── __init__.py          # 新：ApiClient 聚合五个资源
│   ├── _parse.py            # 新：形状校验，不符抛 TransportError
│   ├── user.py              # 新
│   ├── guild.py             # 新
│   ├── channel.py           # 新
│   ├── group.py             # 新：群组只读（info / bot_state / members / mute）
│   └── message.py           # 新：占位，Phase 2 填
├── model/
│   ├── __init__.py          # 改：统一导出
│   ├── base.py              # 新：QQModel
│   ├── user.py              # 改：补 public_flags / system
│   ├── guild.py             # 新
│   ├── channel.py           # 新
│   ├── member.py            # 新
│   ├── group.py             # 新：Group / GroupMember / 禁言规则
│   ├── role.py              # 新
│   └── token.py             # 不动
└── module/
    ├── http_client.py       # 改：传输层全部能力
    ├── token_manager.py     # 改：refresh_at / hard_expire_at 拆分 + invalidate()
    └── pagination.py        # 新：_paginate

tests/
├── conftest.py              # 新：MockServer fixture
├── data/                    # 新：官方响应示例 JSON 原文，逐字拷贝
├── test_hello_route.py      # 改：改用 conftest + pytest-asyncio
├── test_http_client.py      # 新：超时/重试/429/204/非 JSON/错误映射
├── test_token_manager.py    # 新：并发、刷新、回退、invalidate
├── test_pagination.py       # 新：去重、终止、游标推进
├── test_models.py           # 新：官方示例 JSON → 模型，字段不漂移
├── test_guild_api.py        # 新：频道六个接口的端到端 mock 测试
└── test_group_api.py        # 新：群组五个接口 + next_cursor 翻页
```

`APIError` 从 `module/http_client.py` 迁到顶层 `exceptions.py`：它已是公开 API 的一部分，留在传输层内部不合适。旧路径保留 re-export 一版。

---

## 10 测试策略

### 10.1 conftest 设计

```python
@dataclass
class RecordedCall:
    method: str
    path: str
    query: dict[str, str]
    headers: dict[str, str]
    json: object | None


class MockServer:
    def route(self, method: str, path: str, handler: Handler) -> None: ...
    def routes(self, *specs) -> None: ...  # 批量注册
    @property
    def calls(self) -> list[RecordedCall]: ...
    @property
    def url(self) -> str: ...


@pytest.fixture
def server() -> MockServer: ...  # 自带 token 路由


@pytest.fixture
async def bot(server) -> Bot: ...  # 已把 BASE_URL/TOKEN_URL 指向 server
```

要点：

- `MockServer` 记录每次调用的 method/path/query/headers/body，测试用断言检查「发了什么」，而不是只检查返回值。
- token 路由默认注册，返回 `{"access_token": "test-token", "expires_in": 7200}`，避免每个用例重复写。
- `monkeypatch` 的模块属性路径保持现状：`qqbot.module.token_manager.TOKEN_URL`、`qqbot.module.http_client.BASE_URL`。

### 10.2 用例清单

| 文件 | 用例 | 验证点 |
| --- | --- | --- |
| test_http_client | `test_204_returns_none` | 空包体不抛 |
| test_http_client | `test_non_json_body` | 返回原文本，不抛 |
| test_http_client | `test_err_code_mapped` | `err_code` → `APIError.code` |
| test_http_client | `test_trace_id_from_header` | `X-Tps-trace-ID` 进字段 |
| test_http_client | `test_429_retries_with_retry_after` | 第二次成功，等待被记录 |
| test_http_client | `test_429_retry_after_too_long` | 超上限直接抛 |
| test_http_client | `test_500_no_retry_for_post` | POST 只请求一次 |
| test_http_client | `test_timeout_raises_transport_error` | 超时 → `TransportError` |
| test_http_client | `test_401_refreshes_token_once` | token 接口被调两次 |
| test_token_manager | `test_concurrent_single_fetch` | 10 并发只打一次凭证接口 |
| test_token_manager | `test_refresh_after_window` | 过刷新点后用新 token |
| test_token_manager | `test_fallback_after_refresh_failure` | 旧 token 仍可用 |
| test_token_manager | `test_hard_expire_raises` | 刷新失败且已硬过期 → 抛 `APIError` |
| test_token_manager | `test_invalidate_forces_refresh` | 401 路径 |
| test_token_manager | `test_short_lived_token_refreshes_at_half_lifetime` | 有效期短于预留窗口时按半程刷新 |
| test_pagination | `test_members_dedupe` | 重复 user.id 被过滤 |
| test_pagination | `test_stops_on_empty_page` | 不无限循环 |
| test_pagination | `test_stops_when_cursor_stalls` | 游标不推进时中断 |
| test_pagination | `test_guilds_iterate_until_partial_page` | 不足一页即结束 |
| test_guild_api | `test_guilds_pagination` | query 里 after/limit 正确 |
| test_guild_api | `test_channels_list_is_bare_array` | 裸数组解析，不写双形状兜底 |
| test_guild_api | `test_roles_result` | `role_num_limit` 是字符串 |
| test_group_api | `test_group_members_pagination` | 首屏不带 cursor、第二屏带 `next_cursor`，两页即止 |
| test_group_api | `test_group_mute_setting` | `HH:mm` 保持字符串，`weekdays` 为 1~7 |

时间相关断言用可注入的 `sleep` 或 `time.monotonic` 桩，不要真等。

---

## 11 实施切片

按可独立合并、每步都能跑绿拆成 6 片，另加一个增补片 T7：

| 切片 | 内容 | 验收 |
| --- | --- | --- |
| T1 | `exceptions.py`、`options.py`、`http_client.py` 重写 | `pdm run pytest tests/test_http_client.py` 全绿 |
| T2 | `model/base.py` + `Guild`/`Channel`/`Member`/`Role`/`RolesResult` + `User` 补字段 + `tests/data/` 快照与 `test_models.py` | `pdm run pytest tests/test_models.py` 与 `pdm run mypy` 全绿 —— **已完成 2026-10-26** |
| T3 | `module/token_manager.py` 拆分刷新窗口 + `invalidate()` | `tests/test_token_manager.py` 全绿 —— **已完成 2026-10-26** |
| T4 | `api/` 四个资源 + `Bot.api` + `get_me` 转发 | `tests/test_guild_api.py` 全绿 —— **已完成 2026-10-26** |
| T5 | `module/pagination.py` 与 `iter_*` | `tests/test_pagination.py` 全绿 —— **已完成 2026-10-26** |
| T6 | README 快速开始、`examples/` 换成频道列表示例、ROADMAP 打勾 | 四项门禁全绿 |
| T7 | 增补：群组只读（`api/group.py`、`model/group.py`、`GroupResource` 五接口 + `iter_members`） | `tests/test_group_api.py` 全绿 —— **已完成 2026-10-26** |

T7 是 Phase 1 关账后的增补切片：用户要求群组（QQ 群）与频道同阶段交付。它只新增资源与方法，不动已有签名；群组写操作仍留给 Phase 2。

每片合入前固定跑：`pdm run ruff check` → `pdm run ruff format --check` → `pdm run mypy` → `pdm run pytest -q`。

---

## 12 版本与兼容

- 版本号 `0.1.0` → `0.2.0`，`pyproject.toml` 同步。
- 保留：`Bot(app_id, client_secret)`、`Bot.get_me()`、`Bot.close()`、`async with`、`APIError.status/code/message`。
- 新增：`Bot.api.*`、`ClientOptions`、`QQBotError`/`TransportError`、`iter_*`。
- `APIError` 的 `code` 语义修正后从 `None` 变成真实整数，属修 bug，不算破坏性变更。

### 12.1 文案约定

- 异常消息、日志（`logger.trace/error` 等）、返回给调用方的错误文本，**一律英文**；形如 `GET /users/@me request failed: ...`、`Rate limited, retrying GET in 0.80s`。
- 注释、docstring、文档、示例里的人话**保持中文**，`RUF001~RUF003` 也因此保持 ignore。
- 英文文案不拼接原始响应体全文，长包体走 `APIError.body` 的 2KB 预览。

---

## 13 已拍板（2026-10-26）

| # | 议题 | 结论 | 落点 |
| --- | --- | --- | --- |
| 1 | 是否引入 `pytest-asyncio` | **引入**，`asyncio_mode = "auto"`，同时删掉测试里的 `asyncio.run(inner())` 包装 | T1 的 pyproject 改动 |
| 2 | 429 是否对 POST 也重试 | **是**，所有方法一视同仁 | 4.3 矩阵已按此写 |
| 3 | 网络异常是否包装 | **是**，统一为 `TransportError`，原始异常挂 `.cause` | 5.1 异常树 |
| 4 | `module/` 是否改名 `transport/` | **暂不改**。改名的连带成本是测试里 `qqbot.module.http_client.BASE_URL` 这类 monkeypatch 路径与外部 import 全部受影响，正好踩在「不影响功能」的边界上；等 v0.2 接口面定稿后一次性做 | 留 Phase 4 前 |
| 5 | 是否提供 `list_*` 返回全量 | **不提供**，只给 `iter_*` | 7、8 节 |
| 6 | `ClientOptions` 位置 | **独立 `options.py`** | 9 节目录 |
| 7 | 异常消息与日志用什么语言 | **一律英文**；注释、docstring、文档保持中文 | 12.1 节，T1 代码已按此统一 |

第 4 项按「不影响功能」这一约束理解为维持原名。若本意是「改名不影响功能就改」，说一声，我会把它并入 T1 一起做，同时给 `qqbot.module` 留一版兼容 shim。
