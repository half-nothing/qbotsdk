# 示例

每个文件都能单独运行，只依赖 `qbotsdk` 本身。公共环境变量：

```bash
QQ_BOT_APP_ID=你的AppID
QQ_BOT_APP_SECRET=你的AppSecret
```

| 文件                  | 演示内容                                                   |
|---------------------|--------------------------------------------------------|
| `hello.py`          | 拉频道、子频道、身份组、群信息，再发消息 / 表态 / 撤回                         |
| `websocket.py`      | 长连接收四类事件（群 @、单聊、频道 @、互动），带会话落盘                         |
| `webhook.py`        | 用 `WebhookAdapter` 起回调服务，含 TLS 证书与验签                   |
| `group_bot.py`      | 群机器人：按钮键盘、按钮回调、富媒体上传、撤回                                |
| `c2c_bot.py`        | 单聊机器人：正在输入、Markdown 回复、回复次数与错误处理                       |
| `custom_webhook.py` | 把 Webhook 接进自己已有的 aiohttp 应用，只用 SDK 的纯函数与 `dispatcher` |

## 各示例额外的环境变量

| 文件                  | 变量                                                   |
|---------------------|------------------------------------------------------|
| `hello.py`          | `QQ_BOT_CHANNEL_ID`、`QQ_BOT_GROUP_OPENID`（不设则跳过对应演示） |
| `websocket.py`      | `QQ_BOT_INTENTS`、`QQ_BOT_SESSION_FILE`               |
| `webhook.py`        | `QQ_BOT_SECRET`、`QQ_BOT_CERTFILE`、`QQ_BOT_KEYFILE`   |
| `group_bot.py`      | `QQ_BOT_IMAGE_PATH`、`QQ_BOT_SESSION_FILE`            |
| `c2c_bot.py`        | 无                                                    |
| `custom_webhook.py` | `QQ_BOT_SECRET`、`QQ_BOT_WEBHOOK_PORT`                |

## 说明

- 所有示例都用 loguru 输出底层日志，默认`TRACE`，会输出大量网络通讯日志，如果觉得日志太多，可以将级别改成`INFO`
- `webhook.py` 与 `custom_webhook.py` 的回调地址必须是平台允许的端口，本地调试建议用 `custom_webhook.py` 挂在反向代理后面。
