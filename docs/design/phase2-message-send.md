# Phase 2 设计：消息发送与撤回（v0.3.0）

> 状态：已拍板（2026-10-26，见 §14），待实施。范围：只读之外的第一个写操作切片。

## 1. 范围与非目标

### 1.1 本期范围

| 场景 | 能力 | 接口 |
| --- | --- | --- |
| 频道文字子频道 | 发送文本、Markdown、引用回复、图片 URL、`file_image` 直传、撤回 | `POST /channels/{channel_id}/messages`、`DELETE /channels/{channel_id}/messages/{message_id}` |
| QQ 群 | 发送文本、Markdown、富媒体（`msg_type=7`）、引用回复、按钮键盘、撤回 | `POST /v2/groups/{group_openid}/messages`、`DELETE /v2/groups/{group_openid}/messages/{message_id}` |
| QQ 群 | 富媒体上传（URL 上传、二进制直传） | `POST /v2/groups/{group_openid}/files` |

### 1.2 非目标

- **事件与 WebSocket**：本期不接收消息，只提供「拿着 `msg_id` 去回复」的能力。
- **单聊（C2C）**：`/v2/users/{user_openid}/messages` 与流式消息留到 Phase 3。
- **分片上传**：`upload_prepare` / `upload_part_finish` 留到后续版本，本期只支持 URL 上传与 5MB 以内二进制直传。
- **按钮交互的后续部分**：`Modal` 弹窗、`INTERACTION_CREATE` 回调应答（`PUT /interactions/{interaction_id}`）、按钮点击统计，留到 Phase 3。
- **频道私信、表情表态、频道消息列表**。
- **本地限流器**：频控只写进文档与 docstring，不在客户端排队（理由见 §8.3）。

## 2. 现状与差距

Phase 1 结束时 `src/qqbot/api/message.py` 只有一句占位：

```python
class MessageResource:
    def __init__(self, http: HTTPClient) -> None:
        self._http = http
```

| 缺口 | 影响 |
| --- | --- |
| 没有消息模型 | 频道发送接口返回整个 `Message` 对象，目前无处承载 |
| `api.message` 空实现 | 用户只能手写 `bot._http.post(...)`，绕过类型与错误体系 |
| HTTPClient 只发 JSON | 频道发送支持 `multipart/form-data`，需要扩展 |
| 没有「被动回复」概念 | `msg_id` + `msg_seq` 的 5 分钟窗口、最多 5 次、去重规则全靠用户自己记 |
| POST 不重试规则的文档缺位 | Phase 1 只对幂等方法重试，用户需知道发送失败该不该重试（§4.3） |

## 3. 分层与契约（沿用 Phase 1）

- `api/` 只拼路径、组包体、把响应转模型；不 import aiohttp，不解析 raw 响应。
- `HTTPClient.request` 新增可选的 `form` 参数（`multipart/form-data`），其余不变。
- 依赖方向仍是 `api → http_client → token_manager`。

## 4. 传输层扩展

### 4.1 `HTTPClient.request` 的新参数

```python
FormSource = FormData | Callable[[], FormData]

async def request(
    self,
    method: str,
    path: str,
    *,
    params: Mapping[str, str | int] | None = None,
    json: Any = None,
    form: FormSource | None = None,
) -> Any:
```

- `form` 与 `json` 互斥，同时给抛 `ValueError`（英文文案：`json and form are mutually exclusive`）。
- `form` 既收现成的 `FormData`，也收工厂函数 `Callable[[], FormData]`。原因：aiohttp 的 `FormData` 是一次性流，重试时必须重建；传实例则该次请求禁用 5xx/网络异常重试与 401 重放，传工厂才可重放。
- 文件字段走 `add_field(name, data, filename=..., content_type=...)`。
- 现有 `get` / `post` 助手不变，新增 `post_form(path, *, form: Callable[[], FormData])`，只收工厂。

### 4.2 响应体为空的 DELETE

两类撤回接口都返回 `200 + {}`（群）或 `200 + 空体`（频道）。Phase 1 的 `_decode` 已覆盖：空体 → `None`、`{}` → `{}`。撤回方法统一 `-> None`，不返回 `{}`。

### 4.3 POST 不重试

Phase 1 的重试矩阵只覆盖幂等方法（GET / HEAD / PUT / DELETE）。发送消息是 POST，**不自动重试**（§8.2 说明为什么这仍然可用）。

新增 `ClientOptions.retry_post: bool = False`，默认关闭；置 `True` 时 POST 也进 5xx 与网络异常退避，但 429 仍按 `Retry-After` 处理。这个开关存在的原因：平台侧 `50055001` 明确写着「请稍后重试」，某些业务会话愿意用 `msg_seq` 兜底重复。

### 4.4 超时

发送消息沿用全局 `timeout_total = 30s`。上传富媒体可能接近这个值（5MB 直传），`upload_file` 单独用 `timeout = min(timeout_total, 60)`，不改全局配置。

## 5. 请求模型

字段来源同 Phase 1 的 6.0 准则：只收官方请求体表格里出现的字段，不做业务推导。

### 5.1 频道发送：`ChannelMessageDraft`

```python
class ChannelMessageDraft(QQModel):
    content: str | None = None
    embed: dict[str, Any] | None = None  # 结构在 Embed 页面, 本期只透传
    ark: dict[str, Any] | None = None  # 同上, Ark 结构不建模
    image: str | None = None  # 图片 URL，平台转存
    msg_id: str | None = None  # 被动回复：来自 AT_MESSAGE_CREATE
    event_id: str | None = None  # 被动回复：来自事件对象
    markdown: MessageMarkdown | None = None
    message_reference: MessageReference | None = None
```

- 序列化用 `model_dump(by_alias=True, exclude_none=True)`，`None` 字段必须消失（空串不等于不传）。
- 构造时校验「`content` / `embed` / `ark` / `image` / `markdown` 至少有一个」，否则抛 `ValueError("a channel message needs at least one of content/embed/ark/image/markdown")`。

### 5.2 群发送：`GroupMessageDraft`

```python
class GroupMessageDraft(QQModel):
    msg_type: GroupMessageType | None = None  # 0=text 2=markdown 7=media
    content: str | None = None
    markdown: MessageMarkdown | None = None
    keyboard: Keyboard | None = None
    media: MediaInfo | None = None
    message_reference: MessageReference | None = None
    msg_id: str | None = None
    event_id: str | None = None
    msg_seq: int | None = None
```

校验规则（全部来自官方「消息类型与内容不匹配」`22006` 的语义，本地先挡一层）：

| `msg_type` | 必填 | 必须为空 |
| --- | --- | --- |
| 0 | `content` | `markdown` / `media` |
| 2 | `markdown` | `content` / `ark` |
| 7 | `media.file_info` | `content` / `markdown` |

`msg_type` 为空时按内容推断：有 `media` → 7、有 `markdown` → 2、否则 0。推断结果写进包体，用户不必手填。

### 5.2.1 `MessageMarkdown`：只收未废弃的两个字段

官方群聊请求体表格里 `template_id`（integer）与 `custom_template_id`（string）都标了【已废弃】，只保留：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `content` | str | 自定义 Markdown 文本 |
| `force_verify_image_resource` | bool | 为 `true` 时图片转存失败会直接报错、消息不发出；默认 false |

模板参数 `params` 依附于已废弃的模板字段，一并弃用：自定义 Markdown 用 `content` 就够了。频道与群聊共用这个模型，因为两边字段集合完全一致；`extra="ignore"` 让旧调用方传了废弃字段也不会炸。

### 5.3 富媒体上传：三种入口，一个方法

```python
async def upload_file(
    group_openid: str,
    file_type: FileType,
    *,
    url: str | None = None,
    file_data: bytes | None = None,
    file_name: str | None = None,
    srv_send_msg: bool = False,
) -> UploadedFile:
```

- `url` 与 `file_data` 二选一，都给或都不给抛 `ValueError`。
- `file_data` 是 bytes，包体里编码成 `base64`？——**不是**。官方 `file_data` 示例给的是「图片的二进制数据」字符串，实际走 `application/json` 时需 `base64`；走 `multipart/form-data` 时传文件。本期选 **multipart**（`HTTPClient.post_form`），字段名 `file_data` + `file_name`，避免 base64 体积膨胀 33%。
- 二进制超过 5MB 抛 `ValueError("file_data must not exceed 5 MB, use url instead")`。

### 5.4 频道 multipart 直传图片

官方频道发送页给出两种请求体：`application/json` 与 `multipart/form-data`，后者用 `file_image` 字段直接传文件。

```python
async def send_message(
    self,
    channel_id: str,
    *,
    content: str | None = None,
    markdown: MessageMarkdown | None = None,
    image: str | None = None,
    file_image: bytes | None = None,
    file_name: str = "image.png",
    reply_to: str | None = None,
    event_id: str | None = None,
) -> Message:
```

- `image`（URL 转存）与 `file_image`（字节直传）互斥，同时给抛 `ValueError("image and file_image are mutually exclusive")`。
- 给了 `file_image` 时整包走 `HTTPClient.post_form`：文本字段逐个 `add_field(name, value)`，嵌套对象先 `json.dumps(..., ensure_ascii=False)` 再作为字符串字段，文件字段 `add_field("file_image", data, filename=file_name, content_type=...)`。
- `content_type` 按扩展名猜：`.png` → `image/png`、`.jpg`/`.jpeg` → `image/jpeg`、其余 `application/octet-stream`。
- 发给 `ChannelMessageDraft` 的 JSON 里不出现 `file_image`，它不是 JSON 字段；`ChannelMessageDraft` 因此保持纯 JSON 语义。

### 5.5 按钮键盘：`keyboard` 基础支持

官方 `keyboard` 有两种形态：申请模板后的 `{"id": "123"}`，与内邀开通的自定义 `content.rows`。本期两种都建模，只做到「能正确序列化并通过类型检查」：最多 5 行、每行最多 5 个按钮。

```python
class Keyboard(QQModel):
    id: str | None = None
    content: KeyboardContent | None = None


class KeyboardContent(QQModel):
    rows: list[KeyboardRow]


class KeyboardRow(QQModel):
    buttons: list[Button]


class Button(QQModel):
    id: str | None = None
    render_data: ButtonRenderData
    action: ButtonAction


class ButtonRenderData(QQModel):
    label: str
    visited_label: str
    style: ButtonStyle = ButtonStyle.GREY


class ButtonAction(QQModel):
    type: ButtonActionType
    data: str
    permission: ButtonPermission
    unsupport_tips: str = "此操作暂不支持"
    reply: bool = False
    enter: bool = False
    anchor: int | None = None


class ButtonPermission(QQModel):
    type: ButtonPermissionType
    specify_user_ids: list[str] | None = None
    specify_role_ids: list[str] | None = None
```

| 枚举 | 取值 |
| --- | --- |
| `ButtonStyle` | `GREY = 0`、`BLUE = 1` |
| `ButtonActionType` | `LINK = 0` 跳转、`CALLBACK = 1` 回调、`COMMAND = 2` 指令 |
| `ButtonPermissionType` | `SPECIFIED_USERS = 0`、`ADMIN_ONLY = 1`、`EVERYONE = 2`、`SPECIFIED_ROLES = 3`（仅频道） |

校验只做两件：

- `Keyboard` 的 `id` 与 `content` 二选一，都给或都不给抛 `ValueError("keyboard needs either id or content")`。
- `rows` 与 `buttons` 的数量上限 5/5 用 `Field(max_length=5)` 交给 pydantic。

`reply` / `enter` / `anchor` 只在 `COMMAND` 下有效、`anchor` 只在手机端单聊可用，这类「依赖运行环境」的规则写进 docstring，不进校验，免得挡住平台其实接受的组合。官方标已弃用的 `action.click_limit`、`action.at_bot_show_channel_list` 不收。

## 6. 响应模型

### 6.1 频道 `Message`

频道发送接口「返回 Message 对象」，官方响应示例字段如下（`server-inter/channel/message/send.html`）：

| 字段 | 类型 | 示例值 |
| --- | --- | --- |
| `id` | str | `xxxxxx` |
| `channel_id` | str | `xxxxxx` |
| `guild_id` | str | `xxxxxx` |
| `content` | str | `<@!1234>hello world` |
| `timestamp` | datetime | `2021-05-13T14:45:45+08:00` |
| `tts` | bool | `false` |
| `mention_everyone` | bool | `false` |
| `author` | `User` | 内嵌 user 对象，`bot: true` |
| `embeds` | list | `[{}]` |
| `pinned` | bool | `false` |
| `type` | int | `0` |
| `flags` | int | `0` |

模型 `Message` 只收录这 12 个字段，全部 `Field(alias=...)`，`embeds` 用 `list[dict[str, Any]]`（示例里是空对象，结构体在「Embed 消息」页面，本期不解析）。事件里多出来的 `attachments` / `mentions` / `edited_timestamp` 等字段靠 `extra="ignore"` 忽略，等 Phase 3 处理事件时再补。

### 6.2 群 `GroupMessageReceipt`

群发送接口**不返回完整消息**，只有：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | str | 消息 ID，用于撤回 |
| `timestamp` | datetime | RFC3339 东八区 |
| `ext_info.ref_idx` | str | 引用消息索引 |

模型拆两层：

```python
class MessageExtInfo(QQModel):
    ref_idx: str = Field(alias="ref_idx")


class GroupMessageReceipt(QQModel):
    id: str = Field(alias="id")
    timestamp: datetime = Field(alias="timestamp")
    ext_info: MessageExtInfo | None = Field(alias="ext_info", default=None)
```

`ext_info` 在 `srv_send_msg=false` 的普通发送里也可能不返回，所以可选。

### 6.3 群 `UploadedFile`

| 字段 | 类型 | 出现条件 |
| --- | --- | --- |
| `file_uuid` | str | 总是 |
| `file_info` | str | 总是，`ttl` 到期作废 |
| `ttl` | int | 总是，0 表示长期 |
| `id` | str | 仅 `srv_send_msg=true` |
| `raw_url` | str | 仅分片上传合并且 `file_type` ∈ {1,2,3} |

### 6.4 快照

`tests/data/` 新增：

| 快照 | 来源页面 | 保真度 |
| --- | --- | --- |
| `channel_message.json` | `server-inter/channel/message/send.html` 响应示例 | 逐字，含 `"embeds": [{}]` 这种空对象 |
| `group_message_receipt.json` | `autogen/api/v2_groups_group_openid_messages.post.html` 响应示例 | 字段与层级照抄，示例里的长 ID 换成 `xxxxxx` |
| `group_file.json` | `autogen/api/v2_groups_group_openid_files.post.html` 响应示例 | 同上 |

后两个快照的标识符是占位值：官方示例用 `xxxxxx` 表示任意字符串，直接照抄反而会让「解析成功」看起来像巧合。字段集合与嵌套关系保持与示例一致，`test_message_models.py` 用 `missing_fields()` 守住「示例有、模型也必须有的字段」。

## 7. 资源层接口

### 7.1 `ChannelResource`

```python
async def send_message(
    self,
    channel_id: str,
    *,
    content: str | None = None,
    markdown: MessageMarkdown | None = None,
    image: str | None = None,
    file_image: bytes | None = None,
    file_name: str = "image.png",
    reply_to: str | None = None,
    event_id: str | None = None,
) -> Message
async def recall_message(self, channel_id: str, message_id: str, *, hide_tip: bool = False) -> None
```

- 显式关键字参数，不用 `**kwargs` 透传：调用方能看见全部可传项，`mypy` 也能检查。
- `markdown` 与 `content` 同传时只发 `markdown`（官方语义：Markdown 消息不带 content）。
- `recall_message` 的 `hidetip` 是 query，不是包体。

### 7.2 `GroupResource`

```python
async def send_message(
    self,
    group_openid: str,
    *,
    content: str | None = None,
    markdown: GroupMarkdown | None = None,
    media: MediaInfo | None = None,
    keyboard: Keyboard | None = None,
    reply_to: str | None = None,
    event_id: str | None = None,
    msg_seq: int | None = None,
) -> GroupMessageReceipt
async def recall_message(self, group_openid: str, message_id: str) -> None
async def upload_file(self, group_openid: str, file_type: FileType, /, *, url: str | None = None, file_data: bytes | None = None, file_name: str | None = None, srv_send_msg: bool = False) -> UploadedFile
```

### 7.3 `ApiClient`

`channel` 与 `group` 各加两个方法，`group` 另有 `upload_file`。

`message` 域本期仍是占位，但不再是空类：留一个 `reply()` 方法标出将来的入口（D3 结论）：

```python
class MessageResource:
    def __init__(self, http: HTTPClient) -> None:
        self._http = http

    async def reply(self, message_id: str, content: str, /) -> None:
        raise NotImplementedError("message.reply is available from the event layer in phase 3")
```

不用静默 `pass`：`pass` 会让调用方以为消息已经发出去，等到线上「机器人不回话」才发现。签名与返回类型现在钉死，Phase 3 只换实现。

## 8. 被动回复、去重与频控

### 8.1 被动回复窗口

| 场景 | 有效期 | 每条消息可回复次数 |
| --- | --- | --- |
| 频道 | 5 分钟 | 未限制 |
| QQ 群 | 5 分钟 | 5 次 |

SDK 侧只做两件事：把 `msg_id` 作为 `reply_to` 参数透传；文档写清过期错误码（频道 `304103` / 群 `40034005`、`40034128`）。

### 8.2 `msg_seq` 与去重

- 相同 `msg_id` + `msg_seq` 重复发送会失败（群侧 `40054005 消息被去重`）。
- `send_message(..., reply_to=msg_id)` 且未给 `msg_seq` 时，SDK 传 `msg_seq=1`（官方默认值）。
- **不做**进程内自动递增：一个 `msg_id` 分布在多个进程/重启后无法共享计数，自动递增会给出「以为去重了、其实没有」的错觉。要多次回复就自己传 `msg_seq=2`、`3`。

### 8.3 频控

| 场景 | 限制 |
| --- | --- |
| 频道子频道 | 5 条/秒（主动与被动合计）；主动每天每子频道 20 条、每天最多 2 个子频道 |
| QQ 群 | 接口 100 QPS；主动消息 Bot 维度 60 qpm（认证）/ 30 qpm（未认证），单群 20 qpm、1000 条/天 |
| 群撤回 | 10 QPS；2 分钟内 |

不内置限流器（D6：本期只写文档，令牌桶留到后续版本）：限流器需要跨进程状态、且会把「发送慢」的责任从业务挪到 SDK。文档给出数字，超限时平台返回 `40034100` / `40054005` 等明确错误码。`send_message` 的 docstring 里重复一遍「每个子频道每秒最多 5 条」这条最常踩的线。

## 9. 错误

沿用 Phase 1 的 `APIError`，新增两类判据：

- `RETRYABLE_CODES` 补 `{50055001, 850027, 40093001}`（三处文档都写「请稍后重试」）；它们只在 `retry_post=True` 时生效。
- 消息场景的高频码进文档表格，不进枚举：`22006`、`304061`、`304103`、`40034005`、`40034100`、`40034128`、`40054002`、`40054005`、`40054007`、`40054010`、`40061001`、`40062003`、`40064004`、`850018`、`850019`、`850031`。

## 10. 目录结构（新增部分）

```text
src/qqbot/
├── api/
│   ├── channel.py          # 加 send_message（JSON 与 multipart）/ recall_message
│   ├── group.py            # 加 send_message / recall_message / upload_file
│   └── message.py          # reply() 占位，抛 NotImplementedError
├── model/
│   ├── message.py          # Message / MessageExtInfo / GroupMessageReceipt
│   ├── draft.py            # ChannelMessageDraft / GroupMessageDraft / 校验
│   ├── media.py            # MediaInfo / FileType / UploadedFile
│   └── keyboard.py         # Keyboard / Button / ButtonAction / 三个枚举
tests/
├── data/
│   ├── channel_message.json
│   ├── group_message_receipt.json
│   └── group_file.json
├── test_message_api.py     # 频道发送（JSON + multipart）、撤回
├── test_group_message_api.py
├── test_keyboard.py        # 键盘序列化与 5×5 上限
└── test_message_models.py
```

## 11. 测试策略

MockServer 已经能断言「请求方法 + 路径 + query」，本期新增两项能力：

1. `RecordedCall.body` —— 记录请求体（JSON 与 multipart 都要），供断言 `msg_type`、`msg_seq`、`content` 是否按预期出现/消失。
2. multipart 断言只校验字段名与值，不校验 boundary 顺序。

用例表（14 条）：

| 用例 | 断言 |
| --- | --- |
| `test_channel_send_text` | POST `/channels/{id}/messages`，body 只有 `content` 与 `msg_id`，响应解析成 `Message` |
| `test_channel_send_requires_content` | 无内容字段抛 `ValueError`，且未发出请求 |
| `test_channel_send_markdown_excludes_content` | `markdown` 与 `content` 同传时 `content` 被丢弃 |
| `test_channel_send_multipart_file_image` | `Content-Type` 以 `multipart/form-data` 开头，含 `file_image` 字段与 `content` 字段，响应仍是 `Message` |
| `test_channel_send_rejects_image_and_file` | `image` 与 `file_image` 同传抛 `ValueError`，未发请求 |
| `test_channel_recall_uses_query_flag` | `DELETE ...?hidetip=true`，返回 `None` |
| `test_group_send_infers_msg_type` | 只给 `media` → 包体 `msg_type == 7`；只给 `markdown` → `2`；只给 `content` → `0` |
| `test_group_send_reply_defaults_seq` | `reply_to` 给定、`msg_seq` 未给 → 包体 `msg_seq == 1` |
| `test_group_send_explicit_seq` | `msg_seq=3` 原样透传 |
| `test_group_send_keyboard_payload` | `keyboard` 对象按官方嵌套形状序列化，`rows` 与 `buttons` 结构不被压平 |
| `test_group_recall_returns_none` | `DELETE /v2/groups/{gid}/messages/{mid}`，响应 `{}` → `None` |
| `test_upload_by_url_sends_json` | `file_type=1` + `url`，包体只有 `file_type`/`url`/`srv_send_msg`，解析出 `ttl` |
| `test_upload_binary_is_multipart` | `Content-Type` 以 `multipart/form-data` 开头，字段含 `file_data; filename="a.silk"` 与 `file_name` |
| `test_upload_binary_with_srv_send_msg` | `srv_send_msg=True` 时包体带 `true`，响应里的 `id` 被解析 |
| `test_upload_rejects_oversize` | `file_data` 超 5MB 抛 `ValueError`，未发请求 |
| `test_upload_needs_exactly_one_source` | 都不给与都给分别抛 `ValueError`，未发请求 |
| `test_upload_binary_needs_file_name` | 二进制但缺 `file_name` 抛 `ValueError`，未发请求 |
| `test_post_not_retried_by_default` | 500 后直接抛 `APIError`，只发生一次请求 |
| `test_keyboard_requires_id_or_content` | 都不给与都给分别抛 `ValueError` |
| `test_keyboard_rejects_more_than_five_rows` | 6 行触发 `ValidationError` |
| `test_message_reply_placeholder` | `bot.api.message.reply(...)` 抛 `NotImplementedError` |

实际是 21 条：上表按文件归组，`test_keyboard_*` 归 `tests/test_keyboard.py`，`test_post_not_retried_by_default` 归 `tests/test_http_client.py`，`test_message_reply_placeholder` 归 `tests/test_message_api.py`，`test_upload_*` 归 `tests/test_group_file_api.py`。

## 12. 切片

| 切片 | 内容 | 验收 |
| --- | --- | --- |
| T1 | `model/message.py`、`model/media.py`、`model/keyboard.py`、`model/draft.py` + 三个快照 + `test_message_models.py` / `test_keyboard.py` | 模型用例全绿（已完成 2026-10-26，11 用例） |
| T2 | `HTTPClient.request(form=...)` 与 `post_form`、`ClientOptions.retry_post`、`RecordedCall.body` | `test_http_client.py` 新增 3 用例（已完成 2026-10-26） |
| T3 | `ChannelResource.send_message`（JSON + multipart）/ `recall_message`、`MessageResource.reply` 占位 + 7 用例 | 频道发送端到端可跑（已完成 2026-10-26，`tests/test_message_api.py`） |
| T4 | `GroupResource.send_message`（含 keyboard）/ `recall_message` + 7 用例 | 群发送端到端可跑（已完成 2026-10-26，`tests/test_group_message_api.py`） |
| T5 | `GroupResource.upload_file`（URL 与二进制）+ 6 用例 | 上传后能拿到 `file_info` 并发出 `msg_type=7`（已完成 2026-10-26，`tests/test_group_file_api.py`） |
| T6 | README / ROADMAP / 示例脚本 / 版本号 0.3.0 | 门禁全绿（已完成 2026-10-26，README「发消息」节 + `examples/hello.py` 发送与撤回演示） |

## 13. 版本

`0.2.x` → `0.3.0`：新增公开 API，无破坏性变更（`get_me` 的 deprecated 保持到 0.4）。

## 14. 拍板结论（2026-10-26 已定）

| # | 问题 | 结论 |
| --- | --- | --- |
| D1 | 频道发送是否支持 `multipart/form-data` + `file_image` 直传 | **支持**。`file_image` 走 `post_form`，与 `image` URL 互斥（§5.4） |
| D2 | 群 `keyboard` 是否做完整模型 | **做基础支持**：`{"id": ...}` 模板与 `content.rows` 自定义两形态，上限 5 行 × 5 按钮（§5.5）；`Modal`、交互回调与点击统计等扩展留到后续版本 |
| D3 | 是否引入 `msg.reply(...)` 门面 | **本期不引入**，但留占位方法。现在没有事件对象，`api/message.py` 的 `reply()` 抛 `NotImplementedError`，签名先钉死（§7.3） |
| D4 | `retry_post` 是否默认开启 | **默认关闭**；要重试的人在 `ClientOptions` 里打开（§4.3） |
| D5 | 群分片上传是否本期做 | **不做**，URL 与 ≤5MB 二进制已覆盖图片/语音场景 |
| D6 | 消息频控是否做客户端令牌桶 | **本期只做文档**，同 D2 一样留到后续版本扩展（§8.3） |
