# qbotsdk 开发快捷命令。
#
# 需要 GNU Make。Windows 上装一个即可：`winget install ezwinports.make`
# 或 `choco install make`；用 Git Bash / MSYS2 时通常自带。
#
# 所有命令都是 `pdm run` 的薄包装，和 CI 的 .github/workflows/check.yml 一一对应。

PDM ?= pdm
RUN = $(PDM) run

.DEFAULT_GOAL := help

.PHONY: help install install-frozen lint lint-fix fmt fmt-check typecheck test test-v check clean

help: ## 列出可用命令
	@echo qbotsdk 常用命令:
	@echo   make install          安装依赖
	@echo   make install-frozen   按 pdm.lock 锁定安装，与 CI 一致
	@echo   make lint            ruff check
	@echo   make lint-fix        ruff check --fix
	@echo   make fmt             ruff format，会连 Markdown 代码块一起格式化
	@echo   make fmt-check       ruff format --check
	@echo   make typecheck       mypy
	@echo   make test            pytest -q
	@echo   make test-v          pytest -v
	@echo   make check           四项门禁全跑：lint + fmt-check + typecheck + test
	@echo   make clean           清理缓存与构建产物

install: ## 安装依赖
	$(PDM) install -d

install-frozen: ## 按 pdm.lock 锁定安装
	$(PDM) install -d --frozen-lockfile

lint: ## ruff check
	$(RUN) ruff check

lint-fix: ## ruff check --fix
	$(RUN) ruff check --fix

fmt: ## ruff format
	$(RUN) ruff format

fmt-check: ## ruff format --check
	$(RUN) ruff format --check

typecheck: ## mypy
	$(RUN) mypy

test: ## pytest -q
	$(RUN) pytest -q

test-v: ## pytest -v
	$(RUN) pytest -v

check: lint fmt-check typecheck test ## 四项门禁全跑

clean: ## 清理缓存与构建产物
	$(RUN) python -c "import shutil; [shutil.rmtree(p, ignore_errors=True) for p in ('.mypy_cache', '.pytest_cache', '.ruff_cache', 'build', 'dist', 'src/qbotsdk.egg-info')]"
	$(RUN) python -c "import pathlib, shutil; [shutil.rmtree(p, ignore_errors=True) for p in pathlib.Path('.').rglob('__pycache__')]"
