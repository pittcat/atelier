"""ModemLogAnalyzer —— 统一的 LLM 客户端。

通过环境变量 ``ANTHROPIC_AUTH_TOKEN`` + ``ANTHROPIC_BASE_URL`` 选 provider。
走 **Anthropic Messages 协议** 接入 anthropic-compat 服务（如 MiniMax）。

惰性: import 时不会触碰 langchain_anthropic；单元测试如果只测工具/提示词，
不需要安装它。
"""

from __future__ import annotations

import os
from typing import Any


def get_llm(model_name: str) -> Any:
    """返回 ChatAnthropic 实例。

    provider:
        Anthropic 官方 / 任何 Anthropic-Messages 协议兼容服务（如 MiniMax）
        - 通过 ANTHROPIC_AUTH_TOKEN (or ANTHROPIC_API_KEY) 取 key
        - 通过 ANTHROPIC_BASE_URL 取 endpoint

    关键点:
        - ``disable_streaming=True`` 强制 astream/stream 走 invoke,
          减少 OpenAI SDK 在 streaming 模式下偶发的 502。
    """
    try:
        from langchain_anthropic import ChatAnthropic
    except ImportError as e:
        raise RuntimeError(
            "langchain_anthropic not installed. Run `uv pip install langchain-anthropic`."
        ) from e

    api_key = os.getenv("ANTHROPIC_AUTH_TOKEN") or os.getenv("ANTHROPIC_API_KEY") or "test-no-key"
    base_url = os.getenv("ANTHROPIC_BASE_URL")

    kwargs: dict = dict(
        model=model_name,
        api_key=api_key,
        timeout=120,
        max_retries=3,
        streaming=False,
        disable_streaming=True,
    )
    if base_url:
        kwargs["base_url"] = base_url
    return ChatAnthropic(**kwargs)


def resolve_default_model() -> str:
    """返回当前默认模型字符串（CLI 启动时打印用）。"""
    return os.getenv("ATELIER_DEFAULT_MODEL", "claude-opus-4-8")
