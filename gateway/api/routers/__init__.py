"""所有 Agent 路由的合集。

新 Agent 加 router 时,在这里 import + append 进 ALL_ROUTERS。
"""

from __future__ import annotations

from routers.code_writer import router as code_writer_router
from routers.compound_builder import router as compound_builder_router
from routers.modem_log_analyzer import router as modem_log_analyzer_router


ALL_ROUTERS = [
    code_writer_router,
    compound_builder_router,
    modem_log_analyzer_router,
]
