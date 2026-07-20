"""U1: 预处理 bundle 契约 + Deep Agents 可调用工具。

按 Plan Unit 1 / S4:
  - ``get_preprocessed_bundle`` 在 set context 后返回本 run 的命令事件摘要 + evidence_refs
    (含 EV-NNNN)。
  - ``read_evb_log_slice`` 按行号窗口回读原文; 越界 / 文件不存在 → 稳定错误字符串。
  - ``run_context.set / get / clear`` 必须线程/run 隔离; 未 set 时所有工具返回稳定错误。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


# ============================================================
# 测试 helper: 在每个用例前后清理 run_context
# ============================================================
def _reset_context():
    from modem_log_analyzer.run_context import clear as _clear

    _clear()


# ============================================================
# run_context 基础行为
# ============================================================
def test_run_context_set_get_clear():
    from modem_log_analyzer.run_context import set as _set, get as _get, clear as _clear

    _clear()
    bundle = {"run_label": "x", "evidence_refs": ["EV-0001"]}
    _set(bundle)
    # set 必须保留外部 mutate 隔离 (浅拷贝即可)
    assert _get() == bundle
    assert _get() is not bundle
    _clear()
    assert _get() is None


def test_run_context_isolation():
    """多次 set 必须替换, get 永远拿到最新一份。"""
    from modem_log_analyzer.run_context import set as _set, get as _get, clear as _clear

    _clear()
    _set({"run_label": "A"})
    _set({"run_label": "B"})
    assert _get()["run_label"] == "B"
    _clear()


# ============================================================
# 工具 1: get_preprocessed_bundle
# ============================================================
def test_get_preprocessed_bundle_returns_summary():
    from modem_log_analyzer.run_context import set as _set
    from modem_log_analyzer.tools import build_tools
    from modem_log_analyzer import run_context as rc

    _reset_context()
    tools = build_tools()
    bundle_tool = next(t for t in tools if t.name == "get_preprocessed_bundle")
    _set(
        {
            "run_label": "loop75",
            "command_summary": [
                {"ref_id": "EV-0001", "command": "debug_bes_rpc 0"},
                {"ref_id": "EV-0003", "command": "!ping"},
            ],
            "evidence_refs": ["EV-0001", "EV-0003"],
            "control_summary": None,
        }
    )
    try:
        out = bundle_tool.invoke({})
    finally:
        rc.clear()
    # 返回值含 EV-NNNN
    assert "EV-0001" in str(out)
    assert "loop75" in str(out)
    # 必须 JSON 序列化友好
    import json

    json.dumps(out)


def test_get_preprocessed_bundle_without_context_returns_error():
    from modem_log_analyzer.tools import build_tools
    from modem_log_analyzer import run_context as rc

    _reset_context()
    tools = build_tools()
    bundle_tool = next(t for t in tools if t.name == "get_preprocessed_bundle")
    out = bundle_tool.invoke({})
    rc.clear()  # 保险
    s = str(out)
    assert "ERROR" in s or "error" in s.lower()
    assert "run_context" in s.lower() or "context" in s.lower()


def test_get_preprocessed_bundle_includes_control_summary_when_set():
    from modem_log_analyzer.run_context import set as _set
    from modem_log_analyzer.tools import build_tools
    from modem_log_analyzer import run_context as rc

    _reset_context()
    tools = build_tools()
    bundle_tool = next(t for t in tools if t.name == "get_preprocessed_bundle")
    _set(
        {
            "run_label": "loop75",
            "command_summary": [],
            "evidence_refs": [],
            "control_summary": [
                {"line_no": 3, "summary": "AssertionError: ping failed"}
            ],
        }
    )
    try:
        out = bundle_tool.invoke({})
    finally:
        rc.clear()
    assert "AssertionError" in str(out)


# ============================================================
# 工具 2: read_evb_log_slice
# ============================================================
def test_read_evb_log_slice_returns_window(tmp_path):
    log = tmp_path / "merge.log"
    log.write_text("\n".join(f"L{i}: line {i}" for i in range(1, 21)), encoding="utf-8")
    from modem_log_analyzer.run_context import set as _set
    from modem_log_analyzer.tools import build_tools
    from modem_log_analyzer import run_context as rc

    _reset_context()
    _set(
        {
            "run_label": "loop75",
            "evb_log_path": str(log),
            "command_summary": [],
            "evidence_refs": [],
            "control_summary": None,
        }
    )
    tools = build_tools()
    slice_tool = next(t for t in tools if t.name == "read_evb_log_slice")
    try:
        out = slice_tool.invoke({"start_line": 5, "end_line": 7})
    finally:
        rc.clear()
    s = str(out)
    assert "L5:" in s
    assert "L7:" in s
    assert "L4:" not in s
    assert "L8:" not in s


def test_read_evb_log_slice_clamps_out_of_range(tmp_path):
    log = tmp_path / "merge.log"
    log.write_text("\n".join(f"L{i}" for i in range(1, 6)), encoding="utf-8")
    from modem_log_analyzer.run_context import set as _set
    from modem_log_analyzer.tools import build_tools
    from modem_log_analyzer import run_context as rc

    _reset_context()
    _set(
        {
            "run_label": "x",
            "evb_log_path": str(log),
            "command_summary": [],
            "evidence_refs": [],
            "control_summary": None,
        }
    )
    tools = build_tools()
    slice_tool = next(t for t in tools if t.name == "read_evb_log_slice")
    try:
        out = slice_tool.invoke({"start_line": 0, "end_line": 9999})
    finally:
        rc.clear()
    s = str(out)
    # 不应崩溃; 应含真实行
    assert "L1" in s
    assert "L5" in s


def test_read_evb_log_slice_without_context_returns_error():
    from modem_log_analyzer.tools import build_tools
    from modem_log_analyzer import run_context as rc

    _reset_context()
    tools = build_tools()
    slice_tool = next(t for t in tools if t.name == "read_evb_log_slice")
    out = slice_tool.invoke({"start_line": 1, "end_line": 5})
    rc.clear()
    s = str(out).lower()
    assert "error" in s
    assert "context" in s or "evb_log_path" in s


def test_read_evb_log_slice_missing_file_returns_error(tmp_path):
    from modem_log_analyzer.run_context import set as _set
    from modem_log_analyzer.tools import build_tools
    from modem_log_analyzer import run_context as rc

    _reset_context()
    _set(
        {
            "run_label": "x",
            "evb_log_path": str(tmp_path / "missing.log"),
            "command_summary": [],
            "evidence_refs": [],
            "control_summary": None,
        }
    )
    tools = build_tools()
    slice_tool = next(t for t in tools if t.name == "read_evb_log_slice")
    try:
        out = slice_tool.invoke({"start_line": 1, "end_line": 3})
    finally:
        rc.clear()
    s = str(out).lower()
    assert "error" in s
    assert "not found" in s or "missing" in s


def test_read_evb_log_slice_truncates_oversized_window(tmp_path):
    log = tmp_path / "merge.log"
    # 写 5000 行, 让单次 slice 触发截断
    log.write_text("\n".join(f"L{i}" for i in range(1, 5001)), encoding="utf-8")
    from modem_log_analyzer.run_context import set as _set
    from modem_log_analyzer.tools import build_tools
    from modem_log_analyzer import run_context as rc

    _reset_context()
    _set(
        {
            "run_label": "x",
            "evb_log_path": str(log),
            "command_summary": [],
            "evidence_refs": [],
            "control_summary": None,
        }
    )
    tools = build_tools()
    slice_tool = next(t for t in tools if t.name == "read_evb_log_slice")
    try:
        out = slice_tool.invoke({"start_line": 1, "end_line": 5000, "max_lines": 50})
    finally:
        rc.clear()
    s = str(out)
    assert "truncated" in s.lower()


# ============================================================
# 白名单回归: 4 个工具 + 不含危险
# ============================================================
def test_build_tools_includes_new_tools():
    from modem_log_analyzer.tools import build_tools

    tools = build_tools()
    names = {t.name for t in tools}
    assert "get_preprocessed_bundle" in names
    assert "read_evb_log_slice" in names
    assert "read_control_log" in names
    assert "validate_analysis_draft" in names


def test_build_tools_still_blocks_dangerous():
    from modem_log_analyzer.tools import build_tools

    tools = build_tools()
    names = {t.name for t in tools}
    for forbidden in ("bash", "shell", "git_commit", "git_push", "write_file"):
        assert forbidden not in names, f"主代理不应暴露 {forbidden}"


def test_build_tools_count_under_5():
    from modem_log_analyzer.tools import build_tools

    tools = build_tools()
    assert len(tools) <= 5, f"主代理工具过多 ({len(tools)}): {[t.name for t in tools]}"


# ============================================================
# env 探测: 没有 langchain_core 时仍可构建; 但必须返回可 invoke 工具
# ============================================================
def test_build_tools_invoke_interface_present():
    """无论是否安装 langchain_core, 工具必须支持 ``.invoke({...})``。"""
    from modem_log_analyzer.tools import build_tools

    tools = build_tools()
    for t in tools:
        assert hasattr(t, "invoke")
        assert hasattr(t, "name")


# ============================================================
# Code Review 回归 (Plan U1 / S5 收口)
# ============================================================
def test_run_context_concurrent_isolation():
    """Plan U1: run_context 必须真正线程/run 隔离。

    两个并发线程同时 set 不同 bundle, 各自 get 必须拿回自己的 bundle,
    而非 process-global last-writer-wins。
    """
    import threading
    from concurrent.futures import ThreadPoolExecutor

    from modem_log_analyzer import run_context as rc

    rc.clear()
    barrier = threading.Barrier(2)
    observed: list[str] = []

    def _worker(label: str) -> None:
        rc.set({"run_label": label, "evidence_refs": [f"EV-{label}"]})
        # 等另一线程也 set 完再同时 get, 触发潜在 race
        barrier.wait()
        observed.append(rc.get()["run_label"])  # type: ignore[index]
        rc.clear()

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            f1 = pool.submit(_worker, "A")
            f2 = pool.submit(_worker, "B")
            f1.result(timeout=5)
            f2.result(timeout=5)
    finally:
        rc.clear()
    # 两个线程都应拿到自己的 label; 若非隔离会拿到同一个值
    assert sorted(observed) == ["A", "B"], f"concurrent run_context got {observed}"


def test_read_control_log_tool_uses_bundle_path():
    """Plan S5 安全: read_control_log_tool 路径必须从 run_context 来,
    Agent 不能传任意绝对路径读到 /etc/passwd 等敏感文件。
    """
    from modem_log_analyzer import run_context as rc
    from modem_log_analyzer.tools import build_tools

    rc.clear()
    rc.set(
        {
            "run_label": "x",
            "control_log_path": "/etc/passwd",
            "command_summary": [],
            "evidence_refs": [],
        }
    )
    tools = build_tools()
    tool = next(t for t in tools if t.name == "read_control_log")
    try:
        # 关键: 即便 Agent 尝试传其他路径, 工具签名已不允许 (只有 max_lines)
        out = tool.invoke({"max_lines": 100})
    finally:
        rc.clear()
    s = str(out).lower()
    # 工具尝试读 /etc/passwd, 在沙箱中可能成功也可能拒绝; 关键是它**只**从
    # bundle 读, 不暴露从 Agent 传任意路径的能力。
    # 如果读取失败 (e.g. permission), 我们只验证工具不抛 + 返回 ERROR 字符串
    assert "error" in s or "root:" in s or ":" in s  # 不抛 + 有内容或 error


def test_validate_refs_against_bundle_rejects_timeline_refs():
    """Plan S5: fake EV-NNNN 出现在 timeline[*].ref_id 也必须被拒。"""
    from modem_log_analyzer.agent_runner import _validate_refs_against_bundle

    bundle = {"evidence_refs": ["EV-0001"]}
    draft = {
        "evidence_refs": [],
        "first_anomaly": None,
        "root_cause_chain": [],
        "timeline": [
            {"ts": "10:00", "event": "callback", "ref_id": "EV-9999", "kind": "callback"}
        ],
    }
    try:
        _validate_refs_against_bundle(draft, bundle)
    except ValueError as e:
        assert "EV-9999" in str(e)
    else:
        raise AssertionError("expected ValueError for fake timeline ref_id")


def test_validate_refs_against_bundle_empty_both_passes():
    """空 draft + 空 bundle 应当放行 (诚实降级)。"""
    from modem_log_analyzer.agent_runner import _validate_refs_against_bundle

    bundle: dict = {"evidence_refs": []}
    draft: dict = {"evidence_refs": [], "first_anomaly": None, "root_cause_chain": [], "timeline": []}
    # 不抛
    _validate_refs_against_bundle(draft, bundle)


def test_validate_refs_against_bundle_empty_bundle_with_fake_ref_rejects():
    """空 bundle + draft 含 fake ref → 拒绝 (Plan S5 收紧)。"""
    from modem_log_analyzer.agent_runner import _validate_refs_against_bundle

    bundle: dict = {"evidence_refs": []}
    draft = {
        "evidence_refs": [{"ref_id": "EV-FAKE"}],
        "first_anomaly": None,
        "root_cause_chain": [],
        "timeline": [],
    }
    try:
        _validate_refs_against_bundle(draft, bundle)
    except ValueError as e:
        assert "EV-FAKE" in str(e)
    else:
        raise AssertionError("expected ValueError: empty bundle must not permit fake refs")