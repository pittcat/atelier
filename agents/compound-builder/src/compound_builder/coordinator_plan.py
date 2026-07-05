"""Coordinator —— 用 LLM 读 plan.md 并拆 unit。

``init`` 阶段由 ``coordinator`` 调用;``ATELIER_DRY_RUN=true`` 时退回
确定性 ``parse_plan``(测试 / 拓扑自检)。
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from compound_builder.llm import get_llm
from compound_builder.progress import progress
from compound_builder.prompts import SYSTEM_PROMPT_COORDINATOR_PARSE
from compound_builder.state import CompoundBuilderState
from compound_builder.tools import PlanSchema, PlanValidationError, _parse_plan
from compound_builder.worker import is_dry_run


def _coordinator_shape(schema: PlanSchema) -> dict[str, Any]:
    dumped = schema.model_dump()
    units = dumped["units"]
    plan = {
        "title": dumped["title"],
        "acceptance": dumped.get("acceptance") or [],
        "scope_boundaries": dumped.get("scope_boundaries") or [],
        "units": units,
    }
    return {"plan": plan, "units": units}


def _parse_from_state_plan(state: CompoundBuilderState) -> dict[str, Any]:
    """测试 / 已注入 state.plan 时直接规范化。"""
    raw = state.get("plan") or {}
    if not raw.get("units"):
        raise PlanValidationError("state.plan.units missing")
    schema = PlanSchema(
        title=raw.get("title") or "(untitled)",
        acceptance=list(raw.get("acceptance") or []),
        scope_boundaries=list(raw.get("scope_boundaries") or []),
        units=raw["units"],
    )
    return _coordinator_shape(schema)


def _parse_regex(plan_path: Path) -> dict[str, Any]:
    flat = _parse_plan(plan_path)
    schema = PlanSchema(**flat)
    return _coordinator_shape(schema)


def _parse_llm(plan_text: str, plan_path: str) -> dict[str, Any]:
    progress(f"coordinator: LLM parsing plan ({len(plan_text)} chars) …")
    model = get_llm()
    structured = model.with_structured_output(PlanSchema)
    schema: PlanSchema = structured.invoke(
        [
            SystemMessage(content=SYSTEM_PROMPT_COORDINATOR_PARSE),
            HumanMessage(
                content=(
                    f"plan_path: {plan_path}\n\n"
                    "Parse the following plan.md into PlanSchema "
                    "(title, acceptance, scope_boundaries, units).\n\n"
                    f"---\n{plan_text}\n---"
                )
            ),
        ]
    )
    if not schema.units:
        raise PlanValidationError("LLM returned zero units")
    progress(f"coordinator: LLM parsed {len(schema.units)} unit(s)")
    return _coordinator_shape(schema)


def parse_plan_for_coordinator(state: CompoundBuilderState) -> tuple[dict[str, Any], str]:
    """解析 plan,返回 (coordinator_payload, source)。

    source 为 ``state`` | ``regex`` | ``llm`` | ``llm+regex_fallback``。
    """
    if is_dry_run():
        plan = state.get("plan") or {}
        if plan.get("units"):
            return _parse_from_state_plan(state), "state"
        plan_path = state.get("plan_path")
        if plan_path and Path(plan_path).is_file():
            return _parse_regex(Path(plan_path)), "regex"
        raise PlanValidationError("dry-run: need state.plan.units or plan_path")

    plan_path = state.get("plan_path")
    if not plan_path or not Path(plan_path).is_file():
        if state.get("plan", {}).get("units"):
            return _parse_from_state_plan(state), "state"
        raise PlanValidationError(f"plan_path not found: {plan_path!r}")

    path = Path(plan_path)
    text = path.read_text(encoding="utf-8")

    try:
        return _parse_llm(text, str(path.resolve())), "llm"
    except Exception as exc:
        progress(f"coordinator: LLM parse failed ({exc!s}), falling back to regex …")
        return _parse_regex(path), "llm+regex_fallback"


__all__ = ["parse_plan_for_coordinator"]
