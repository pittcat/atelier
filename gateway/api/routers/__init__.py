"""所有 Agent 路由的合集。

新 Agent 加 router 时，在这里 import + append 进 ALL_ROUTERS。
"""

from __future__ import annotations

from fastapi import APIRouter

from routers.code_writer import router as code_writer_router


ALL_ROUTERS = [
    code_writer_router,
]
