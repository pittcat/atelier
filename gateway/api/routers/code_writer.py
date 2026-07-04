"""Code Writer 路由。"""

from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from auth import verify_token
from registry import get_agent


router = APIRouter(prefix="/agents/code-writer", tags=["code-writer"])


class InvokeRequest(BaseModel):
    prompt: str
    thread_id: Optional[str] = None


class InvokeResponse(BaseModel):
    thread_id: str
    output: dict


@router.post("/threads/{thread_id}/runs")
async def invoke_run(thread_id: str, req: InvokeRequest, _: None = Depends(verify_token)):
    """同步调用：等到最终结果。"""
    agent = get_agent("code-writer")
    cfg = {"configurable": {"thread_id": thread_id}}
    result = agent.invoke({"messages": [("user", req.prompt)]}, config=cfg)
    return {"thread_id": thread_id, "output": result}


@router.post("/threads/{thread_id}/runs:stream")
async def stream_run(thread_id: str, req: InvokeRequest, _: None = Depends(verify_token)):
    """SSE 流式：边生成边推。"""
    agent = get_agent("code-writer")
    cfg = {"configurable": {"thread_id": thread_id}}

    async def event_gen():
        for event in agent.stream({"messages": [("user", req.prompt)]}, config=cfg):
            yield f"data: {event}\n\n"

    return StreamingResponse(event_gen(), media_type="text/event-stream")


@router.get("/threads/{thread_id}/state")
async def get_state(thread_id: str, _: None = Depends(verify_token)):
    """读 thread 当前状态。"""
    agent = get_agent("code-writer")
    cfg = {"configurable": {"thread_id": thread_id}}
    state = agent.get_state(cfg)
    return {"thread_id": thread_id, "state": state}


@router.get("/threads/{thread_id}/history")
async def get_history(thread_id: str, _: None = Depends(verify_token)):
    """读 thread 完整历史（用于回放）。"""
    agent = get_agent("code-writer")
    cfg = {"configurable": {"thread_id": thread_id}}
    history = []
    for state in agent.get_state_history(cfg):
        history.append({
            "created_at": str(state.created_at),
            "next": state.next,
            "values": state.values,
        })
    return {"thread_id": thread_id, "history": history}
