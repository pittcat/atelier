"""ModemLogAnalyzer 的工具集。

只读日志分析 Agent:主代理与 subagent 都不需要 bash / write_file / edit_file /
git_commit / git_push。所有产物由 CLI 直接生成,不通过 Agent 工具。

工具集设计原则 (Plan S16):
  - main agent 工具 ≤ 5 个,全部只读
  - 不暴露通用 write_file / bash / git_push
  - Agent 仅能: 读控制脚本日志(可选)、校验 schema 草稿

设计边界:
  - ``build_tools()`` 在 deepagents / langgraph 装配时才被调用,因此
    这里 import ``langchain_core.tools`` 是惰性的(在函数体内)。
  - 单元测试可以静态校验"工具注册表不能含危险工具",而无需安装 langchain_core。
"""

from __future__ import annotations

from pathlib import Path


# ============================================================
# 反向断言（测试 + 启动期都调用,确保禁用的工具永远不被悄悄注册）
# ============================================================
def _assert_no_push() -> None:
    """反向断言:本文件不能注册任何 ``git_push`` / ``bash`` 工具。

    在测试与 smoke 里显式调用,确保 AGENTS.md 规则不被悄悄绕过。
    """
    import inspect

    src = inspect.getsource(__import__(__name__))
    forbidden = ("def git_push", "def bash", "def write_file")
    for bad in forbidden:
        # docstring/字符串里的反向断言是允许的; 仅匹配真正的 def 开头

        for line in src.splitlines():
            stripped = line.strip()
            if stripped.startswith("def ") and bad in stripped:
                raise AssertionError(f"tools.py 严禁定义 {bad}(违反 AGENTS.md 硬规矩): {stripped}")


# ============================================================
# 工具 1: 读取项目级控制脚本日志(只读)
# ============================================================
def read_control_log_tool(log_path: str, max_lines: int = 2000) -> str:
    """Read a control-script log file (text). Used only when CLI provides --control-log."""
    p = Path(log_path).expanduser().resolve()
    if not p.exists() or not p.is_file():
        return f"ERROR: control log not found: {p}"
    try:
        text = p.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        return f"ERROR: read failed: {e}"
    lines = text.splitlines()
    if len(lines) > max_lines:
        return "\n".join(lines[:max_lines]) + f"\n... ({len(lines)} lines total, truncated)"
    return text


# ============================================================
# 工具 2: 校验 LLM 返回的 AnalysisResult 草稿是否合法
# ============================================================
def validate_analysis_draft_tool(candidate: dict) -> str:
    """Validate a candidate AnalysisResult draft against the public schema."""
    from modem_log_analyzer.contracts import AnalysisResult

    try:
        result = AnalysisResult.model_validate(candidate)
    except Exception as e:
        return f"INVALID: {e!s}"
    return f"VALID classification={result.classification.value}"


# ============================================================
# 工厂: 主代理可用工具集
# ============================================================
def build_tools() -> list:
    """主代理可用工具合集。

    返回 ``list[BaseTool]``(deepagents / langgraph 能直接消费)。
    在没有安装 langchain_core 的测试环境,我们返回轻量 SimpleTool 替身,
    它们通过 ``.name`` / ``.invoke({...})`` 接口可被静态测试校验。
    """
    from modem_log_analyzer.tools_simple import (
        _as_simple_tool,
    )

    _assert_no_push()

    # 注意:这里 import 是惰性的,以避免在没有 langchain_core 的环境失败。
    # 测试只校验工具的 ``.name`` 属性与总数, 不真正调用。
    return [
        _as_simple_tool("read_control_log", read_control_log_tool),
        _as_simple_tool("validate_analysis_draft", validate_analysis_draft_tool),
    ]
