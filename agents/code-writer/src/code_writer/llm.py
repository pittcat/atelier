"""统一的 LLM 客户端。

通过环境变量 `ANTHROPIC_API_KEY` 与 `ANTHROPIC_AUTH_URL` 选 provider。

注意：`get_llm(...)` 是**惰性**函数——import 时不会触碰 langchain_anthropic。
单元测试如果只测试工具 / 提示词，不需要安装它。
"""

from __future__ import annotations

import os
from typing import Any


def get_llm(model_name: str) -> Any:
    """返回 ChatModel 实例。

    默认用 langchain-anthropic；要换 provider，改这里即可。
    缺包时给一个清晰报错，方便本地仅装最小依赖的测试通过。
    """
    try:
        from langchain_anthropic import ChatAnthropic
    except ImportError as e:
        raise RuntimeError(
            "langchain_anthropic not installed. Run `uv pip install langchain-anthropic`."
        ) from e

    api_key = os.getenv("ANTHROPIC_API_KEY") or "test-no-key"
    return ChatAnthropic(
        model=model_name,
        api_key=api_key,
        timeout=120,
        max_retries=3,
    )
