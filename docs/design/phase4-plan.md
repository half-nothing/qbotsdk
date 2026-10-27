# Phase 4 计划：补全与发布（v0.5 → v1.0）

## 1. 起点与目标

Phase 1–3 已关账，当前 `v0.4.0` 覆盖：REST 只读查询（频道/子频道/成员/身份组/群）、频道与群消息的发送与撤回、群富媒体上传、WebSocket 网关（Identify / 心跳 / Resume / 退避重连）、事件分发（`async-event-bus` 薄门面）、Webhook（签名校验 + 开箱即用服务器）。

Phase 4 的目标不是再堆接口，而是把「机器人能正常运营」缺的三块补齐，然后具备发布条件：

1. **单聊（C2C）全链路** —— 现在只能收群 @消息，单聊一条都没有；
2. **主动消息** —— 现在只能被动回复，过期就没法再发；
3. **交互闭环** —— 键盘按钮已经能发出去，但点回来没有回调事件，等于半截功能。

收尾再补长尾接口与工程化发布。

## 2. 现状差距

| 能力 | 现状 | 缺口 |
| --- | --- | --- |
| 单聊消息 | 无 | 发送、撤回、富媒体上传、`C2C_MESSAGE_CREATE` 事件 |
| 主动消息 | 无 | 群/单聊不带 `msg_id` 的发送路径；频控与配额 |
| 频道 @消息 | 只有频道 REST 查询 | `AT_MESSAGE_CREATE` 事件与被动回复 |
| 按钮交互 | 只能发键盘 | `INTERACTION_CREATE` 回调事件 |
| 长尾接口 | 无 | 论坛 threads、音频控制、表情表态 |
| 发布 | 无远程仓 | PyPI 发布、`CHANGELOG.md`、版本策略 |

## 3. 目标一：单聊（C2C）全链路

### 3.1 接口事实（官方文档）

| 项 | 值 | 来源 |
| --- | --- | --- |
| 发送 | `POST /v2/users/{user_openid}/messages`，100 QPS | [发送单聊消息](https://bot.qq.com/wiki/develop/api-v2/autogen/api/v2_users_user_openid_messages.post.html) |
| 撤回 | `DELETE /v2/users/{user_openid}/messages/{message_id}` | 同上站点「撤回单聊消息」 |
| 上传 | `POST /v2/users/{user_openid}/files` | 同上站点「单聊富媒体」 |
| 被动有效期 | 60 分钟，每条消息最多回复 4 次 | 发送单聊消息页 |
| 主动频控 | Bot 维度：企业/身份证认证 10 qps，未认证 5 qps + 30 qpm；单关系 20 qpm，每个好友每天 1000 条 | 同上 |
| 互动召回 | `is_wakeup=true`，30 天内四个周期各一条（当天 / 1–3 天 / 3–7 天 / 7–30 天），与 `msg_id`、`event_id` 互斥 | 同上 |

请求体字段：`msg_type`(0 文本 / 2 Markdown / 6 输入中 / 7 富媒体)、`content`、`markdown`、`keyboard`、`msg_id`、`event_id`、`msg_seq`、`media.file_info`、`message_reference.message_id`、`is_wakeup`、`input_notify{input_type=1, input_second<=60}`。

### 3.2 事件事实

`C2C_MESSAGE_CREATE`（Intent `GROUP_AND_C2C_EVENT` 1<<25）字段：`id`、`author`（User，`user_openid` 有值）、`content`、`timestamp`、`message_type`(0 文本 / 3 卡片 / 101 并行 / 102 聊天记录 / 103 引用)、`message_scene`（`source` + `ext` 的 `k=v` 列表）、`attachments`、`ark_data`、`msg_elements`。官方同样警告「相同 `msg_id` 可能重复推送」。

### 3.3 设计要点

- `model/draft.py` 新增 `UserMessageDraft`（`msg_type` 0/2/6/7，`input_notify` 只在 6 生效），不复用群草稿：群侧 `msg_type` 是 0/2/7、单聊多一个 6。
- `api/user.py` 的 `UserResource` 扩成「自己 + 任意用户」两种路径：`me()` 走 `/users/@me`，新增 `messages` 域走 `/v2/users/{user_openid}/messages`。为避免 `me()` 与 `openid` 参数混淆，单聊发送放新类 `api/user_message.py::UserMessageResource`。
- 新增 `C2CMessageCreate`，`reply()` 与群事件同形，走 `UserMessageResource.reply`。
- `EventModel` 里 `reply()` 的实现下沉成 `GroupAtMessageCreate.reply` 与 `C2CMessageCreate.reply` 两个方法，不抽公共基类（两者签名不同：单聊多 `input_notify`，且 `is_wakeup` 只在主动场景出现）。

## 4. 目标二：主动消息

「主动」不是新接口，是**不带 `msg_id` 的发送**。真正的工作量在配额：

- 官方把频控写在错误码里（`40034100` 主动消息发送超过频控限制、`40054005` 消息被去重、`40034128` 被动回复时间或次数超限），SDK 不该盲目重试这三类。
- 设 `ClientOptions.respect_rate_limits: bool = True` 时，`send_message` 在**同一个 openid** 上做轻量令牌桶（群 20 qpm、单聊 20 qpm，默认从官方值起步，可用 `rate_limits` 覆盖），超限在本地抛 `RateLimitExceededError` 而不是打到服务端换 40034100。
- 令牌桶只在**进程内**有效，多实例部署仍会撞服务端限流，文档必须写清楚这一点（不承诺分布式限流）。
- `msg_seq`：主动消息不需要 `msg_id`，也就不需要 `msg_seq`；被动回复的 `msg_seq` 自增已有实现，Phase 4 只补「同一条消息第 5 次回复」的本地拦截（抛 `ValueError("passive reply limit reached")`），避免用户白等 `40034128`。

## 5. 目标三：频道 @消息与按钮交互

| 事件 | Intent | 状态 |
| --- | --- | --- |
| `AT_MESSAGE_CREATE` | `PUBLIC_GUILD_MESSAGES` 1<<30 | 官方页待取证（wiki 会跳转到启动接入页） |
| `INTERACTION_CREATE` | `INTERACTION` 1<<26 | 需确认回调接口 `PUT /interactions/{interaction_id}` 的请求体 |

设计方向（取证后细化）：

- `AT_MESSAGE_CREATE` → `AtMessageCreate`，`reply()` 走 `ChannelResource.send_message(reply_to=...)`。
- `INTERACTION_CREATE` → `InteractionCreate`，带 `button_id`/`button_data`/`message_id`，提供 `ack()`（回复一条消息完成回调）与 `defer()`（先 ACK 再异步回）。

这两个事件都需要补 Intents 位与 `EVENT_MODELS` 映射；因为是「新事件类型 + 新回复路径」，代码增量小，主要成本是取证。

## 6. 目标四：长尾接口

按「有人用才做」的原则排优先级，不追求全覆盖：

| 优先级 | 接口 | 理由 |
| --- | --- | --- |
| 高 | 表情表态 `PUT /channels/{channel_id}/messages/{message_id}/reactions/{type}/{id}` | 几行代码，群里常用 |
| 中 | 论坛 threads 列表与发帖 | 频道场景的独立子域，需先取证 |
| 低 | 音频控制（`/channels/{channel_id}/audio`） | 小众，且有状态机 |

## 7. 目标五：发布

- `CHANGELOG.md`：按 Phase 回溯整理 0.1.0 → 0.4.0，之后按 Keep a Changelog 维护。
- 版本策略：0.x 期间 minor 可破坏（已在 Phase 3 的 `get_me` 弃用处示范），1.0 起严格 semver。
- PyPI：用 Trusted Publishing（OIDC）而不是长期 token，`release.yml` 由 tag 触发，先 `pdm build` 再 `pdm publish`。
- 仓库仍无 remote：**这条得先有 GitHub 仓库**，否则 Actions 与信任发布都只是文件。

## 7.5 文档站（VitePress）

用户明确要求：文档站一定要有，且习惯用 VitePress，所以提前规划、分两步落地（骨架与指南早做，API 自动生成等接口稳定再接）。

### 7.5.1 选型与位置

- 站点生成器 `vitepress@1.6.4`（本机 Node 24.20 / pnpm 11.24 已就绪）；不用 mkdocs，避免两套 Markdown 生态。
- 站点根就用现有 `docs/`，配置放 `docs/.vitepress/`；`docs/design/` 只做仓库内留档，**不进站点**（用户 2026-10-27 明确要求），在 `srcExclude` 里排除，导航与侧栏也不挂入口。
- 语言 `zh-CN`，搜索用 VitePress 自带 local provider（不引 Algolia，省申请与外部依赖）。

### 7.5.2 目录结构

```text
docs/
├─ index.md                # 首页: hero + 特性 + 三行上手代码
├─ guide/                  # 手写指南
│  ├─ quickstart.md        # 安装、鉴权、收第一条消息
│  ├─ auth.md              # 凭证获取与刷新、QQBot 前缀
│  ├─ channel.md           # 频道/子频道/成员/身份组
│  ├─ group.md             # 群信息、成员、禁言
│  ├─ message.md           # 发送、撤回、富媒体、频控与 msg_seq
│  ├─ event.md             # 网关、intents、handler、reply()
│  └─ webhook.md           # 签名校验、服务器、TLS、反向代理
├─ api/                    # 由脚本生成, 不手写
├─ design/                 # 设计文档, 仅仓库留档, srcExclude 排除
└─ .vitepress/config.mts
```

`docs/design/` 不进站点后，`srcExclude: ["design/**"]` 要同时保证两点：站内没有任何链接指向 `design/`（否则构建告警或 404），以及 `gen-api` 生成物不落在 `design/` 下。

### 7.5.3 API 参考的生成方式

手写 API 页一定会和代码漂移，所以 `docs/api/` 全部由脚本生成：

- `scripts/gen_api_docs.py` 用 `griffe`（2.4.1）静态解析 `src/qqbot`，每个模块一页：类、方法签名、docstring、pydantic 模型的字段表（字段名 + 类型 + 别名）。
- 生成命令 `pdm run gen-api`，输出到 `docs/api/`。
- CI 加一条 `pdm run gen-api --check`：重新生成到临时目录并与已提交文件比较，不一致即红。思路与 `ruff format --check` 一致，防止「改了代码忘了更文档」。
- 若 griffe 2.x 的 API 在实现时出现坑，退回到 `ast` + `inspect.getdoc` 的百行自写生成器，不引入第二个依赖；评估成本控制在半天内。

### 7.5.4 构建与部署

- 本地：`pnpm docs:dev`（热更新）、`pnpm docs:build`、`pnpm docs:preview`；三条命令同时写进 `Makefile` 的 `docs-dev`/`docs-build`。
- CI：`.github/workflows/docs.yml`，`main` 推送与手动触发，`pnpm install --frozen-lockfile` → `pnpm docs:build` → `actions/deploy-pages@v4`。
- `base`：GitHub Pages 用 `/qq-bot-sdk/`，本地 dev 用 `/`，按 `process.env.GITHUB_ACTIONS` 区分。
- 前置：仓库必须已有 remote 并启用 Pages（与 P6 同一条前置）。

### 7.5.5 版本化

0.x 期间只维护 main 一份文档，不做多版本共存；1.0 之后再按 tag 出 `v1.x` 站点（届时再评估 VitePress 的版本插件或自建二级路径），现在不提前引依赖。

## 8. 切片

| 切片 | 内容 | 验收 |
| --- | --- | --- |
| P1 | 单聊发送 + 撤回 + 上传（`api/user_message.py`、`UserMessageResource`、`UserMessageDraft`） | `test_user_message_api.py` 全绿 |
| P2 | `C2C_MESSAGE_CREATE` 事件 + `reply()` | `test_c2c_event.py` 全绿 |
| P3 | 主动消息配额层（`RateLimiter`、`respect_rate_limits`、被动回复次数拦截） | `test_rate_limit.py` |
| P4 | `AT_MESSAGE_CREATE` + `INTERACTION_CREATE`（先取证） | 两个事件的快照与用例 |
| P5 | 表情表态 + 论坛/音频按需 | 各一个用例 |
| P6 | `CHANGELOG.md`、`release.yml`、PyPI | tag 触发后能在 PyPI 看到版本 |
| P7 | VitePress 文档站：骨架 + 七篇指南 + API 自动生成 + Pages 部署（`design/` 不进站） | 本地 `docs:build` 通过且产物里没有 `design/`，CI 的生成物校验为绿 |

进度：P1 已完成（2026-10-27），新增 `api/user_message.py`、`UserMessageDraft`、`UserMessageType`、`InputNotify`；单聊上传只实现 `url` 方式，二进制直传的字段表官方没给，未取证不实现。

P2 已完成（2026-10-27）：新增 `C2CMessageCreate`（`C2CUser` 作者、`msg_elements` 递归、`message_scene`）与事件上的 `reply()`；`MessageElement.content` 按官方改成 `str`，元素作者单独用 `ElementAuthor`（元素层不保证 `id`），`ARKData` 补卡片数据；`tests/data/c2c_message_create.json` 与 `c2c_message_create_quote.json` 两个快照，门禁 154 passed / mypy 62 / format 70。

## 9. 已拍板（2026-10-27）

| 编号 | 问题 | 决定 |
| --- | --- | --- |
| D1 | 单聊是否拆独立 `UserMessageDraft` | 拆。群侧 `msg_type` 是 0/2/7，单聊多一个 6（输入中状态），复用会把两套枚举塞进一个校验器 |
| D2 | 是否内置本地限流 | 内置，默认按官方值、可关；文档写明只在本进程生效，不承诺分布式 |
| D3 | `INTERACTION_CREATE` 是否本期做 | 做。否则键盘按钮只能发不能接，功能半截 |
| D4 | 发布用 Trusted Publishing 还是 token | Trusted Publishing（OIDC），无长期密钥 |
| D5 | 文档站选型 | VitePress，提前规划、分两步落地，详见 §7.5 |


## 10. 风险

- **取证依赖**：`AT_MESSAGE_CREATE`、`INTERACTION_CREATE`、论坛 threads 的官方页在 wiki 上不稳定（部分路径 404 回落首页），P4/P5 可能卡在文档缺失；届时以「未取证不实现」为原则，不猜字段。
- **频控误判**：本地令牌桶与服务端配额（认证状态、好友数）不同步，可能本地放行但服务端仍 40034100；错误码仍要走 `APIError`，不要因为本地限流就吞掉服务端错误。
- **单聊可用性**：单聊需要先有好友关系（`40054004`），沙箱环境难以端到端验证，测试只能到 mock 层。
- **无 remote**：P6 的前置是建仓库并推送，否则发布链路无法验证。

## 11. 引用

- [发送单聊消息](https://bot.qq.com/wiki/develop/api-v2/autogen/api/v2_users_user_openid_messages.post.html)
- [单聊消息事件](https://bot.qq.com/wiki/develop/api-v2/autogen/event/c2c_message_create.html)
- [消息收发概述](https://bot.qq.com/wiki/develop/api-v2/server-inter/message/overview.html)
- [群@机器人消息](https://bot.qq.com/wiki/develop/api-v2/autogen/event/group_at_message_create.html)
