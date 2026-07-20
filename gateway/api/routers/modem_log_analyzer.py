"""ModemLogAnalyzer —— Gateway 路由。

按 Plan §5 Unit 8 + U4:
  - 模仿 code-writer / compound-builder router 模式。
  - 客户端禁止提交任意服务器绝对路径: 通过 multipart 上传或 thread-scoped
    artifact-id, 文件限定在服务端为该 thread 创建的隔离暂存区。
  - 响应遵守 AnalysisResult schema; 不返回原始日志全文。
  - Plan U4 主路径: 与 CLI 共用同一个 Agent runner (``agent_runner.run_agent_analyze``)。
    ``MODEM_LOG_ANALYZER_CLI_FORCE_RULES=1`` 时退回 ``AnalysisService._run_rules_pipeline``
    (供离线 / 合成 e2e 使用, **不**用于生产 Agent 诊断)。
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import uuid
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, Field

from auth import verify_token

from modem_log_analyzer.report import atomic_write_artifacts


router = APIRouter(prefix="/agents/modem-log-analyzer", tags=["modem-log-analyzer"])


def _dispatch_runner(**kwargs):
    """Plan U4: 选 runner。

    - ``MODEM_LOG_ANALYZER_CLI_FORCE_RULES=1`` 且
      ``ATELIER_ENV in {"dev","test"}`` 或 ``MODEM_LOG_ANALYZER_ALLOW_RULES=1``
      → 确定性规则管线 (合成 e2e / 离线)
    - 默认: ``agent_runner.run_agent_analyze`` (AI Agent 诊断)
    - 生产环境无 ATELIER_ENV=dev/test 时, 即便误设 CLI_FORCE_RULES 也**拒绝**
      而非静默降级 (与 CLI guard 一致)。
    """
    import logging

    from fastapi import HTTPException

    log = logging.getLogger("gateway.modem_log_analyzer")
    force = os.getenv("MODEM_LOG_ANALYZER_CLI_FORCE_RULES") == "1"
    atelier_env = os.getenv("ATELIER_ENV", "production").lower()
    allow = os.getenv("MODEM_LOG_ANALYZER_ALLOW_RULES") == "1"
    if force and not (atelier_env in {"dev", "test"} or allow):
        log.error(
            "FORCE_RULES_GUARD: refusing to downgrade to rules pipeline in non-dev env"
        )
        raise HTTPException(
            status_code=500,
            detail=(
                "MODEM_LOG_ANALYZER_CLI_FORCE_RULES=1 is set but ATELIER_ENV is not "
                "dev/test and MODEM_LOG_ANALYZER_ALLOW_RULES is unset. Refusing to "
                "silently downgrade AI Agent diagnosis to deterministic rules."
            ),
        )
    if force:
        log.warning("FORCE_RULES=1 active — using legacy rules pipeline (not AI)")
        from modem_log_analyzer.analysis_service import AnalysisService

        return AnalysisService()._run_rules_pipeline(**kwargs)
    from modem_log_analyzer.agent_runner import run_agent_analyze

    return run_agent_analyze(**kwargs)


# ============================================================
# 内存暂存: thread_id -> 目录
# 注意: 进程重启即丢; 生产应当用 Redis / S3 替代。
# ============================================================
_THREAD_STAGING: dict[str, Path] = {}


def _staging_root() -> Path:
    """返回服务端暂存根目录。

    默认 ``/tmp/atelier-modem-log-analyzer-staging``。
    可通过环境变量 ``MODEM_LOG_ANALYZER_STAGING_DIR`` 覆盖。
    """
    raw = os.getenv("MODEM_LOG_ANALYZER_STAGING_DIR")
    if raw:
        p = Path(raw).expanduser().resolve()
    else:
        p = Path(tempfile.gettempdir()) / "atelier-modem-log-analyzer-staging"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _thread_dir(thread_id: str) -> Path:
    """返回 thread 的隔离暂存目录。"""
    if thread_id not in _THREAD_STAGING:
        # thread id 必须仅含 ASCII / 数字 / dash, 防止路径穿越
        safe = "".join(c for c in thread_id if c.isalnum() or c in "-_")
        if not safe or len(safe) > 64:
            raise HTTPException(400, "invalid thread_id")
        p = _staging_root() / safe
        p.mkdir(parents=True, exist_ok=True)
        _THREAD_STAGING[thread_id] = p
    return _THREAD_STAGING[thread_id]


def _cleanup_thread(thread_id: str) -> None:
    """到达终态后清理 thread 的暂存目录。

    失败也允许 (容错)。
    """
    p = _THREAD_STAGING.pop(thread_id, None)
    if p is not None and p.exists():
        try:
            shutil.rmtree(p)
        except Exception:
            pass


def _resolve_artifact(td: Path, artifact_id: str | None, default_name: str) -> Path | None:
    """在 thread dir 下解析一个 artifact 文件。

    - artifact_id 为 None → 找 thread dir 下名为 ``default_name`` 的文件。
    - artifact_id 给出 → 找 ``{artifact_id}_{default_name}``(约定格式)。

    强制约束: 解析后的路径必须仍在 thread dir 内 (防穿越)。
    返回 None 表示找不到。
    """
    td_resolved = td.resolve()
    if artifact_id is None:
        # 默认: thread 根下直接命名的文件
        target = (td / default_name).resolve()
    else:
        # 仅允许 [a-zA-Z0-9_-] 字符, 防路径注入
        if not all(c.isalnum() or c in "-_" for c in artifact_id) or not artifact_id:
            return None
        target = (td / f"{artifact_id}_{default_name}").resolve()
    try:
        target.relative_to(td_resolved)
    except ValueError:
        return None
    return target if target.exists() else None


# ============================================================
# 请求 / 响应模型
# ============================================================
class RunRequest(BaseModel):
    """Gateway 调用 AnalysisService 的请求。"""

    label: Optional[str] = Field(default=None, description="可选: 自定义标识")
    overwrite: bool = Field(default=False)
    evb_artifact_id: Optional[str] = Field(
        default=None,
        description="EVB 日志 artifact id; 不提供时使用 thread 默认的 evb.log",
    )
    control_artifact_id: Optional[str] = Field(
        default=None,
        description="可选: 已上传的控制脚本日志 artifact id",
    )


class ResumeRequest(BaseModel):
    """interrupt 后用户回应 (提供 control log 或拒绝)。"""

    control_artifact_id: Optional[str] = Field(
        default=None,
        description="已上传的控制脚本日志 artifact id; None = 拒绝",
    )
    evb_artifact_id: Optional[str] = Field(
        default=None,
        description="EVB 日志 artifact id; 不提供时使用 thread 默认的 evb.log",
    )


class ArtifactResponse(BaseModel):
    artifact_id: str
    size: int
    filename: str


class AnalysisSummary(BaseModel):
    """对外暴露的 analysis 摘要。

    注意: 不返回 evidence raw_text (可能含敏感值)。
    """

    schema_version: str
    classification: str
    root_cause_confidence: str
    scenario: Optional[str] = None
    classification_reasoning: Optional[str] = None
    evidence_ref_count: int = 0
    interrupt_request: Optional[dict] = None


# ============================================================
# 上传 artifact
# ============================================================
@router.post("/threads/{thread_id}/artifacts", response_model=ArtifactResponse)
async def upload_artifact(
    thread_id: str,
    artifact: UploadFile = File(...),
    _: None = Depends(verify_token),
) -> ArtifactResponse:
    """上传一份日志 (EVB 或 control log) 到该 thread 的隔离暂存。

    拒绝绝对路径或跨 thread 引用: 服务端固定保存到 ``_thread_dir(thread_id)``。
    """
    td = _thread_dir(thread_id)
    artifact_id = uuid.uuid4().hex
    filename = artifact.filename or f"{artifact_id}.log"
    # 拒绝 ../ 或 / 开头的文件名
    if "/" in filename or "\\" in filename or filename.startswith("."):
        raise HTTPException(400, f"invalid filename: {filename!r}")
    safe_name = "".join(c for c in filename if c.isalnum() or c in "._-") or "artifact.log"

    target = td / f"{artifact_id}_{safe_name}"
    content = await artifact.read()
    if not content:
        raise HTTPException(400, "empty upload")
    if len(content) > 100 * 1024 * 1024:  # 100MB 上限
        raise HTTPException(413, "artifact too large")
    target.write_bytes(content)

    return ArtifactResponse(
        artifact_id=artifact_id,
        size=len(content),
        filename=safe_name,
    )


@router.post("/threads/{thread_id}/runs", response_model=AnalysisSummary)
def invoke_run(
    thread_id: str,
    req: RunRequest,
    _: None = Depends(verify_token),
) -> AnalysisSummary:
    """同步 invoke: 跑一次分析, 返回摘要。

    内部使用 AnalysisService.run_analyze; 输入文件来自 thread 暂存。
    """
    td = _thread_dir(thread_id)
    evb_artifact = _resolve_artifact(td, req.evb_artifact_id, default_name="evb.log")
    if evb_artifact is None or not evb_artifact.exists():
        raise HTTPException(400, f"no evb.log uploaded for thread {thread_id}")
    output_dir = td / "out"
    output_dir.mkdir(parents=True, exist_ok=True)

    # 控制日志路径 (若有)
    control_path: str | None = None
    if req.control_artifact_id:
        cp = _resolve_artifact(td, req.control_artifact_id, default_name="control.log")
        if cp is None:
            raise HTTPException(404, "control artifact not found")
        control_path = str(cp)

    # Plan U4: 共用 CLI 的 runner
    result = _dispatch_runner(
        evb_log_path=str(evb_artifact),
        output_dir=str(output_dir),
        control_log_path=control_path,
        label=req.label,
        thread_id=thread_id,
        overwrite=req.overwrite,
        dry_run=False,
    )

    # 写产物 (原子提交)
    try:
        atomic_write_artifacts(
            result=result,
            output_dir=str(output_dir),
            overwrite=req.overwrite,
        )
    except FileExistsError as e:
        raise HTTPException(409, str(e))
    except ValueError as e:
        raise HTTPException(500, f"INVALID_RESULT: {e}")

    # 摘要 (不返回 raw_text)
    return AnalysisSummary(
        schema_version=result.get("schema_version", ""),
        classification=result.get("classification", "UNKNOWN"),
        root_cause_confidence=result.get("root_cause_confidence", "low"),
        scenario=result.get("scenario"),
        classification_reasoning=result.get("notes", [None])[0] if result.get("notes") else None,
        evidence_ref_count=len(result.get("evidence_refs") or []),
        interrupt_request=(result.get("_meta") or {}).get("interrupt_request"),
    )


@router.post("/threads/{thread_id}/runs:resume", response_model=AnalysisSummary)
def resume_run(
    thread_id: str,
    req: ResumeRequest,
    _: None = Depends(verify_token),
) -> AnalysisSummary:
    """interrupt 后用户回应: 提供 control log 或拒绝。

    提供控制脚本日志后, AnalysisService 会基于 has_direct_evidence 重新评估。
    """
    td = _thread_dir(thread_id)
    evb_artifact = _resolve_artifact(td, req.evb_artifact_id, default_name="evb.log")
    if evb_artifact is None or not evb_artifact.exists():
        raise HTTPException(400, f"no evb.log uploaded for thread {thread_id}")
    output_dir = td / "out"
    if not output_dir.exists():
        output_dir.mkdir(parents=True, exist_ok=True)

    control_path: str | None = None
    if req.control_artifact_id:
        cp = _resolve_artifact(td, req.control_artifact_id, default_name="control.log")
        if cp is None:
            raise HTTPException(404, "control artifact not found")
        control_path = str(cp)

    # Plan U4: 共用 CLI 的 runner
    result = _dispatch_runner(
        evb_log_path=str(evb_artifact),
        output_dir=str(output_dir),
        control_log_path=control_path,
        label=None,
        thread_id=thread_id,
        overwrite=True,
        dry_run=False,
    )
    atomic_write_artifacts(
        result=result,
        output_dir=str(output_dir),
        overwrite=True,
    )

    # 不在 resume_run 立即清理 thread 暂存 (客户端可能还要 GET /report)。
    # 由客户端在完成读取后调用 DELETE /threads/{tid} 或由 TTL 后台清理。

    return AnalysisSummary(
        schema_version=result.get("schema_version", ""),
        classification=result.get("classification", "UNKNOWN"),
        root_cause_confidence=result.get("root_cause_confidence", "low"),
        scenario=result.get("scenario"),
        classification_reasoning=result.get("notes", [None])[0] if result.get("notes") else None,
        evidence_ref_count=len(result.get("evidence_refs") or []),
        interrupt_request=None,  # 已处理
    )


@router.get("/threads/{thread_id}/state")
def get_state(
    thread_id: str,
    _: None = Depends(verify_token),
) -> dict:
    """读取 thread 当前状态 (最近一次分析摘要)。"""
    td = _thread_dir(thread_id)
    analysis_json = td / "out" / "analysis.json"
    if not analysis_json.exists():
        raise HTTPException(404, f"no analysis for thread {thread_id}")
    payload = json.loads(analysis_json.read_text(encoding="utf-8"))
    return {
        "thread_id": thread_id,
        "state": {
            "classification": payload.get("classification"),
            "root_cause_confidence": payload.get("root_cause_confidence"),
            "scenario": payload.get("scenario"),
            "control_log_used": payload.get("control_log_used"),
            "external_result": payload.get("external_result"),
        },
    }


@router.get("/threads/{thread_id}/artifacts/{artifact_id}")
def get_artifact_report(
    thread_id: str,
    artifact_id: str,
    _: None = Depends(verify_token),
) -> dict:
    """返回 report.md 路径 (供客户端拉取)。

    不直接返回 report 全文, 避免泄露; 客户端按需 GET /report。
    """
    # 校验 artifact_id 不越界
    safe_id = "".join(c for c in artifact_id if c.isalnum() or c in "-_")
    if not safe_id or safe_id != artifact_id:
        raise HTTPException(400, "invalid artifact_id")
    td = _thread_dir(thread_id)
    target = (td / f"{artifact_id}.log").resolve()
    if not str(target).startswith(str(td.resolve())):
        raise HTTPException(400, "artifact_id escapes thread dir")
    return {"thread_id": thread_id, "artifact_id": artifact_id, "exists": target.exists()}


@router.get("/threads/{thread_id}/report")
def get_report(
    thread_id: str,
    _: None = Depends(verify_token),
) -> dict:
    """返回 report.md 全文 (由调用方自决是否展示)。"""
    td = _thread_dir(thread_id)
    report = td / "out" / "report.md"
    if not report.exists():
        raise HTTPException(404, f"no report for thread {thread_id}")
    return {"thread_id": thread_id, "report_md": report.read_text(encoding="utf-8")}


@router.delete("/threads/{thread_id}")
def delete_thread(
    thread_id: str,
    _: None = Depends(verify_token),
) -> dict:
    """客户端显式清理 thread 的服务端暂存 (读取报告后调用)。

    终态清理策略: 客户端负责; 服务端在 TTL 后兜底清理。
    """
    _cleanup_thread(thread_id)
    return {"thread_id": thread_id, "status": "cleaned"}


# ============================================================
# 健康检查 (供 gateway 聚合)
# ============================================================
@router.get("/health")
def health(_: None = Depends(verify_token)) -> dict:
    return {"status": "ok", "agent": "modem-log-analyzer"}
