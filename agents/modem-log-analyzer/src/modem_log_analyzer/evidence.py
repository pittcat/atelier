"""ModemLogAnalyzer —— Evidence Index (Unit 3)。

按 Plan §1 R9 + §5:
  - 每个解析事件都有稳定的 ``ref_id``, 形如 ``EV-NNNN``。
  - ref_id 与 ``source`` (文件展示名) + ``line_no`` (1-based) + ``raw_text`` 共同构成
    "可复核证据"。
  - 同一文件两次解析 → 同一 ref_id 列表 (S13)。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class EvidenceRef:
    """正式证据索引中的一项。

    字段映射到 contracts.EvidenceRef, 但本文件内是纯 dataclass(便于测试)。
    """

    ref_id: str
    source: str
    line_no: int
    raw_text: str
    module: str | None = None
    timestamp: str | None = None


def build_evidence_index(
    events: list[dict[str, Any]], source: str = "evb.log"
) -> list[EvidenceRef]:
    """从事件列表构造稳定的证据索引。

    规则:
      - 每个事件分配一个 EV-NNNN 序号 (按 line_no 升序)。
      - timestamp 取 ``device_ts or capture_ts``(设备时间优先)。
      - 同 line_no 多个事件 → 全部保留, ref_id 仍然稳定(按 events 顺序)。
    """
    refs: list[EvidenceRef] = []
    for idx, ev in enumerate(events, start=1):
        ref_id = f"EV-{idx:04d}"
        line_no = int(ev.get("line_no") or 0)
        ts = ev.get("device_ts") or ev.get("capture_ts")
        refs.append(
            EvidenceRef(
                ref_id=ref_id,
                source=source,
                line_no=line_no,
                raw_text=str(ev.get("raw_text") or ""),
                module=ev.get("module"),
                timestamp=ts,
            )
        )
    return refs


def attach_evidence_refs(
    events: list[dict[str, Any]],
    refs: list[EvidenceRef],
) -> list[dict[str, Any]]:
    """把 ref_id 写回到 events 副本里(供下游 schema 直接读)。

    不修改原始 events;返回新列表。
    """
    out: list[dict[str, Any]] = []
    by_line: dict[int, list[EvidenceRef]] = {}
    for r in refs:
        by_line.setdefault(r.line_no, []).append(r)

    cursor: dict[int, int] = {}
    for ev in events:
        new_ev = dict(ev)
        line_no = int(ev.get("line_no") or 0)
        bucket = by_line.get(line_no, [])
        if bucket:
            i = cursor.get(line_no, 0)
            if i < len(bucket):
                new_ev["ref_id"] = bucket[i].ref_id
                cursor[line_no] = i + 1
        out.append(new_ev)
    return out


__all__ = ["EvidenceRef", "build_evidence_index", "attach_evidence_refs"]
