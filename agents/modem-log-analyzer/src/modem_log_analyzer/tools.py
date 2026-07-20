"""ModemLogAnalyzer 的工具集。

只读日志分析 Agent:主代理与 subagent 都不需要 bash / write_file / edit_file /
git_commit / git_push。所有产物由 CLI 直接生成,不通过 Agent 工具。

工具集设计原则 (Plan S16):
  - main agent 工具 ≤ 5 个,全部只读
  - 不暴露通用 write_file / bash / git_push
  - Agent 仅能:
      * get_preprocessed_bundle:  读本 run 的命令 + 证据摘要 (含 EV-NNNN)
      * read_evb_log_slice:        按行号窗口回读 EVB 原文
      * read_control_log:          读控制脚本日志(可选)
      * validate_analysis_draft:   校验 AnalysisResult 草稿

设计边界:
  - ``build_tools()`` 在 deepagents / langgraph 装配时才被调用,因此
    这里 import ``langchain_core.tools`` 是惰性的(在函数体内)。
  - ``get_preprocessed_bundle`` / ``read_evb_log_slice`` 通过 ``run_context``
    读取本 run 的预处理结果; runner 在 invoke agent 之前必须 ``set``。
  - 单元测试可以静态校验"工具注册表不能含危险工具",而无需安装 langchain_core。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


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
# 工具 0: 读取本 run 的预处理 bundle
# ============================================================
def get_preprocessed_bundle_tool() -> str:
    """返回本 run 的预处理结果 (JSON 字符串)。

    内容包括: run_label / command_summary / evidence_refs (EV-NNNN) /
    control_summary (若提供)。

    必须在 runner 已 set run_context 时调用; 否则返回明确错误字符串,
    防止 Agent 误以为工具静默可用。
    """
    from modem_log_analyzer import run_context as rc

    try:
        bundle = rc.require()
    except RuntimeError as e:
        return f"ERROR: {e}"
    # 精简输出: 不暴露 evb_log_path 绝对路径(避免 trace 含 PII/路径信息)
    payload = {
        "run_label": bundle.get("run_label"),
        "command_summary": bundle.get("command_summary", []),
        "evidence_refs": bundle.get("evidence_refs", []),
        "control_summary": bundle.get("control_summary"),
        "interrupt_request": bundle.get("interrupt_request"),
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


# ============================================================
# 工具 1: 按行号窗口回读 EVB 原文
# ============================================================
def read_evb_log_slice_tool(start_line: int, end_line: int, max_lines: int = 200) -> str:
    """读取 EVB 原文的 [start_line, end_line] 区间 (1-based, inclusive)。

    - 行号越界会被 clamp 到 [1, total_lines], 不抛错。
    - ``max_lines`` 上限保护, 超出会标注 truncated。
    - 文件不存在 / context 缺失 → 返回明确错误字符串。
    """
    from modem_log_analyzer import run_context as rc

    try:
        bundle = rc.require()
    except RuntimeError as e:
        return f"ERROR: {e}"

    evb_path = bundle.get("evb_log_path")
    if not evb_path:
        return "ERROR: run_context has no evb_log_path"

    p = Path(evb_path).expanduser()
    if not p.exists() or not p.is_file():
        return f"ERROR: evb log not found: {evb_path}"

    try:
        text = p.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        return f"ERROR: read failed: {e}"

    lines = text.splitlines()
    total = len(lines)
    if total == 0:
        return "ERROR: evb log is empty"

    a = max(1, int(start_line))
    b = min(int(end_line), total)
    if a > b:
        return f"ERROR: empty window after clamping; total={total}"

    window = lines[a - 1 : b]
    truncated = len(window) > max_lines
    if truncated:
        window = window[:max_lines]

    body = "\n".join(window)
    suffix = ""
    if truncated:
        suffix = f"\n... (truncated to {max_lines} lines; total {b - a + 1} requested, file has {total})"
    elif (b - a + 1) < (int(end_line) - int(start_line) + 1) or a != int(start_line) or b != int(end_line):
        suffix = f"\n... (clamped to {a}-{b}; file has {total} lines)"

    return f"[EVB {evb_path}: lines {a}-{b}]{suffix}\n{body}"


# ============================================================
# 工具 2: 读取项目级控制脚本日志(只读)
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
# 工具 3: 校验 LLM 返回的 AnalysisResult 草稿是否合法
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
        _as_simple_tool("get_preprocessed_bundle", get_preprocessed_bundle_tool),
        _as_simple_tool("read_evb_log_slice", read_evb_log_slice_tool),
        _as_simple_tool("read_control_log", read_control_log_tool),
        _as_simple_tool("validate_analysis_draft", validate_analysis_draft_tool),
    ]


__all__ = [
    "get_preprocessed_bundle_tool",
    "read_evb_log_slice_tool",
    "read_control_log_tool",
    "validate_analysis_draft_tool",
    "build_tools",
]