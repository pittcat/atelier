# Code Writer Agent —— Makefile

.PHONY: help format lint test dev build up
help:
	@echo "Code Writer 命令:"
	@echo "  make format / lint / test"
	@echo "  make dev / build / up"

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
	langgraph build -t atelier/code-writer

up:
	langgraph up
