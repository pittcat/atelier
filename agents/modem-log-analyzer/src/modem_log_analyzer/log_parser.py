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
# 真实 merge.log: ``<ISO-Z>\t<device line>``（多串口按采集时间合并）
_ISO_CAPTURE_RE = re.compile(
    r"^(?P<capture>\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z)\s+"
)
_DEVICE_DATE_BRACKET_RE = re.compile(
    r"^(?P<date>\d{4}-\d{2}-\d{2})\s+\[(?P<tod>\d{2}:\d{2}:\d{2}(?:\.\d+)?)\]\s*"
)
_KNOWN_MODULES = frozenset({"ap", "apc1", "sensor", "cp", "modem", "ril"})


def _split_merge_capture_prefix(line: str) -> tuple[str | None, str]:
    """拆分 merge.log 行首采集时间; 支持 Tab 或空白分隔。"""
    if "\t" in line:
        left, right = line.split("\t", 1)
        left = left.strip()
        if _ISO_CAPTURE_RE.match(left + " "):
            return left, right
    m = _ISO_CAPTURE_RE.match(line)
    if m:
        return m.group("capture"), line[m.end() :]
    return None, line


def _parse_line_timestamps(line: str) -> tuple[str | None, str | None, str | None, str]:
    """从行首抽取时间戳/模块前缀;返回 (device_ts, capture_ts, module, rest)。

    支持两种输入:
      1. 合成 fixture: ``[device_ts][capture_ts][module] rest``
      2. 真实 merge.log: ``capture_iso\\tYYYY-MM-DD [HH:MM:SS...] [uptime] [cpu] [module] rest``

    容错: 全部可空; rest = 去掉前缀后的行内容(去首尾空格)。
    """
    capture_from_merge, payload = _split_merge_capture_prefix(line)
    working = payload if capture_from_merge is not None else line

    device_ts: str | None = None
    capture_ts: str | None = capture_from_merge
    module: str | None = None

    # 真实板端前缀: ``2026-05-27 [21:33:58.165511] ...``
    m_dev = _DEVICE_DATE_BRACKET_RE.match(working)
    if m_dev:
        device_ts = f"{m_dev.group('date')} {m_dev.group('tod')}"
        working = working[m_dev.end() :]

    parts = _BRACKET_RE.findall(working)
    # 只剥时间戳/模块/数值壳, 保留正文括号内容
    strip_count = 0
    for p in parts:
        p_stripped = p.strip()
        if "T" in p_stripped and ("Z" in p_stripped or "+" in p_stripped):
            if capture_ts is None:
                capture_ts = p_stripped
            strip_count += 1
        elif "-" in p_stripped and ":" in p_stripped:
            if device_ts is None:
                device_ts = p_stripped
            strip_count += 1
        elif p_stripped.replace(".", "", 1).replace(" ", "").isdigit():
            # uptime / cpu id 壳: ``[ 8241.761800]`` / ``[ 0]`` / ``[62]``
            strip_count += 1
        elif p_stripped.lower() in _KNOWN_MODULES or (
            p_stripped.isalnum() and len(p_stripped) <= 16 and any(c.isalpha() for c in p_stripped)
        ):
            if module is None:
                module = p_stripped.lower() if p_stripped.lower() in _KNOWN_MODULES else p_stripped
            strip_count += 1
        else:
            break

    rest = _BRACKET_RE.sub("", working, count=strip_count).strip() if strip_count else working.strip()
    return device_ts, capture_ts, module, rest


_SESSION_PROMPT_RE = re.compile(r"^\s*modemcli[>\s]+(.*)$")
_BUILTIN_CMD_RE = re.compile(r"^\s*!([a-zA-Z0-9_-]+)(?:\s+(.*))?$")
_PLAUSIBLE_CMD_RE = re.compile(r"^(?:debug_bes_rpc|![A-Za-z][A-Za-z0-9_-]*)$")


def _is_plausible_command_name(cmd_name: str) -> bool:
    """modemcli> 后跟的必须是已知/可识别命令, 不能把 ping 回显当成命令。"""
    if not cmd_name:
        return False
    if _PLAUSIBLE_CMD_RE.match(cmd_name):
        return True
    try:
        from modem_log_analyzer.command_catalog import get_default_catalog

        return get_default_catalog().get(cmd_name) is not None
    except Exception:
        return False


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


_RESPONSE_OK_RE = re.compile(
    r"\bOK\b|\bbytes from\b|\bping\s+OK\b|\bifconfig ok\b",
    re.IGNORECASE,
)
_RESPONSE_FAIL_RE = re.compile(
    r"\b(FAIL|ERROR|EXCEPTION|TIMEOUT)\b|"
    r"\bNo response from\b|"
    r"\bassertion\s+failed\b|"
    r"\bcheck ping\b.*\bfail\b",
    re.IGNORECASE,
)
# 板端噪声 ERROR: 不构成业务失败 (真实 merge.log 常见)
_NOISE_FAILURE_RE = re.compile(
    r"RingPlayOnce|no ring file|OFONO_DFX|CPU USAGE",
    re.IGNORECASE,
)


def _classify_response(text: str) -> str | None:
    if _NOISE_FAILURE_RE.search(text):
        return None
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
            # 始终记 modemcli 会话入口 (Plan R3)
            events.append(
                {
                    "kind": "session_entry",
                    "subkind": "session_entry",
                    "command_name": "modemcli",
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
            # prompt 后若是可识别命令 → 再发 command; 否则当回显/响应
            if cmd_name and cmd_name != "modemcli":
                if _is_plausible_command_name(cmd_name):
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
                else:
                    outcome = _classify_response(rest)
                    events.append(
                        {
                            "kind": "callback",
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
