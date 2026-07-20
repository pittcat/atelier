"""ModemLogAnalyzer —— EVB 日志解析器 (Unit 3)。

按 Plan Unit 3:
  - 把原始 EVB 日志文本/字节 → 稳定结构化事件流 (list[dict])。
  - ANSI 控制符 / CRLF / 空行 / 畸形 UTF-8 / 超长行: 全部 fail-safe。
  - modemcli 提示符 → ``session_entry`` 事件; 后续 debug_bes_rpc / !ping → ``command`` 事件。
  - 双时间戳 (``device_ts`` + ``capture_ts``) 与模块名 (``ap/apc1/sensor``) 都保留。
  - 未知 RPC 参数保留为 ``unknown`` (S11)。
  - 同步构造 ``evidence_refs`` 的稳定 ID (见 ``evidence.py``)。

设计原则:
  - 单遍扫描; 不调用外部依赖(除 yaml catalog 在 command_catalog 里加载)。
  - 确定性: 同一输入 → 同一输出 (S13)。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from modem_log_analyzer.command_catalog import classify_command

# ============================================================
# ANSI 转义清理 (S5)
# ============================================================
_ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]|\x1b\][^\x07]*\x07")


def _strip_ansi(text: str) -> str:
    return _ANSI_RE.sub("", text)


# ============================================================
# 行/事件结构
# ============================================================
@dataclass
class ParsedEvent:
    """一个解析后的事件。

    字段:
      kind:            "command" | "callback" | "response" | "session_entry" | "warning"
      subkind:         "session_entry" | "rpc" | "builtin" | None
      rpc:             RPC 名 (e.g. "debug_bes_rpc")
      command_name:    顶层命令字面量
      args:            参数列表
      business_action: 业务动作 (call/sms/data_ping/setting/unknown/...)
      terminal_outcome: "success" | "failure" | None(未知)
      raw_text:        原文 (清洗 ANSI 后)
      line_no:         行号 (1-based)
      device_ts:       设备时间 (string)
      capture_ts:      采集时间 (string)
      module:          模块名 (ap/apc1/sensor/...)
      warnings:        list[str]
    """

    kind: str
    raw_text: str
    line_no: int
    subkind: str | None = None
    rpc: str | None = None
    command_name: str | None = None
    args: list[str] = field(default_factory=list)
    business_action: str | None = None
    terminal_outcome: str | None = None
    device_ts: str | None = None
    capture_ts: str | None = None
    module: str | None = None
    warnings: list[str] = field(default_factory=list)


# ============================================================
# 行模式 (Plan §1 S6: 双时间戳 + 模块 + 命令)
# ============================================================
_BRACKET_RE = re.compile(r"\[([^\]]+)\]")


def _parse_line_timestamps(line: str) -> tuple[str | None, str | None, str | None, str]:
    """从行首抽取时间戳/模块前缀;返回 (device_ts, capture_ts, module, rest)。

    容错: 全部可空; rest = 去掉前缀后的行内容(去首尾空格)。
    """
    parts = _BRACKET_RE.findall(line)
    rest = _BRACKET_RE.sub("", line, count=len(parts)).strip()

    device_ts: str | None = None
    capture_ts: str | None = None
    module: str | None = None

    for p in parts:
        if "T" in p and ("Z" in p or "+" in p):
            if capture_ts is None:
                capture_ts = p
        elif "-" in p and ":" in p:
            if device_ts is None:
                device_ts = p
        elif p.isalnum() and len(p) <= 16 and any(c.isalpha() for c in p):
            if module is None:
                module = p
    return device_ts, capture_ts, module, rest


_SESSION_PROMPT_RE = re.compile(r"^\s*modemcli[>\s]+(.*)$")
_BUILTIN_CMD_RE = re.compile(r"^\s*!([a-zA-Z0-9_-]+)(?:\s+(.*))?$")


def _parse_session_prompt(rest: str) -> tuple[str, list[str]] | None:
    m = _SESSION_PROMPT_RE.match(rest)
    if not m:
        return None
    payload = m.group(1).strip()
    if not payload:
        return ("modemcli", [])
    parts = payload.split()
    return (parts[0], parts[1:])


def _parse_builtin(rest: str) -> tuple[str, list[str]] | None:
    m = _BUILTIN_CMD_RE.match(rest)
    if not m:
        return None
    cmd = "!" + m.group(1)
    rest_args = (m.group(2) or "").strip()
    args = rest_args.split() if rest_args else []
    return (cmd, args)


_RESPONSE_OK_RE = re.compile(r"\bOK\b", re.IGNORECASE)
_RESPONSE_FAIL_RE = re.compile(r"\b(FAIL|ERROR|EXCEPTION|err)\b", re.IGNORECASE)


def _classify_response(text: str) -> str | None:
    has_ok = bool(_RESPONSE_OK_RE.search(text))
    has_fail = bool(_RESPONSE_FAIL_RE.search(text))
    if has_fail and not has_ok:
        return "failure"
    if has_ok and not has_fail:
        return "success"
    return None


def parse_evb_log(raw: str | bytes) -> list[dict[str, Any]]:
    """解析 EVB 日志文本 → 事件列表 (字典,便于序列化/测试)。"""
    # bytes → str with replace
    if isinstance(raw, (bytes, bytearray)):
        try:
            raw_str = bytes(raw).decode("utf-8")
        except UnicodeDecodeError:
            raw_str = bytes(raw).decode("utf-8", errors="replace")
    else:
        raw_str = str(raw)

    try:
        cleaned = _strip_ansi(raw_str)
    except Exception:
        cleaned = raw_str

    lines = cleaned.splitlines()
    events: list[dict[str, Any]] = []
    warnings_global: list[str] = []

    for i, raw_line in enumerate(lines, start=1):
        line = raw_line.rstrip("\r\n").rstrip()
        if not line.strip():
            continue

        # 畸形 UTF-8 字节在解码时已被替换为 U+FFFD; 检测它作为 warning
        line_warnings: list[str] = []
        if "\ufffd" in line:
            line_warnings.append("malformed_utf8")

        device_ts, capture_ts, module, rest = _parse_line_timestamps(line)
        if not rest:
            events.append(
                {
                    "kind": "raw",
                    "raw_text": line,
                    "line_no": i,
                    "device_ts": device_ts,
                    "capture_ts": capture_ts,
                    "module": module,
                    "warnings": line_warnings,
                }
            )
            continue

        session_cmd = _parse_session_prompt(rest)
        if session_cmd is not None:
            cmd_name, args = session_cmd
            events.append(
                {
                    "kind": "session_entry",
                    "subkind": "session_entry",
                    "command_name": cmd_name,
                    "args": [],
                    "rpc": None,
                    "raw_text": line,
                    "line_no": i,
                    "device_ts": device_ts,
                    "capture_ts": capture_ts,
                    "module": module,
                    "business_action": "session_entry",
                    "terminal_outcome": None,
                    "warnings": line_warnings,
                }
            )
            if args:
                events.append(
                    _build_command_event(
                        cmd_name,
                        args,
                        line,
                        i,
                        device_ts,
                        capture_ts,
                        module,
                        line_warnings,
                    )
                )
            continue

        builtin = _parse_builtin(rest)
        if builtin is not None:
            cmd_name, args = builtin
            events.append(
                _build_command_event(
                    cmd_name,
                    args,
                    line,
                    i,
                    device_ts,
                    capture_ts,
                    module,
                    line_warnings,
                )
            )
            continue

        outcome = _classify_response(rest)
        events.append(
            {
                "kind": "callback" if (device_ts or capture_ts or module) else "response",
                "subkind": None,
                "command_name": None,
                "args": [],
                "rpc": None,
                "raw_text": line,
                "line_no": i,
                "device_ts": device_ts,
                "capture_ts": capture_ts,
                "module": module,
                "business_action": None,
                "terminal_outcome": outcome,
                "warnings": line_warnings,
            }
        )

    # 全局 warning: 任意行包含畸形 UTF-8 替换符 -> 顶层加 warning 事件。
    if any("\ufffd" in (ev.get("raw_text") or "") for ev in events):
        warnings_global.append("malformed_utf8_in_input")
    if warnings_global:
        events.append(
            {
                "kind": "warning",
                "raw_text": "",
                "line_no": 0,
                "warnings": warnings_global,
            }
        )

    return events


def _build_command_event(
    cmd_name: str,
    args: list[str],
    line: str,
    line_no: int,
    device_ts: str | None,
    capture_ts: str | None,
    module: str | None,
    line_warnings: list[str] | None = None,
) -> dict[str, Any]:
    action = classify_command(cmd_name, args)

    subkind = "builtin"
    rpc = None
    if cmd_name == "debug_bes_rpc":
        subkind = "rpc"
        rpc = "debug_bes_rpc"
    elif cmd_name.startswith("!"):
        subkind = "builtin"

    return {
        "kind": "command",
        "subkind": subkind,
        "command_name": cmd_name,
        "args": list(args),
        "rpc": rpc,
        "raw_text": line,
        "line_no": line_no,
        "device_ts": device_ts,
        "capture_ts": capture_ts,
        "module": module,
        "business_action": action,
        "terminal_outcome": None,
        "warnings": list(line_warnings or []),
    }


__all__ = ["ParsedEvent", "parse_evb_log"]
