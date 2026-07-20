"""ModemLogAnalyzer —— ModemCLI 命令知识 (Unit 3)。

按 Plan §1 R3 + §5:
  - 命令知识从项目级 ``knowledge/modemcli_commands.yaml`` 加载。
  - ``modemcli`` 是会话入口 (业务动作 = ``session_entry``)。
  - ``debug_bes_rpc`` 是 RPC 调度; 业务动作取决于 ``args[0]``。
  - 未知命令保留为 ``unknown``, 不猜为成功。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

# 业务动作枚举(与 Plan R13 区分:这里是"业务动作",不是"诊断分类")
BUSINESS_ACTIONS = frozenset(
    {
        "session_entry",
        "call",
        "sms",
        "data_ping",
        "setting",
        "rpc_dispatch",
        "unknown",
    }
)


@dataclass(frozen=True)
class CommandSpec:
    """catalog 中的一条命令定义。"""

    name: str
    kind: str  # session_entry | rpc_dispatch | builtin | unknown
    business_action: str  # 见 BUSINESS_ACTIONS
    description: str = ""
    known_arg_ranges: tuple[dict[str, Any], ...] = field(default_factory=tuple)
    notes: str = ""

    def matches_arg(self, args: list[str]) -> dict[str, Any] | None:
        """若 args[0] 匹配某个已知子命令区间,返回该区间的元数据;否则 None。"""
        if not self.known_arg_ranges:
            return None
        try:
            first = int(args[0])
        except (ValueError, IndexError):
            return None
        for r in self.known_arg_ranges:
            lo, hi = r["range"][0], r["range"][1]
            if lo <= first <= hi:
                return r
        return None


@dataclass(frozen=True)
class CommandCatalog:
    """只读的命令知识表。"""

    version: str
    commands: tuple[CommandSpec, ...]

    def get(self, name: str) -> CommandSpec | None:
        for c in self.commands:
            if c.name == name:
                return c
        return None


def _default_catalog_path() -> Path:
    """返回项目级 catalog yaml 路径。

    顺序:
      1. env ``MODEM_LOG_ANALYZER_COMMAND_CATALOG`` 绝对路径
      2. 仓库根 ``agents/modem-log-analyzer/knowledge/modemcli_commands.yaml``
         (按当前文件位置回溯)
    """
    import os

    env_p = os.getenv("MODEM_LOG_ANALYZER_COMMAND_CATALOG")
    if env_p:
        p = Path(env_p).expanduser().resolve()
        if p.is_file():
            return p

    # this file: agents/modem-log-analyzer/src/modem_log_analyzer/command_catalog.py
    # 回溯 4 层 → modem-log-analyzer/
    here = Path(__file__).resolve()
    agent_dir = here.parents[2]
    candidate = agent_dir / "knowledge" / "modemcli_commands.yaml"
    if candidate.is_file():
        return candidate
    # 兜底: 在仓库内的全局查找
    repo_root = here.parents[3] if len(here.parents) >= 4 else here.parents[-1]
    candidate2 = (
        repo_root / "agents" / "modem-log-analyzer" / "knowledge" / "modemcli_commands.yaml"
    )
    return candidate2


def load_catalog(path: Path | None = None) -> CommandCatalog:
    """从 yaml 文件加载 catalog。

    参数:
        path: 显式路径; None 则用 ``_default_catalog_path``。
    """
    target = path or _default_catalog_path()
    if not target.is_file():
        raise FileNotFoundError(
            f"command catalog not found at {target}; "
            "set MODEM_LOG_ANALYZER_COMMAND_CATALOG or place the file at the default path."
        )
    data = yaml.safe_load(target.read_text(encoding="utf-8")) or {}
    items = data.get("commands") or data.get("items") or []
    cmds: list[CommandSpec] = []
    for item in items:
        ranges = tuple(item.get("known_arg_ranges") or ())
        cmds.append(
            CommandSpec(
                name=item["name"],
                kind=item.get("kind", "unknown"),
                business_action=item.get("business_action", "unknown"),
                description=item.get("description", ""),
                known_arg_ranges=ranges,
                notes=item.get("notes", ""),
            )
        )
    return CommandCatalog(version=str(data.get("version", "0.0.0")), commands=tuple(cmds))


def get_default_catalog() -> CommandCatalog:
    """便捷函数: 加载默认 catalog。"""
    return load_catalog()


def classify_command(name: str, args: list[str]) -> str:
    """返回命令的业务动作分类。

    规则:
      - 不在 catalog 中 → ``unknown``
      - ``session_entry`` → ``session_entry``
      - ``builtin`` → catalog.bussiness_action
      - ``rpc_dispatch`` 且 args[0] 命中 known_arg_ranges → 该 range.business_action
      - ``rpc_dispatch`` 但 args[0] 不命中 → ``unknown``(子命令未知)
    """
    cat = get_default_catalog()
    spec = cat.get(name)
    if spec is None:
        return "unknown"

    if spec.kind == "session_entry":
        return "session_entry"

    if spec.kind == "builtin":
        return spec.business_action

    if spec.kind == "rpc_dispatch":
        hit = spec.matches_arg(args)
        if hit is not None:
            return hit.get("business_action", "unknown")
        return "unknown"

    # 其它 (其它种类的 kind 一律 unknown)
    return "unknown"


__all__ = [
    "BUSINESS_ACTIONS",
    "CommandSpec",
    "CommandCatalog",
    "load_catalog",
    "get_default_catalog",
    "classify_command",
]
