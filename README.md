# qbotsdk

非官方 QQ 机器人 SDK

[![Python](https://img.shields.io/badge/Python-3.12%2B-blue)](https://www.python.org/)
[![License](https://img.shields.io/github/license/half-nothing/qbotsdk)](./LICENSE)
[![PyPI](https://img.shields.io/pypi/v/qbotsdk)](https://pypi.org/project/qbotsdk/)

## 特性

- **全异步**: 基于 `asyncio` 与 `aiohttp`, 所有接口均为异步接口。
- **登录态自动维护**: `access_token` 自动换取、缓存、到期前刷新。
- **连接与重连**: WebSocket 适配器自动心跳、断线重连与 Resume。
- **接入方式可插拔**: 默认走 WebSocket 长连接, 也可以换成 Webhook 回调, 或自己实现 `Adapter`。
- **消息即对象**: 收到的事件可以直接 `await event.reply(...)`。
- **命令与权限**: `Router` 用前缀树匹配命令, 支持模板参数、`--` 选项与子路由 `include`;权限键按操作拆分, 内置
  `/permission` 管理命令, 存储可选内存、文件、Redis 或关系库。
- **按钮回调**: `@router.button` 把按钮点击路由到带 pydantic 载荷的处理器, `ack` 策略自动回应客户端, 不必自己调
  `respond`。
- **容错内置**: 429 按 `Retry-After` 重试, 幂等请求遇 5xx 与网络异常退避重试, 本地限流分会话速率、会话日配额与机器人总速率三层,
  错误统一成 `QQBotError` 体系。
- **原始报文兜底**: 每个模型都带 `raw`, 官方新增字段时可以直接取用, 不必等 SDK 更新。
- **类型完整**: pydantic v2 模型、全量类型标注、随包分发 `py.typed`。

## 安装

包名与导入名均为 `qbotsdk`, 要求 Python 版本 >= 3.12。

```bash
pip install qbotsdk
uv add qbotsdk           # uv 项目里加依赖
uv pip install qbotsdk   # 或直接装进当前环境
```

要从源码安装

```bash
git clone https://github.com/half-nothing/qbotsdk.git
cd qbotsdk

pip install -e .         # 可编辑模式, 改完立刻生效
uv pip install -e .      # uv 同理
```

## 快速开始

```python
import asyncio
import os

from qbotsdk import Bot


async def main() -> None:
    # https://q.qq.com/qqbot/dashboard/manage
    # 进入上方网站管理机器人, 在开发设置中找到“AppID 接入凭证”卡片
    # 将环境变量QQ_BOT_APP_ID设为获取到的AppID
    # 将环境变量QQ_BOT_APP_SECRET设为获取到的AppSecret
    # 如果您选择直接替换对应内容, 请不要将携带敏感信息的文件提交到仓库
    async with Bot(
        app_id=os.environ["QQ_BOT_APP_ID"],
        app_secret=os.environ["QQ_BOT_APP_SECRET"],
    ) as bot:
        me = await bot.api.user.me()
        print(f"登录成功: {me.username}")

        async for guild in bot.api.user.iter_guilds():
            channels = await bot.api.guild.channels(guild.id)
            print(f"{guild.name}: {len(channels)} 个子频道")


asyncio.run(main())
```

## 接收事件

默认走 WebSocket 长连接

```python
import asyncio

from async_event_bus import EventContext

from qbotsdk import Bot
from qbotsdk.model.event import C2CMessageCreate, GroupAtMessageCreate, InteractionCreate


async def main() -> None:
    # 认证信息的具体获取方式请查看“快速开始”章节
    async with Bot(app_id=..., app_secret=...) as bot:

        @bot.on(GroupAtMessageCreate)
        async def on_group_at(ctx: EventContext[GroupAtMessageCreate]) -> None:
            await ctx.event.reply("收到: " + ctx.event.content)

        @bot.on(C2CMessageCreate)
        async def on_c2c(ctx: EventContext[C2CMessageCreate]) -> None:
            await ctx.event.reply("收到: " + ctx.event.content)

        @bot.on(InteractionCreate)
        async def on_interaction(ctx: EventContext[InteractionCreate]) -> None:
            if ctx.event.needs_response:
                await ctx.event.respond()  # 不回应客户端会一直 loading

        await bot.run()  # 启动并阻塞到 Ctrl+C 或 SIGTERM


asyncio.run(main())
```

bot的`adapter`参数默认为`WebSocketAdapter`, 可以显式指定为`WebhookAdapter`

也可以自行实现`Adapter`从而扩展更多接入方式, 自行实现的`Adapter`需要继承`qbotsdk.adapter.Adapter`并实现两个抽象方法

`WebSocketAdapter`的会话状态默认存在内存里  
如果想关闭后自动续连, 可以在构造`WebSocketAdapter`的时候传递参数`session_storage=`  
可选值为`MemorySessionStorage`, `FileSessionStorage`, `RedisSessionStorage`, 默认为`MemorySessionStorage`

会话存档会连同 `intents` 一起记录。重启时如果存档的 `intents` 与当前配置不同, SDK 会丢弃这份存档并重新 Identify, 避免
Resume 进一个订阅位不同的旧会话;旧版本写下的存档没有该字段, 解析为 0, 与当前配置不同时同样会被丢弃。

```python
from qbotsdk.adapter import WebSocketAdapter
from qbotsdk.storage import FileSessionStorage

# 若不传存储路径, 默认路径为软件运行目录下的.session.json文件
WebSocketAdapter(session_storage=FileSessionStorage())

# Redis 在可选依赖里, 使用前需要先安装qbotsdk[redis]
from qbotsdk.storage import RedisSessionStorage

# 给完整地址
WebSocketAdapter(session_storage=RedisSessionStorage.from_url("redis://:pwd@10.0.0.5:6379/2"))

# 或者只给零件, 地址由SDK拼
storage = RedisSessionStorage.from_url(host="10.0.0.5", port=6379, password="pwd", db=2)
WebSocketAdapter(session_storage=storage)

# Unix domain socket, 以及指定RESP协议版本
RedisSessionStorage.from_url(unix_socket="/var/run/redis/redis.sock", db=2, protocol=3)
```

也可以直接把现成的Redis客户端交给SDK

```python
# 特别注意, SDK需要的Redis实例全限定名是redis.asyncio.Redis
from redis.asyncio import Redis

from qbotsdk.storage import RedisSessionStorage

storage = RedisSessionStorage(Redis(host="10.0.0.5", port=6379))
```

### Webhook 接入

在[QQ机器人管理后台](https://q.qq.com/qqbot/dashboard/manage)填好回调地址并勾选要监听的事件后,
事件就改走 HTTP 推送, 代码层面仅需把适配器换成 `WebhookAdapter`:

```python
from qbotsdk import Bot
from qbotsdk.adapter import WebhookAdapter

bot = Bot(
    # 认证信息的具体获取方式请查看“快速开始”章节
    app_id=...,
    app_secret=...,
    adapter=WebhookAdapter(
        "同app_secret",
        port=8443,
        path="/qbotsdk",
        certfile="certs/fullchain.pem",
        keyfile="certs/privkey.pem",
    ),
)
await bot.start()
```

没有公网地址时用反向代理或内网穿透把请求转到本机, 务必原样透传 body 和两个签名头, 任何改写都会导致验签失败。

如果事件要接进自己已有的aiohttp应用, 不用起整套服务器, 挂一个处理函数就行:

```python
from aiohttp import web

from qbotsdk import Bot
from qbotsdk.gateway import build_webhook_handler

bot = Bot(app_id=..., app_secret=...)
app = web.Application()
app.router.add_post("/qbotsdk", build_webhook_handler(bot.dispatcher, "机器人密钥"))
```

如果要使用flask等其他http框架, 仿照该处理函数写一遍处理函数即可。

## 文本交互

官方把 @ 某人、@ 全部成员、可点击指令、跳转子频道、系统表情都做成嵌在正文里的标记, 渲染成字符串后放进 `content` 或
`MessageMarkdown.content`。`qbotsdk.model.markup` 把这些标记做成了节点, 拼好之后一次渲染, 不用手动拼尖括号:

```python
from qbotsdk.model.markup import (
    AtEveryone,
    AtUser,
    CommandEnter,
    CommandInput,
    PlainText,
    TextChain,
)

chain = TextChain.of(
    AtUser("member-openid"),
    PlainText(" 签到去 "),
    CommandInput("我要签到", show="签到"),
    PlainText(" 或者直接 "),
    CommandEnter("/sign"),
)
await event.reply(markdown=MessageMarkdown(content=chain.render()))
```

渲染结果是
`<qqbot-at-user id="member-openid" /> 签到去 <qqbot-cmd-input text="...%20..." show="..."/> 或者直接 <qqbot-cmd-enter text="%2Fsign" />`,
指令文本会自动 urlencode。

反方向也能拆回来, 认不出的片段原样保留在 `PlainText` 里:

```python
chain = TextChain.parse(markdown_text)
for node in chain:
    print(type(node).__name__, node.render())
```

几点边界:

- `AtUser` 的 `id` 在群聊里填 `member_openid`、在文字子频道里填 `user_openid`, 两者 id 空间不同, 本模型不做转换。
- 群聊的 `AtUser` 只支持 markdown 消息;文字子频道支持文本、图文与 markdown 三种。
- `AtEveryone` 在群聊里要求机器人是群管理员, 且每个群每个自然日只能发一次。
- `CommandEnter` 仅 markdown 可用;它与 `CommandInput` 的文本都限 100 字符。
- `ChannelLink` 与 `EmojiMarkup` 仅频道可用, 表情只支持 `type = 1` 的系统表情。
- 旧的 `<@userid>` 与 `@everyone` 即将弃用, 这里既不生成也不解析。

## 命令与权限

命令层是叠在事件之上的可选模块, 它不订阅任何事件, 也不挂在 `Bot` 上。
注册时声明每条命令响应哪些事件, 再由你在自己的监听器里决定是否交给它。

### 三步接入

```python
from async_event_bus import EventContext

from qbotsdk import Bot
from qbotsdk.commands import GroupContext, Reply, Router
from qbotsdk.model.event import GroupMessageCreate

router = Router()


@router.command("ping", on=GroupMessageCreate)
async def ping(ctx: GroupContext) -> Reply:
    return Reply(text="pong")


bot = Bot(app_id=..., app_secret=...)


@bot.on(GroupMessageCreate)
async def on_group(ctx: EventContext[GroupMessageCreate]) -> None:
    await router.handle(ctx.event)  # 不是命令时返回 NOT_FOUND, 什么都不发
```

就这样, 群里发 `/ping` 会收到 `pong`。
注册命令必须写 `on=`, 它决定这条命令响应哪种事件。

### 带权限的完整例子

```python
from async_event_bus import EventContext

from qbotsdk import Bot
from qbotsdk.commands import GroupContext, Reply, Router, Status
from qbotsdk.model.event import GroupMessageCreate
from qbotsdk.permissions import (
    MemoryPermissionStorage,
    Permission,
    PermissionChecker,
    PermissionGroup,
    install_permission_commands,
)


class Server(PermissionGroup, namespace="server"):
    START = Permission("start", "启动服务器")
    STOP = Permission("stop", "停止服务器")


store = MemoryPermissionStorage()
router = Router(checker=PermissionChecker(store))

# /permission show [target] | grant | revoke | claim | whoami | role
install_permission_commands(router, store)


@router.command("server start", on=GroupMessageCreate, permission=Server.START)
async def start(ctx: GroupContext) -> Reply:
    return Reply(text="started")


@router.command("kick <member:mention>", on=GroupMessageCreate)
async def kick(ctx: GroupContext, member: str) -> Reply:
    return Reply(text=f"kicked {member}")


bot = Bot(app_id=..., app_secret=...)


@bot.on(GroupMessageCreate)
async def on_group(ctx: EventContext[GroupMessageCreate]) -> None:
    result = await router.handle(ctx.event)
    if result.status is Status.HANDLED:
        print(result.command, result.replied)
```

### 处理器返回值

处理器返回值必须是 `Reply`, `Reply(text="...")` 当正文发出去, `Reply.ok()` 表示静默成功,
`Reply(..., markdown=True)` / `Reply(..., keyboard=...)` 带额外能力, 参数错误请显式 `raise UsageError(...)`。

参数有问题就 `raise UsageError("...")`, 其它异常统一回内部错误文案;
`ExecutionResult.status` 会区分 `HANDLED` / `DENIED` / `FAILED` / `NOT_FOUND`, 方便在监听器里做记录或埋点。
handler 里已经 `await ctx.reply(...)` 过的话, 路由器不会把返回值再发一遍。

一条命令可以同时挂在多个事件上。

#### 回复前的 @

群聊里默认会在正文前带上对发送者的 @。QQ 的 @ 标记只在 markdown 消息里生效, 所以带 @ 的回复会自动
按 markdown 发送, 正文形如 `<qqbot-at-user id="..." /> pong`。不想带就逐层关掉, 优先级从高到低是
`Reply(mention=...)`、`router.command(..., mention=...)`、`Router(reply_mention=False)`。单聊不带,
频道会把正文换成 markdown 消息再带 @。

### 参数与模板

模板里的占位符默认按注解转换, `str`、`int`、`float`、`mention`, 末尾写 `<text:rest>` 表示吃掉剩余全部 token。
模板不支持默认值, 可选参数用注册两条命令表达:

```python
@router.command("roll", on=GroupMessageCreate)
async def roll(ctx: GroupContext) -> Reply:
    return Reply(text=f"掷出了 {random.randint(1, 6)}")


@router.command("roll <sides:int>", on=GroupMessageCreate)
async def roll_sides(ctx: GroupContext, sides: int) -> Reply:
    return Reply(text=f"掷出了 {random.randint(1, sides)}")
```

想让处理器自己拿原始参数, 注册时写 `bind_args=False`, 此时处理器只收 `ctx` 和 `argv: list[str]`:

```python
@router.command("echo <text:rest>", on=GroupMessageCreate, bind_args=False)
async def echo(ctx: GroupContext, argv: list[str]) -> Reply:
    return Reply(text=" ".join(argv))
```

### 匹配顺序

命令匹配是一棵按事件类型分开的前缀树, 字面量边优先, 整棵子树走不通才回退到 `<name>` 这类可变参边, 最后才是
`<text:rest>`;
token 用完却停在没有处理器的节点上时, 框架会按该节点的子项回 usage,
例如 `/permission role` → `Invalid arguments. Usage: /permission role <add|*name>`。

### 选项

`--` 开头的 token 在匹配阶段被收进选项表, `--` 单独出现表示后面不再当选项。注册时声明类型即可自动转换并绑定:

```python
@router.command("roll <sides:int>", on=GroupMessageCreate, options={"loud": bool, "times": int})
async def roll(ctx: GroupContext, sides: int, *, loud: bool = False, times: int = 1) -> Reply: ...
```

`/roll 20 --loud --times=3` 会得到 `sides=20`、`loud=True`、`times=3`。
`<text:rest>` 之后的 token 原样打包, 不再解析选项, 交给 handler 自己处理。

### 未知命令

带前缀但没命中任何命令时默认静默;需要提示就 `Router(reply_unknown=True)`,
回复文案是 `Messages.unknown_command`, 可整体或按键替换。不带前缀的普通聊天不会触发任何回复。

### 处理器身份

`ctx.command` 是这次命中的路径。
同一个 handler 注册多条路径时每条路径各有一个名字, 但 `handler` 是同一个函数对象:

```python
@router.command("ban <member>", on=GroupMessageCreate)
async def ban(ctx: GroupContext, member: str) -> Reply:
    hit(ctx.route.handler)  # 两条路径共用这一个键
    return Reply(text=f"banned {member}")


# 同一个 handler, 另一条路径
router.command("封禁 <member>", on=GroupMessageCreate)(ban)
```

### 权限

权限键自己声明, 注册命令时挂上去:

```python
class Demo(PermissionGroup, namespace="demo"):
    ADMIN = Permission("admin", "演示管理")
    PING = Permission("ping", "演示 ping")


@router.command("ban <member:mention>", on=GroupMessageCreate, permission=Demo.ADMIN)
async def ban(ctx: GroupContext, member: str) -> Reply:
    return Reply(text=f"banned {member}")
```

`namespace` 加键名就是完整键, `Demo.ADMIN` 即 `demo.admin`;`Demo.ADMIN.wildcard()` 是 `demo.*`,
只授 `demo.*` 就能一次覆盖 `demo.admin` 与 `demo.ping`。

判定由 `Router(checker=PermissionChecker(store))` 完成, `store` 是下面的任意一种权限存储;
没配 checker 时命令一律被拒并打 warning, 不会静默放行。

#### 第一次授权

`/permission grant` 自己也要 `permission.grant`, 所以第一次得在启动时给一个人:

```python
import os

from qbotsdk.permissions import Grant, install_permission_commands

owner = os.environ["QQ_BOT_OWNER"]  # 形如 group:{群 openid}:{你的 openid}
await store.grant(owner, Grant("permission.*"))
install_permission_commands(router, store)
```

主体键可以先让机器人回 `/permission whoami` 告诉你, 再填进环境变量。

#### 内置命令

| 命令                                          | 作用                       | 需要                |
|-----------------------------------------------|----------------------------|---------------------|
| `/permission whoami`                          | 打印自己的主体键           | 无                  |
| `/permission show`                            | 看自己的作用域、授予与角色 | 无                  |
| `/permission show @某人`                      | 看别人的同一组信息         | `permission.show`   |
| `/permission grant @某人 demo.admin`          | 授权（默认场景级）         | `permission.grant`  |
| `/permission grant @某人 demo.admin --global` | 授到账号级                 | `permission.grant`  |
| `/permission grant demo.admin --code`         | 生成一次性授权码           | `permission.grant`  |
| `/permission claim ABCD-2345`                 | 领取授权码                 | 无                  |
| `/permission revoke @某人 demo.admin`         | 撤销                       | `permission.revoke` |
| `/permission role list`                       | 列出角色                   | `permission.role`   |
| `/permission role save vip demo.*`            | 定义角色                   | `permission.role`   |
| `/permission role assign @某人 vip`           | 把角色分给人               | `permission.role`   |

`@某人` 依赖事件里的成员标记,
`GroupMessageCreate` 下事件层把 `<@openid>` 渲染成 `@openid`, `mention` 参数直接得到裸 openid;
机器人只订阅 `GROUP_AT_MESSAGE_CREATE` 时拿不到 @ 信息, 这时用 `--code` 或直接写 openid。

`/permission show` 的输出按主体分段, 每段带上作用域、直接授予与角色:

```text
Your permissions:
group:group-1:member-1
  scope: group group-1
  direct: demo.admin
  roles:
    vip
      grants: demo.*, -demo.admin
      inherits: base
user:member-1
  scope: user, applies in every scene
  direct: none
  roles: none
```

`scope` 是主体所在的作用域, `direct` 是直接授予, `roles` 下每个角色列自己的 `grants` 与父角色 `inherits`;
角色被分配但定义已删除时写 `definition is missing`。

#### 判定规则

主体分两级: 场景键与账号键, 先判场景再判账号;候选链从具体往笼统走, 同一级拒绝优先, 默认拒绝。

### 权限存储

按需选择: `MemoryPermissionStorage`（默认）、`FilePermissionStorage`、`RedisPermissionStorage`、`SqlitePermissionStorage`、
`MysqlPermissionStorage`、`PostgresPermissionStorage`;外层套 `CachedPermissionStorage` 可以少打几次存储。

权限数据要跨重启保留时才需要换存储, 本地调试用默认的内存实现即可。

Redis 权限存储的构造方式与会话存储一致, 同样支持 `from_url` 与现成客户端:

```python
from qbotsdk.permissions.store import RedisPermissionStorage

# 给完整地址, 或者只给零件, 地址由SDK拼
RedisPermissionStorage.from_url("redis://:pwd@10.0.0.5:6379/2")
RedisPermissionStorage.from_url(host="10.0.0.5", port=6379, password="pwd", db=2)

# Unix domain socket, 以及指定RESP协议版本
RedisPermissionStorage.from_url(unix_socket="/var/run/redis/redis.sock", db=2, protocol=3)

# 也可以直接把现成的Redis客户端交给SDK, 全限定名必须是 redis.asyncio.Redis
from redis.asyncio import Redis

RedisPermissionStorage(Redis(host="10.0.0.5", port=6379))
```

SQL 存储默认带一个异步驱动

- SQLite 用 `aiosqlite`
- MySQL 用 `asyncmy`
- PostgreSQL 用 `asyncpg`

已有项目用别的驱动时不必换装:

```python
from qbotsdk.permissions.store import MysqlPermissionStorage, PostgresPermissionStorage

# 只换驱动, 连接参数写法不变
MysqlPermissionStorage(database="qbot", driver="aiomysql")

# 给完整连接串, 驱动、SSL 与驱动私有参数放进 URL 或 connect_args
PostgresPermissionStorage.from_url(
    "postgresql+psycopg://qbot:pwd@10.0.0.5:5432/qbot?sslmode=require",
    connect_args={"prepare_threshold": 0},
)

# 已经有异步引擎时直接交进来, 存储不负责关闭它
PostgresPermissionStorage.from_engine(engine)
```

`qbotsdk[mysql]` 与 `qbotsdk[postgres]` 只安装默认驱动, 用别的驱动时自行安装即可。

连接层本身与权限无关, 放在 `qbotsdk.storage.sql`: `SqlBackend` 描述方言与默认驱动, `SqlStorage` 负责 URL 解析、引擎创建/释放与 `from_url`/`from_engine`, 其它存储可以直接继承或单独使用。

### 按钮回调

按钮与快捷菜单回调用 `router.button(载荷模型)` 注册, handler 里写 `return Reply(text="已处理")`
或 `await ctx.reply("已处理")` 都可以, 框架按 `ack` 策略把它变成客户端回应。

## 富媒体上传

群聊与单聊的 `upload_file()` 在 `url` 和 `file` 之间二选一: 传 `url` 时由平台自行抓取; 传 `file` 时
SDK 按大小自动选择直传还是分片（`str` / `Path` 按路径读文件, `BinaryIO` 需要可 seek, 也可以直接给
`bytes`）, 调用方不必关心底层走哪条路径。

```python
from pathlib import Path

from qbotsdk import Bot
from qbotsdk.model.media import FileType, MediaInfo

async with Bot(app_id="app", app_secret="secret") as bot:
    # 本地文件, 超过 5MB 自动走预上传 + 分片 + 合并
    uploaded = await bot.api.group.upload_file(
        "group-openid",
        FileType.FILE,
        file=Path("./report.pdf"),
        progress=lambda done, total: print(f"{done}/{total}"),
    )
    await bot.api.group.send_message("group-openid", media=MediaInfo(file_info=uploaded.file_info))
```

不传 `file_name` 时取文件名; 分片用的 `md5` / `sha1` / `md5_10m` 由 SDK 单遍读取计算, 不接受调用方
传入。分片并发取 `ClientOptions(upload_concurrency=4)` 与服务端下发的 `upload_config.concurrency`
的较小值。`srv_send_msg=True` 表示平台把文件直接发进会话, 这次发送会计入本地限流与发送记录。

## 本地限流

发消息前 `RateLimiter` 会依次检查三层限制, 任何一层没额度都会在本地拦下, 请求不会发出:

| 层           | 统计范围          | 默认值     | 配置项              |
|--------------|-------------------|------------|---------------------|
| 会话速率     | 每个群 / 每个单聊 | 20 条/分钟 | `rate_limits`       |
| 会话日配额   | 每个群 / 每个单聊 | 1000 条/天 | `daily_limits`      |
| 机器人总速率 | 所有主动消息共享  | 不限       | `global_rate_limit` |

被动回复（带 `reply_to` 或 `event_id`）只走前两层, 不占机器人总速率, 避免正常回复被主动消息的配额拖住。
这几层都是本进程内的计数: 多实例部署时各算各的, 最终仍以服务端的 `40034100` 为准。

```python
from qbotsdk import Bot, ClientOptions

options = ClientOptions(
    # 每个群每分钟 20 条、每个单聊每分钟 10 条
    rate_limits={"group": 20.0, "c2c": 10.0},
    # 每个群每天 1000 条、单聊不限
    daily_limits={"group": 1000, "c2c": 0},
    # 整个机器人每分钟最多 200 条主动消息
    global_rate_limit=200.0,
)

async with Bot(app_id="app", app_secret="secret", options=options) as bot:
    await bot.api.group.send_message("group-openid", content="hello")
```

`rate_limits` 与 `daily_limits` 的键是 scope（`group`、`c2c`）, 值为 0 表示不限;
`global_rate_limit` 传 `None` 或 0 表示不限。任一限制被触发都会抛 `RateLimitExceededError`,
异常上的 `window` 说明是哪一层（`minute` / `day` / `bot`）, `retry_after` 是预计需要等待的秒数。
`ClientOptions(respect_rate_limits=False)` 会整体关掉本地限流。

查询剩余额度: `bot.api.limiter.remaining("group", group_openid)` 返回这一分钟还剩几条,
`daily_remaining(...)` 返回这一天还剩几条（没有配置日配额时返回 `None`）。

## 发送记录

`ClientOptions(send_hook=...)` 可以挂一个切面, 统一观察所有发出的消息: 每次发送结束后回调一次,
群聊、单聊、频道三条通道都覆盖, `event.reply()` 这类高层入口最终也走同一个切面。

```python
from qbotsdk import Bot, ClientOptions
from qbotsdk.module.send_hook import SendHook, SendRecord


class SendLog(SendHook):
    async def on_sent(self, record: SendRecord) -> None:
        if record.error is not None:
            await log_failure(record)
        else:
            await save_message(record)


options = ClientOptions(send_hook=SendLog())

async with Bot(app_id="app", app_secret="secret", options=options) as bot:
    await bot.api.group.send_message("group-openid", content="hello")
```

`SendRecord` 的字段: `scope` 是通道（`group` / `c2c` / `channel`）, `target` 是对应的
群 openid、用户 openid 或子频道 id, `path` 是实际请求路径, `proactive` 表示这条是不是主动消息,
`message` 是真正发出去的那条消息本身, 群聊/单聊是 `GroupMessageDraft`/`UserMessageDraft`,
频道是 `ChannelMessageDraft`: 正文、Markdown、图片或富媒体、keyboard、回复引用都在上面,
`record.message.model_dump(by_alias=True, exclude_none=True)` 就是可直接落库的完整请求体;
要展示或写日志时用 `record.message.to_text()`, 它把正文与 Markdown 还原成文字,
图片带上地址, 富媒体、keyboard 这类没有文字的部分用 `[media]`、`[keyboard]` 占位。
`message_id` 与 `error` 二选一: 发送成功时前者是平台返回的消息 id, 失败时后者是抛出的
`QQBotError`（包括本地限流拦下的 `RateLimitExceededError`, 此时请求没发出去, `message` 也可能为 `None`）。

切面只做观察, 不能改写消息、也不会截断发送: 回调抛异常只会记一条日志, 发送结果照旧返回。
不传 `send_hook` 就不产生任何回调。

## 原始报文

SDK 给每个响应模型和事件模型都挂了一个 `raw`, 内容是**解析这条数据时用的那份 dict 本身**

```python
from qbotsdk.model.event import GroupMessageCreate


@bot.on(GroupMessageCreate)
async def on_group(ctx) -> None:
    event = ctx.event
    print(event.content)  # SDK 已建模的字段
    print(event.raw["content"])  # 同一份数据, 原文
    print(event.raw.get("some_new_field"))  # 官方新加、SDK 还没建模的字段
```

嵌套模型各自带一份子 dict, `event.author.raw["username"]`等都能直接读。REST 接口同理:

```python
me = await bot.api.user.me()
print(me.raw["username"])
```

注意事项:

1. `raw`字段是dict类型, 生成的 `__hash__` 在调用时会抛 `TypeError`, 不要把模型放进 `set` 或当作 dict 的键。
2. 内存上每个模型有一份dict引用, 嵌套对象与原报文共享同一个dict对象, 不是深拷贝。

## 示例

具体示例请见[examples文件夹](examples/README.md)。

## 第三方依赖

| 依赖                                                               | 用途                          | 许可                       |
|--------------------------------------------------------------------|-------------------------------|----------------------------|
| [aiohttp](https://github.com/aio-libs/aiohttp)                     | HTTP 与 WebSocket 客户端      | Apache-2.0 AND MIT         |
| [pydantic](https://github.com/pydantic/pydantic)                   | 数据模型与校验                | MIT                        |
| [loguru](https://github.com/Delgan/loguru)                         | 日志                          | MIT                        |
| [cryptography](https://github.com/pyca/cryptography)               | Webhook 的 ed25519 签名与验签 | Apache-2.0 OR BSD-3-Clause |
| [async-event-bus](https://github.com/half-nothing/async-event-bus) | 事件总线                      | MIT                        |
| [yarl](https://github.com/aio-libs/yarl)                           | URL 拼接                      | Apache-2.0                 |

## 致谢

- [QQ 机器人官方文档](https://bot.q.qq.com/wiki/develop/api-v2): 字段、错误码与协议细节都以它为准。
- [async-event-bus](https://github.com/half-nothing/async-event-bus): 事件总线。
- [aiohttp](https://github.com/aio-libs/aiohttp): HTTP 与 WebSocket 客户端。
- [pydantic](https://github.com/pydantic/pydantic): 数据模型与校验。
- [loguru](https://github.com/Delgan/loguru): 日志。
- [cryptography](https://github.com/pyca/cryptography): ed25519 签名与验签。
- [yarl](https://github.com/aio-libs/yarl): URL 拼接。
- 腾讯官方 Python SDK 文档与社区实现: 心跳、Resume、关闭码语义对照过。
- 所有反馈过的使用者。

## 许可证

Apache-2.0, 见 [LICENSE](LICENSE)。
