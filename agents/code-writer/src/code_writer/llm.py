"""统一的 LLM 客户端。

通过环境变量 `ANTHROPIC_AUTH_TOKEN` + `ANTHROPIC_BASE_URL` 选 provider。

走 **Anthropic Messages 协议** 接入 anthropic-compat 服务(如 MiniMax)。

CC Switch / 路由代理软件通常按 path 重定向 —— 用 `/anthropic/v1/messages`
协议的请求会被转发,直接走 OpenAI ChatCompletions 会被过滤成 502。

惰性: import 时不会触碰 langchain_anthropic;单元测试如果只测工具/提示词,
不需要安装它。
"""

from __future__ import annotations

import os
from typing import Any


def get_llm(model_name: str) -> Any:
    """返回 ChatAnthropic 实例。

    provider:
        Anthropic 官方 / 任何 Anthropic-Messages 协议兼容服务(如 MiniMax)
        - 通过 ANTHROPIC_AUTH_TOKEN (or ANTHROPIC_API_KEY) 取 key
        - 通过 ANTHROPIC_BASE_URL 取 endpoint

    关键点:
        - `disable_streaming=True` 强制 astream/stream 走 invoke,
          减少 OpenAI SDK 在 streaming 模式下偶发的 502。
        - `betas=[]` 不发 Anthropic 私有 beta header,避免兼容服务拒绝。
    """
    try:
        from langchain_anthropic import ChatAnthropic
    except ImportError as e:
        raise RuntimeError(
            "langchain_anthropic not installed. Run `uv pip install langchain-anthropic`."
        ) from e

    api_key = (
        os.getenv("ANTHROPIC_AUTH_TOKEN")
        or os.getenv("ANTHROPIC_API_KEY")
        or "test-no-key"
    )
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
    # 注意:**不**设置 betas=[]。langchain-anthropic 检测到 payload["betas"] key 存在就走 beta endpoint
    # (`/v1/messages?beta=true`),部分 anthropic-compat 服务(MiniMax)对 beta=true URL 重写失败、502。
    return ChatAnthropic(**kwargs)


def resolve_minimax_env(env_path: str | None = None) -> dict:
    """工具函数:把 MiniMax 推荐环境写进 .env(不改用户已有行)。

    用法:
        from code_writer.llm import resolve_minimax_env
        resolve_minimax_env("agents/code-writer/.env")
    """
    import io, re
    lines = []
    if env_path and os.path.exists(env_path):
        with open(env_path, encoding="utf-8") as f:
            lines = f.read().splitlines()

    keys = ("ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_BASE_URL", "ATELIER_DEFAULT_MODEL")
    have = {k: any(re.match(rf"\s*{k}\s*=", ln) for ln in lines) for k in keys}

    out = io.StringIO()
    if lines:
        out.write("\n".join(lines) + "\n")
    if not have["ANTHROPIC_AUTH_TOKEN"]:
        out.write("\n# --- MiniMax (Anthropic Messages 协议) ---\n")
        out.write("ANTHROPIC_AUTH_TOKEN=<paste-your-minimax-key>\n")
    if not have["ANTHROPIC_BASE_URL"]:
        out.write("ANTHROPIC_BASE_URL=https://api.minimaxi.com/anthropic\n")
    if not have["ATELIER_DEFAULT_MODEL"]:
        out.write("ATELIER_DEFAULT_MODEL=MiniMax-M3[1M]\n")
    return {"written_preview": out.getvalue(), "would_write": [k for k in keys if not have[k]]}
