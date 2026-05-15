"""Plan Controller — 规划任务相关的 HTTP 路由。

对应 Spring Boot @RestController。
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from backend.models.request.agent_requests import SavePlanArtifactRequest
from backend.services import plan as plan_service

router = APIRouter(prefix="/chat", tags=["plans"])
_log = logging.getLogger(__name__)


class UpdatePlanStepRequest(BaseModel):
    artifactId: int
    stepIndex: int
    status: str | None = None
    error: str | None = None


class UpdatePlanArtifactStatusRequest(BaseModel):
    artifactId: int
    status: str | None = None
    currentStep: int | None = None


@router.delete("/plans")
async def delete_all_plans() -> dict:
    """删除全部任务规划记录（主表 ``plan_artifacts`` + 子表 ``plan_artifact_steps``）。

    Runs in a thread pool so it never blocks the async event loop.
    """
    import asyncio
    import concurrent.futures

    _log.info("DELETE /api/chat/plans called — beginning plan purge")
    loop = asyncio.get_running_loop()
    counts = await loop.run_in_executor(
        concurrent.futures.ThreadPoolExecutor(max_workers=1),
        plan_service.delete_all_plans,
    )
    _log.info("DELETE /api/chat/plans result: %s", counts)
    return {"ok": True, "deletedArtifacts": counts.get("artifacts", 0), "deletedSteps": counts.get("steps", 0)}


@router.post("/plans")
async def save_plan(body: SavePlanArtifactRequest) -> dict:
    """将模型推理结果中解析出的 PlanArtifact JSON 写入数据库。"""
    resolved_agent_id = plan_service.resolve_agent_id_for_session(body.sessionId)
    steps = [s.model_dump() for s in body.steps]
    pk = plan_service.save_plan_artifact(
        session_id=body.sessionId,
        agent_id=resolved_agent_id,
        name=body.name,
        plan_summary=body.planSummary,
        steps=steps,
        raw_text=body.rawText,
    )
    if pk is None:
        raise HTTPException(status_code=500, detail="保存失败")
    return {"ok": True, "id": pk}


@router.post("/plans/step")
async def update_plan_step(body: UpdatePlanStepRequest) -> dict:
    """更新规划链中某一步的执行状态。"""
    import time as _time

    ok = plan_service.update_plan_chain_step(
        body.artifactId,
        body.stepIndex,
        status=body.status,
        error=body.error,
        completed_at=_time.time() if body.status == "done" else None,
    )
    return {"ok": ok}


@router.post("/plans/status")
async def update_plan_artifact_status(body: UpdatePlanArtifactStatusRequest) -> dict:
    """更新规划主表的执行状态。"""
    ok = plan_service.update_plan_artifact_status(
        body.artifactId,
        status=body.status,
        current_step=body.currentStep,
    )
    return {"ok": ok}


@router.delete("/plans/artifact/{artifact_id}")
async def delete_plan_artifact_route(artifact_id: int) -> dict:
    """删除指定主键的规划及其所有步骤（子表先删）。无此 id 时返回 404。"""
    ok = plan_service.delete_plan_artifact(artifact_id)
    if not ok:
        raise HTTPException(status_code=404, detail="规划不存在或已删除")
    return {"ok": True, "artifactId": artifact_id}


@router.get("/plans/{session_id}")
async def list_plans(session_id: str) -> dict:
    """读取指定会话的规划历史。"""
    plans = plan_service.get_plan_artifacts(session_id)
    return {"ok": True, "plans": plans}


@router.get("/plans/detail/{artifact_id}")
async def get_plan_detail(artifact_id: int) -> dict:
    """读取某条规划及其全部步骤子表记录。"""
    plan = plan_service.get_plan_artifact_with_steps(artifact_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="规划不存在")
    return {"ok": True, "plan": plan}


@router.get("/plans/agent/{agent_id}")
async def list_plans_for_agent(
    agent_id: str,
    limit: int = Query(500, ge=1, le=5000, description="最多返回多少条规划（按创建时间降序）"),
) -> dict:
    """读取某 Agent 主导或参与的所有规划。"""
    plans = plan_service.get_plan_artifacts_for_agent(agent_id, limit=limit)
    return {"ok": True, "plans": plans}


@router.get("/plans/step-result")
async def get_step_result(session_id: str, completed_at: float) -> dict:
    """根据 session_id 和 completed_at（秒）查找该时间点最近的一条助手推理结果。"""
    return plan_service.get_step_result(session_id, completed_at)
