# ============================================
# CompoundBuilder Agent - Makefile
# ============================================
# 项目根目录下使用：
#   make format           # 格式化
#   make lint             # lint
#   make test             # 跑测试
#   make dev              # langgraph dev 本地开发
#   make build            # 构建 Docker 镜像
#   make up               # 启动服务

.PHONY: help format lint test dev build up

help:
	@echo "CompoundBuilder 命令:"
	@echo "  make format           # ruff format"
	@echo "  make lint             # ruff check + mypy"
	@echo "  make test             # pytest"
	@echo "  make dev              # langgraph dev (本地)"
	@echo "  make build            # 构建 Docker 镜像"
	@echo "  make up               # 启动服务"

format:
	ruff format .

lint:
	ruff check .
	mypy src

test:
	pytest -q $(if $(TEST),tests/$(TEST),tests/)

dev:
	langgraph dev

build:
	langgraph build -t atelier/compound_builder

up:
	langgraph up
