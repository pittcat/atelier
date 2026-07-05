"""Compound Builder 路由。

按 plan R16 / R17 / R18(模仿 code_writer 形态):
  POST /threads/{tid}/runs             → 同步 invoke
  POST /threads/{tid}/runs:stream      → SSE 流式
  GET  /threads/{tid}/state            → 当前快照
  GET  /threads/{tid}/history          → 全部历史

Compound Builder 与 code-writer 的差异:输入是 ``plan.md``,不是对话 prompt。
thread_id 由 Gateway 在外部创建(plan worktree 也由 gateway 持有,R18)。
"""
from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from auth import verify_token
from registry import get_agent


router = APIRouter(prefix="/agents/compound-builder", tags=["compound-builder"])


class PlanRunRequest(BaseModel):
    plan: dict                               # already-parsed PlanSchema dict
    workdir: str = "."
    thread_id: Optional[str] = None


class PlanRunResponse(BaseModel):
    thread_id: str
    output: dict


def _build_initial_state(req: PlanRunRequest) -> dict:
    return {
        "plan": req.plan,
        "units": [],
        "fix_units": [],
        "current_unit_index": 0,
        "phase": "init",
        "review_findings": [],
        "fix_plan_path": None,
        "review_round": 0,
        "repair_budget_used": 0,
        "decisions": [],
        "last_error": None,
        "messages": [],
        "results_log": [],
        "workdir": req.workdir,
    }


@router.post("/threads/{thread_id}/runs")
async def invoke_run(thread_id: str, req: PlanRunRequest, _: None = Depends(verify_token)):
    """同步调用 —— 灌入 plan,等整图跑完。"""
    agent = get_agent("compound-builder")
    cfg = {"configurable": {"thread_id": thread_id}}
    state_in = _build_initial_state(req)
    result = agent.invoke(state_in, config=cfg)
    return {"thread_id": thread_id, "output": result}


@router.post("/threads/{thread_id}/runs:stream")
async def stream_run(thread_id: str, req: PlanRunRequest, _: None = Depends(verify_token)):
    """SSE 流式 —— 边生成边推。"""
    agent = get_agent("compound-builder")
    cfg = {"configurable": {"thread_id": thread_id}}
    state_in = _build_initial_state(req)

    async def event_gen():
        for event in agent.stream(state_in, config=cfg):
            yield f"data: {event}\n\n"

    return StreamingResponse(event_gen(), media_type="text/event-stream")


@router.get("/threads/{thread_id}/state")
async def get_state(thread_id: str, _: None = Depends(verify_token)):
    agent = get_agent("compound-builder")
    cfg = {"configurable": {"thread_id": thread_id}}
    state = agent.get_state(cfg)
    return {"thread_id": thread_id, "state": state}


@router.get("/threads/{thread_id}/history")
async def get_history(thread_id: str, _: None = Depends(verify_token)):
    agent = get_agent("compound-builder")
    cfg = {"configurable": {"thread_id": thread_id}}
    history = []
    for s in agent.get_state_history(cfg):
        history.append({
            "created_at": str(s.created_at),
            "next": s.next,
            "values": s.values,
        })
    return {"thread_id": thread_id, "history": history}
