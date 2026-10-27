# 更新日志

本项目遵循[语义化版本](https://semver.org/lang/zh-CN/)，格式参考
[Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)。

改动按版本号归档，尚未发版的改动记在「未发布」下。

## [未发布]

### 计划中

- 论坛 threads 与音频 actions 的接口（官方文档缺页，取证后再实现）。
- VitePress 文档站与 API 自动生成。
- PyPI 发布自动化：Trusted Publishing + OIDC，省掉手动令牌。

### 记录

- 项目改名：发行名 `qq-bot-sdk` → `qbotsdk`，导入包 `qqbot` → `qbotsdk`。
  原因是 PyPI 上已有同词干的 `qqbot` 项目，原名被判为「过于相似」而无法发布。
- 当前能力范围（鉴权、REST 接口、消息收发、事件接入、Webhook）以 README 为准。
