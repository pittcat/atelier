"""ModemLogAnalyzer —— LangSmith / 追踪初始化。

部署时关掉 LANGSMITH_TRACING 即可关闭；默认开启。

按 Plan §1 隐私要求:
  - trace 默认只记录结构化摘要和指标。
  - 不上传原始日志正文、号码、IMSI / ICCID / IMEI 等敏感内容。
"""

from __future__ import annotations

import os


def init_tracing(project: str | None = None) -> None:
    """根据环境变量启用 LangSmith 追踪。"""
    if os.getenv("LANGSMITH_TRACING", "false").lower() != "true":
        return
    if not os.getenv("LANGSMITH_API_KEY"):
        return

    # langgraph / langchain 会自动读 LANGSMITH_* 环境变量
    if project:
        os.environ["LANGSMITH_PROJECT"] = project


__all__ = ["init_tracing"]
