# Atelier 仓库的统一 Makefile
#
# 用法（在仓库根目录）：
#   make format          # 全仓格式化
#   make lint            # 全仓 ruff + mypy
#   make test            # 全仓 pytest
#   make smoke           # 项目结构冒烟检查
#   make new-agent       # cookiecutter 引导新建 Agent
#   make dev AGENT=name  # 启 langgraph dev 跑某个 Agent
#   make build AGENT=name
#   make up   AGENT=name

# ---- 路径配置 ----
ATELIER_ROOT := $(shell pwd)
TEMPLATE_DIR := $(ATELIER_ROOT)/_templates/agent-template

# ---- 默认目标 ----
.DEFAULT_GOAL := help

# ---- Python ----
PYTHON ?= python3
ifeq (,$(shell which uv 2>/dev/null))
  PYTHON_PKG := $(PYTHON) -m pip
else
  PYTHON_PKG := uv pip
endif

# ---- help ----
.PHONY: help
help:
	@echo "Atelier 仓库命令："
	@echo "  make format           # 全仓格式化（ruff format）"
	@echo "  make lint             # 全仓 lint（ruff check + mypy）"
	@echo "  make test             # 全仓测试（pytest）"
	@echo "  make smoke            # 冒烟：项目结构自检"
	@echo "  make new-agent        # cookiecutter 引导新建 Agent"
	@echo "  make dev AGENT=slug   # 启 langgraph dev 跑某 Agent"
	@echo "  make build AGENT=slug # 构建 Agent Docker 镜像"
	@echo "  make up   AGENT=slug  # 启 Agent 服务"
	@echo "  make gateway          # 启统一 gateway/api"
	@echo "  make clean            # 清理临时文件"

# ---- format / lint / test ----
.PHONY: format
format:
	@echo ">> 全仓 ruff format ..."
	@find $(ATELIER_ROOT) -name "pyproject.toml" -not -path "*/.venv/*" -print0 | xargs -0 -I {} sh -c 'cd $$(dirname {}) && ruff format . 2>/dev/null || true'

.PHONY: lint
lint:
	@echo ">> 全仓 ruff check + mypy ..."
	@find $(ATELIER_ROOT) -name "pyproject.toml" -not -path "*/.venv/*" -print0 | xargs -0 -I {} sh -c 'cd $$(dirname {}) && ruff check . 2>/dev/null && mypy src 2>/dev/null || true'

.PHONY: test
test:
	@echo ">> 全仓 pytest ..."
	@if [ -d "$(ATELIER_ROOT)/agents/code-writer/.venv" ]; then \
		VENV_PY=$(ATELIER_ROOT)/agents/code-writer/.venv/bin/python; \
	else \
		VENV_PY=python3; \
	fi; \
	cd $(ATELIER_ROOT); \
	if [ -d "$(ATELIER_ROOT)/tests" ]; then \
		$$VENV_PY -m pytest -q tests/ 2>&1; \
		if [ -d "$(ATELIER_ROOT)/agents/code-writer" ]; then \
			echo ">> agents/code-writer 测试(via its venv)..."; \
			cd $(ATELIER_ROOT)/agents/code-writer && uv run pytest -q; \
		fi; \
	else \
		echo "(无顶层 tests，跳过)"; \
	fi

.PHONY: smoke
smoke:
	@echo ">> 项目结构冒烟检查 ..."
	@bash $(ATELIER_ROOT)/scripts/smoke.sh

# ---- Agent 生命周期 ----
.PHONY: new-agent
new-agent:
	@echo ">> cookiecutter 引导 ..."
	@cd $(ATELIER_ROOT) && cookiecutter $(TEMPLATE_DIR)

.PHONY: dev
dev:
	@if [ -z "$(AGENT)" ]; then echo "用法: make dev AGENT=code-writer"; exit 1; fi
	@cd $(ATELIER_ROOT)/agents/$(AGENT) && langgraph dev

.PHONY: build
build:
	@if [ -z "$(AGENT)" ]; then echo "用法: make build AGENT=code-writer"; exit 1; fi
	@cd $(ATELIER_ROOT)/agents/$(AGENT) && langgraph build -t atelier/$(AGENT)

.PHONY: up
up:
	@if [ -z "$(AGENT)" ]; then echo "用法: make up AGENT=code-writer"; exit 1; fi
	@cd $(ATELIER_ROOT)/agents/$(AGENT) && langgraph up

.PHONY: gateway
gateway:
	@echo ">> 启 gateway/api ..."
	@cd $(ATELIER_ROOT)/gateway/api && $(PYTHON_PKG) install -e . && uvicorn main:app --reload --port 8080

# ---- 维护 ----
.PHONY: clean
clean:
	@echo ">> 清理临时文件 ..."
	@find $(ATELIER_ROOT) -type d -name "__pycache__" -not -path "*/.venv/*" -exec rm -rf {} + 2>/dev/null || true
	@find $(ATELIER_ROOT) -type d -name ".pytest_cache" -not -path "*/.venv/*" -exec rm -rf {} + 2>/dev/null || true
	@find $(ATELIER_ROOT) -type d -name ".ruff_cache" -not -path "*/.venv/*" -exec rm -rf {} + 2>/dev/null || true
	@find $(ATELIER_ROOT) -type d -name ".mypy_cache" -not -path "*/.venv/*" -exec rm -rf {} + 2>/dev/null || true
