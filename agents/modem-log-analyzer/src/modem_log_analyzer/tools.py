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
def get_preprocessed_bundle_tool(_: str = "") -> str:
    """返回本 run 的预处理结果 (JSON 字符串)。

    内容包括: run_label / command_summary / evidence_refs (EV-NNNN) /
    control_summary (若提供)。

    必须在 runner 已 set run_context 时调用; 否则返回明确错误字符串,
    防止 Agent 误以为工具静默可用。

    占位参数 ``_`` 仅用于让 langchain StructuredTool 的 args schema 推断稳定
    (零参数工具在不同 langchain 版本下 invoke({}) 行为不一致)。
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
# 工具 2: 读取项目级控制脚本日志(只读; 路径从 run_context 取, 禁止任意路径)
# ============================================================
def read_control_log_tool(max_lines: int = 2000) -> str:
    """Read the control-script log attached to the current run.

    控制日志路径**只能**从 ``run_context`` bundle 读取 —— 不接受 Agent 传入的
    任意路径参数, 避免被 prompt 注入利用来读 ``/etc/passwd`` 等敏感文件。

    返回: 文本 (或 ``ERROR: ...`` 字符串)。
    """
    from modem_log_analyzer import run_context as rc

    try:
        bundle = rc.require()
    except RuntimeError as e:
        return f"ERROR: {e}"

    log_path = bundle.get("control_log_path")
    if not log_path:
        return "ERROR: run_context has no control_log_path (--control-log not provided)"

    p = Path(log_path).expanduser()
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
    """Validate a candidate AnalysisResult draft against schema + spine rules."""
    from modem_log_analyzer.spine_validate import validate_analysis_draft

    result = validate_analysis_draft(candidate)
    if not result.is_valid:
        return f"INVALID: {result.reason}"
    try:
        from modem_log_analyzer.contracts import AnalysisResult

        parsed = AnalysisResult.model_validate(candidate)
        return f"VALID classification={parsed.classification.value}"
    except Exception as e:  # noqa: BLE001
        return f"INVALID: {e!s}"


# ============================================================
# 工厂: 主代理可用工具集
# ============================================================
def build_tools() -> list:
    """主代理可用工具合集。

    返回 ``list[BaseTool]``(deepagents / langgraph 能直接消费)。
    优先返回 langchain 工具 (``@tool`` 装饰对象); 在没有安装 langchain_core
    的测试环境, 退化为轻量 ``SimpleTool`` 替身, 它们通过 ``.name`` /
    ``.invoke({...})`` 接口可被静态测试校验。
    """
    from modem_log_analyzer.tools_simple import try_langchain_tool

    _assert_no_push()

    return [
        try_langchain_tool(
            "get_preprocessed_bundle",
            get_preprocessed_bundle_tool,
            description="Return the current run preprocess bundle (run_label, command_summary, evidence_refs EV-NNNN, control_summary, interrupt_request). Requires runner.run_context to be set.",
        ),
        try_langchain_tool(
            "read_evb_log_slice",
            read_evb_log_slice_tool,
            description="Read a line window [start_line, end_line] (1-based, inclusive) from the current run EVB log. max_lines caps the window; truncated output is annotated.",
        ),
        try_langchain_tool(
            "read_control_log",
            read_control_log_tool,
            description="Read a control-script log file (only available when CLI was invoked with --control-log).",
        ),
        try_langchain_tool(
            "validate_analysis_draft",
            validate_analysis_draft_tool,
            description="Validate a candidate AnalysisResult dict against the public schema; returns 'VALID classification=...' or 'INVALID: ...'.",
        ),
    ]


__all__ = [
    "get_preprocessed_bundle_tool",
    "read_evb_log_slice_tool",
    "read_control_log_tool",
    "validate_analysis_draft_tool",
    "build_tools",
]
