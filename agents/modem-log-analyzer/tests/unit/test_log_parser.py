"""Unit 3 测试: log_parser / evidence / command_catalog。

按 Plan Unit 3:
  - 将 EVB 日志字节/文本 → 规范化事件、命令事件、解析警告和证据索引。
  - 不调用 LLM, 不下诊断结论。
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


# ============================================================
# ANSI / CRLF / 空行
# ============================================================


def test_parser_strips_ansi_escape_codes():
    from modem_log_analyzer.log_parser import parse_evb_log

    raw = "\x1b[32mmodemcli>\x1b[0m debug_bes_rpc 1 0\r\n"
    events = parse_evb_log(raw)
    # 第一个事件应该是会话入口识别, 第二个应该是命令识别
    assert any(ev["kind"] == "command" for ev in events)
    # 命令原文不应含 ANSI
    cmd_events = [ev for ev in events if ev["kind"] == "command"]
    assert "\x1b" not in cmd_events[0]["raw_text"]


def test_parser_handles_crlf_line_endings():
    from modem_log_analyzer.log_parser import parse_evb_log

    raw = "modemcli> debug_bes_rpc 1 0\r\nOK\r\n"
    events = parse_evb_log(raw)
    assert any(ev["kind"] == "command" for ev in events)


def test_parser_skips_empty_lines():
    from modem_log_analyzer.log_parser import parse_evb_log

    raw = "\n\nmodemcli> debug_bes_rpc 1 0\n\nOK\n\n"
    events = parse_evb_log(raw)
    assert all(ev.get("kind") != "empty" for ev in events)


def test_parser_handles_malformed_utf8():
    """畸形 UTF-8 字节不应让 parser 崩溃。"""
    from modem_log_analyzer.log_parser import parse_evb_log

    raw_bytes = b"modemcli> debug_bes_rpc 1 0\n\xff\xfeINVALID\n"
    raw = raw_bytes.decode("utf-8", errors="replace")
    events = parse_evb_log(raw)
    assert any(ev["kind"] == "command" for ev in events)
    # 含 malformed 字节的事件应有 warning (顶层 warning 事件 或 行级 warning 列表)
    has_warning = any("malformed_utf8" in (ev.get("warnings") or []) for ev in events)
    assert has_warning, (
        f"expected malformed_utf8 warning, got events={[ev.get('kind') for ev in events]}"
    )


def test_parser_handles_very_long_lines():
    """超长行不应让 parser 崩溃。"""
    from modem_log_analyzer.log_parser import parse_evb_log

    long_line = "x" * 10000
    raw = f"modemcli> debug_bes_rpc 1 0\n{long_line}\n"
    events = parse_evb_log(raw)
    # 即使很长,也应有 command 事件
    assert any(ev["kind"] == "command" for ev in events)


# ============================================================
# modemcli 会话入口
# ============================================================


def test_modemcli_prompt_recognized_as_session_entry_not_business_action():
    """modemcli 提示符是会话入口, 不是业务动作。"""
    from modem_log_analyzer.log_parser import parse_evb_log

    raw = "modemcli> debug_bes_rpc 1 0\nOK\n"
    events = parse_evb_log(raw)
    session_entries = [ev for ev in events if ev.get("subkind") == "session_entry"]
    business_commands = [ev for ev in events if ev["kind"] == "command"]
    # modemcli 行应被识别为 session_entry (不是 command)
    assert len(session_entries) >= 1
    # 后续 debug_bes_rpc 才是 command
    assert any(ev.get("rpc") == "debug_bes_rpc" for ev in business_commands)


def test_parser_extracts_debug_bes_rpc_command():
    """debug_bes_rpc 1 0 应被解析为 command + rpc + 参数。"""
    from modem_log_analyzer.log_parser import parse_evb_log

    raw = "modemcli> debug_bes_rpc 1 0\n"
    events = parse_evb_log(raw)
    cmds = [ev for ev in events if ev["kind"] == "command"]
    assert len(cmds) == 1
    cmd = cmds[0]
    assert cmd.get("rpc") == "debug_bes_rpc"
    assert cmd.get("args") == ["1", "0"]


# ============================================================
# 双时间戳 + 模块标签
# ============================================================


def test_parser_preserves_dual_timestamps():
    """设备时间与采集时间都应保留,不混淆。"""
    from modem_log_analyzer.log_parser import parse_evb_log

    raw = "[2026-07-19 10:00:00.123][2026-07-19T02:00:00.123Z][ap] modemcli> debug_bes_rpc 1 0\n"
    events = parse_evb_log(raw)
    cmd = next(ev for ev in events if ev["kind"] == "command")
    assert cmd.get("device_ts") == "2026-07-19 10:00:00.123"
    assert cmd.get("capture_ts") == "2026-07-19T02:00:00.123Z"
    assert cmd.get("module") == "ap"


def test_parser_handles_missing_timestamps_gracefully():
    """缺时间戳不应让 parser 失败。"""
    from modem_log_analyzer.log_parser import parse_evb_log

    raw = "modemcli> debug_bes_rpc 1 0\n"
    events = parse_evb_log(raw)
    cmd = next(ev for ev in events if ev["kind"] == "command")
    # 至少 command 字段被识别
    assert cmd["rpc"] == "debug_bes_rpc"


# ============================================================
# 多模块
# ============================================================


def test_parser_distinguishes_multiple_modules():
    """ap / apc1 / sensor 等模块都应被识别。"""
    from modem_log_analyzer.log_parser import parse_evb_log

    raw = (
        "[2026-07-19 10:00:00.000][ap] modemcli> debug_bes_rpc 1 0\n"
        "[2026-07-19 10:00:01.000][apc1] callback OK\n"
        "[2026-07-19 10:00:02.000][sensor] temperature 25\n"
    )
    events = parse_evb_log(raw)
    modules = {ev.get("module") for ev in events if ev.get("module")}
    assert {"ap", "apc1", "sensor"} <= modules


# ============================================================
# 未知 RPC 参数 (S11)
# ============================================================


def test_unknown_rpc_parameters_marked_as_unknown():
    """命令知识表未覆盖的 debug_bes_rpc 参数应保留为 unknown。"""
    from modem_log_analyzer.log_parser import parse_evb_log

    raw = "modemcli> debug_bes_rpc 99 88 77\n"
    events = parse_evb_log(raw)
    cmds = [ev for ev in events if ev["kind"] == "command"]
    assert len(cmds) == 1
    cmd = cmds[0]
    # rpc 名已知,但参数范围不在 catalog, 应标记 unknown_or_uncertain
    assert cmd.get("rpc") == "debug_bes_rpc"
    # 业务语义为 unknown
    assert cmd.get("business_action") in (None, "unknown", "uncertain", "uncategorized")


def test_completely_unknown_rpc_command_kept_as_unknown():
    """modemcli> 后跟非可识别命令 → 当作回显/响应, 不得猜为成功业务命令。"""
    from modem_log_analyzer.log_parser import parse_evb_log

    raw = "modemcli> some_unknown_command arg1 arg2\n"
    events = parse_evb_log(raw)
    cmds = [ev for ev in events if ev["kind"] == "command"]
    assert cmds == []
    # 仍应有 session_entry + callback/response
    assert any(ev["kind"] == "session_entry" for ev in events)
    echo = next(ev for ev in events if ev["kind"] in ("callback", "response"))
    assert echo.get("terminal_outcome") != "success"
    assert "some_unknown_command" in (echo.get("raw_text") or "")


# ============================================================
# 命令重复回显
# ============================================================


def test_parser_keeps_command_echo_separate_from_response():
    """modemcli 命令回显与后续回调应分离为不同事件。"""
    from modem_log_analyzer.log_parser import parse_evb_log

    raw = "modemcli> debug_bes_rpc 1 0\n[2026-07-19 10:00:01.000][apc1] OK\n"
    events = parse_evb_log(raw)
    # 至少有 1 个 command 事件和 1 个 callback/response 事件
    kinds = [ev["kind"] for ev in events]
    assert "command" in kinds
    assert any(k in ("callback", "response") for k in kinds)


# ============================================================
# 稳定 evidence refs
# ============================================================


def test_evidence_refs_are_stable_across_runs():
    """同一文件 → 同一 evidence refs (S13: 稳定诊断核心)。"""
    from modem_log_analyzer.evidence import build_evidence_index
    from modem_log_analyzer.log_parser import parse_evb_log

    raw = (
        "[2026-07-19 10:00:00.000][ap] modemcli> debug_bes_rpc 1 0\n"
        "[2026-07-19 10:00:01.000][apc1] OK\n"
    )
    events_a = parse_evb_log(raw)
    events_b = parse_evb_log(raw)
    idx_a = build_evidence_index(events_a, source="evb.log")
    idx_b = build_evidence_index(events_b, source="evb.log")
    # ref_id 列表必须完全一致
    ids_a = sorted(ev.ref_id for ev in idx_a)
    ids_b = sorted(ev.ref_id for ev in idx_b)
    assert ids_a == ids_b
    # raw_text 也必须一致
    for ev_a, ev_b in zip(idx_a, idx_b, strict=True):
        assert ev_a.raw_text == ev_b.raw_text
        assert ev_a.line_no == ev_b.line_no


def test_evidence_refs_include_source_and_line_no():
    from modem_log_analyzer.evidence import build_evidence_index
    from modem_log_analyzer.log_parser import parse_evb_log

    raw = "[2026-07-19 10:00:00.000][ap] modemcli> debug_bes_rpc 1 0\n"
    events = parse_evb_log(raw)
    idx = build_evidence_index(events, source="evb.log")
    assert len(idx) >= 1
    for ev in idx:
        assert ev.source == "evb.log"
        assert ev.line_no is not None
        assert ev.raw_text  # 非空
        assert ev.ref_id.startswith("EV-")


def test_parser_handles_real_merge_log_format():
    """真实 merge.log: ISO 采集时间 + Tab + 板端行; 含 ANSI 与 !ifconfig 无参。"""
    from modem_log_analyzer.log_parser import parse_evb_log

    raw = (
        "2026-05-27T13:34:00.931Z\t2026-05-27 [21:34:00.931213] modemcli> \x1b[K!ifconfig\n"
        "2026-05-27T13:34:12.397Z\t2026-05-27 [21:34:12.397632] modemcli> \x1b[K!ping -c 60 map.baidu.com &\n"
        "2026-05-27T13:34:12.605Z\t2026-05-27 [21:34:12.605222] modemcli> \x1b[KNo response from 1.1.1.1: icmp_seq=0 time=1000 ms\n"
        "2026-05-27T13:34:34.331Z\t2026-05-27 [21:34:34.331612] modemcli> \x1b[Kdebug_bes_rpc 4 1 10086 hello\n"
    )
    events = parse_evb_log(raw)
    cmds = [e for e in events if e["kind"] == "command"]
    names = [c["command_name"] for c in cmds]
    assert "!ifconfig" in names
    assert "!ping" in names
    assert "debug_bes_rpc" in names
    # ping 回显不得当成命令
    assert "No" not in names
    assert all(not (n and n[0].isdigit()) for n in names)

    ping = next(c for c in cmds if c["command_name"] == "!ping")
    assert ping["capture_ts"] == "2026-05-27T13:34:12.397Z"
    assert ping["business_action"] == "data_ping"

    sms = next(c for c in cmds if c["command_name"] == "debug_bes_rpc")
    assert sms["business_action"] == "sms"

    no_resp = next(
        e
        for e in events
        if e.get("kind") == "callback" and "No response from" in (e.get("raw_text") or "")
    )
    assert no_resp.get("terminal_outcome") == "failure"
