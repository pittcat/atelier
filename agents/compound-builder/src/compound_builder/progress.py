"""CLI 进度输出 —— 全部走 stderr,不污染 stdout JSON。"""
from __future__ import annotations

import os
import sys
from datetime import datetime


def progress(msg: str) -> None:
    if os.getenv("ATELIER_QUIET", "").lower() in ("1", "true", "yes"):
        return
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", file=sys.stderr, flush=True)


def progress_node(node: str, patch: dict) -> None:
    """从节点 delta 提取可读一行进度。"""
    if os.getenv("ATELIER_QUIET", "").lower() in ("1", "true", "yes"):
        return
    phase = patch.get("phase")
    decisions = patch.get("decisions") or []
    bits = [f"node={node}"]
    if phase is not None:
        bits.append(f"phase={phase}")
    if decisions:
        last = decisions[-1]
        ev = last.get("event")
        by = last.get("by")
        if ev:
            bits.append(f"event={ev}")
        if by:
            bits.append(f"by={by}")
    idx = patch.get("current_unit_index")
    if idx is not None:
        bits.append(f"unit_idx={idx}")
    progress(" · ".join(bits))


__all__ = ["progress", "progress_node"]
