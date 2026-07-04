"""Atelier Gateway —— FastAPI 主入口。

启动：
    cd gateway/api
    uvicorn main:app --reload --port 8080

功能：
  - /agents                          列出所有可用 Agent
  - /agents/{slug}/threads          新建 thread
  - /agents/{slug}/threads/{tid}/runs  同步 invoke（非流）
  - /agents/{slug}/threads/{tid}/runs:stream  SSE 流式
  - /agents/{slug}/threads/{tid}/runs/{run_id}/resume  中断恢复
"""

from __future__ import annotations

import os
import uuid
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import Depends, FastAPI, Header, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse

from routers import ALL_ROUTERS
from auth import verify_token
from registry import AGENT_REGISTRY


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # startup：可注入 LangSmith tracing 等
    yield
    # shutdown


app = FastAPI(
    title="Atelier Gateway",
    version="0.1.0",
    description="Atelier 多 Agent 工作流统一网关",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("GATEWAY_ALLOWED_ORIGINS", "*").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---- 注册子路由 ----
for router in ALL_ROUTERS:
    app.include_router(router)


# ---- 顶层：Agent 注册表 ----
@app.get("/agents")
async def list_agents(_: None = Depends(verify_token)) -> dict:
    return {
        "agents": [
            {"slug": slug, "display": meta["display"], "description": meta["description"]}
            for slug, meta in AGENT_REGISTRY.items()
        ]
    }


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "agents_loaded": list(AGENT_REGISTRY.keys())}


# ---- 顶层鉴权错误处理 ----
@app.exception_handler(HTTPException)
async def _http_exc(_, exc: HTTPException) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


__all__ = ["app"]
