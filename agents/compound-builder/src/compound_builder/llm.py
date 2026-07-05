"""CompoundBuilder —— LLM 客户端。

通过 shell / direnv 已导出的 ``ANTHROPIC_*`` 环境变量选 provider(如 MiniMax)。
与 code-writer 同策略:Anthropic Messages 协议 + ``disable_streaming``。
"""
from __future__ import annotations

import os
from typing import Any


def resolve_default_model() -> str:
    """模型名优先级:ATELIER_DEFAULT_MODEL → ANTHROPIC_MODEL → opus 默认。"""
    return (
        os.getenv("ATELIER_DEFAULT_MODEL")
        or os.getenv("ANTHROPIC_MODEL")
        or os.getenv("ANTHROPIC_DEFAULT_OPUS_MODEL")
        or "claude-opus-4-8"
    )


def get_llm(model: str | None = None) -> Any:
    """返回 LangChain ChatAnthropic 实例。"""
    try:
        from langchain_anthropic import ChatAnthropic
    except ImportError as e:
        raise RuntimeError(
            "langchain_anthropic not installed. Run `uv sync` in agents/compound-builder."
        ) from e

    api_key = (
        os.getenv("ANTHROPIC_AUTH_TOKEN")
        or os.getenv("ANTHROPIC_API_KEY")
        or ""
    )
    base_url = os.getenv("ANTHROPIC_BASE_URL")
    model_name = model or resolve_default_model()

    kwargs: dict[str, Any] = dict(
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


__all__ = ["get_llm", "resolve_default_model"]
