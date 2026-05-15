"""Chat Controller — 对应 Spring Boot @RestController.

仅处理 HTTP 请求/响应、参数校验，调用 service/chat.py 完成业务逻辑。
"""

from __future__ import annotations

import logging
import time
from pathlib import Path

import asyncio
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request, UploadFile, File, Form
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from backend.core.config import get_config
from backend.core.exceptions import SessionNotFoundError, ValidationError
from backend.models.request.chat_requests import (
    CreateSessionRequest,
    SubmitPromptRequest,
    OrchestratedChatRequest,
    DelegationReadyRequest,
    ApprovalRequest,
    ClarifyRequest,
    PlanChainStartRequest,
)
from backend.services import chat as chat_service
from backend.services import feishu_transcript as feishu_transcript_service
from backend.services import gateway_studio_bridge as gateway_studio_bridge_service
from backend.services import agent_db as _agent_db
from backend.services.agent import _get_manager
from backend.services.orchestrate import (
    orchestrated_chat_sync,
    orchestrated_control_stream,
    orchestrated_pending,
    notify_delegation_ready,
    start_orchestrated_background_run,
)

router = APIRouter(prefix="/chat", tags=["chat"])
_log = logging.getLogger(__name__)

ALLOWED_IMAGE_TYPES = {"image/png", "image/jpeg", "image/gif", "image/webp", "image/bmp"}
ALLOWED_FILE_TYPES = {"application/pdf", "text/plain", "text/markdown",
                      "application/json", "text/html", "text/csv"}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB

_IMAGE_EXT_BY_CT: dict[str, str] = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/gif": ".gif",
    "image/webp": ".webp",
    "image/bmp": ".bmp",
}
_KNOWN_IMAGE_SUFFIXES = frozenset(
    {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tiff", ".tif", ".svg", ".ico"}
)


def _sanitize_upload_basename(filename: str | None) -> str:
    raw = (filename or "upload").strip() or "upload"
    base = Path(raw).name
    if not base or base in (".", ".."):
        return "upload"
    return base


def _finalize_image_basename(basename: str, content_type: str) -> str:
    p = Path(basename)
    if p.suffix.lower() in _KNOWN_IMAGE_SUFFIXES:
        return basename
    ct = (content_type or "").split(";")[0].strip().lower()
    ext = _IMAGE_EXT_BY_CT.get(ct) or ".png"
    stem = p.stem if p.stem else "image"
    return f"{stem}{ext}"


@router.post("/upload")
async def upload_file(
    file: UploadFile = File(...),
    agent_id: str = Form(...),
) -> dict:
    """上传图片或文件到指定 Agent 的 workspace 目录。"""
    from backend.services.agent import _get_manager

    mgr = _get_manager()
    info = mgr.get_agent(agent_id)
    if info is None:
        raise HTTPException(status_code=404, detail="Agent 不存在")

    gw = info.gateway
    hermes_home = getattr(gw, "hermes_home", None)
    if hermes_home:
        profile_home = Path(hermes_home).expanduser()
    else:
        profile_home = get_config().hermes_home
    upload_dir = profile_home / "images" / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)

    content_type = file.content_type or "application/octet-stream"
    if content_type not in ALLOWED_IMAGE_TYPES and content_type not in ALLOWED_FILE_TYPES:
        raise HTTPException(status_code=415, detail=f"不支持的文件类型: {content_type}")

    contents = await file.read()
    if len(contents) > MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail="文件超过 10MB 限制")

    timestamp = int(time.time() * 1000)
    basename = _sanitize_upload_basename(file.filename)
    if content_type in ALLOWED_IMAGE_TYPES:
        basename = _finalize_image_basename(basename, content_type)
    safe_filename = f"{timestamp}_{basename}"
    file_path = upload_dir / safe_filename

    with open(file_path, "wb") as f:
        f.write(contents)

    _log.info("上传文件: %s -> %s", file.filename, file_path)
    return {"url": str(file_path), "filename": file.filename, "contentType": content_type, "size": len(contents)}


@router.post("/sessions")
async def create_session(body: CreateSessionRequest) -> dict:
    """创建一个新的会话，返回 sessionId。

    若指定 parentSessionId，则表示该 session 是从另一个 session 压缩/续接而来的。
    """
    try:
        return chat_service.create_session(body.agentId, body.cols, body.parentSessionId)
    except ValueError as e:
        raise ValidationError(str(e)) from e
    except RuntimeError as e:
        raise SessionNotFoundError(body.agentId) from e


@router.get("/sessions")
async def list_sessions() -> dict:
    """列出所有 session（按最后活跃时间倒序），用于前端启动时恢复会话状态。"""
    sessions = _agent_db.list_all_sessions()
    return {"sessions": sessions}


@router.delete("/sessions/{session_id}")
async def close_session(session_id: str) -> dict:
    """关闭指定会话。"""
    if not chat_service.close_session(session_id):
        raise HTTPException(status_code=404, detail="会话不存在")
    return {"ok": True}


@router.post("/sessions/{session_id}/resume")
async def resume_session(session_id: str) -> dict:
    """恢复一个旧会话，复用 state.db 历史消息。
    
    使用旧会话的 session_key 创建新会话，保留所有历史对话。
    返回 {"sessionId": newId, "agentId": agentId}。
    """
    try:
        return chat_service.resume_session(session_id)
    except ValueError as e:
        raise SessionNotFoundError(session_id) from e
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/sessions/{session_id}/delete")
async def perm_delete_session(session_id: str) -> dict:
    """彻底删除会话：state.db 记录 + sessions/ 文件 + agent_sessions 表。"""
    return chat_service.delete_session(session_id)


@router.get("/sse/{session_id}")
async def sse_stream(session_id: str) -> StreamingResponse:
    """SSE 端点 — 将 Agent 子进程的 JSON-RPC 事件实时推送至前端。"""
    return StreamingResponse(
        chat_service.sse_generate(session_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/gateway-bridge/sse")
async def gateway_bridge_sse(token: str = Query(..., min_length=8)) -> StreamingResponse:
    """SSE：Hermes 消息网关（Feishu）推理流，事件形状同 ``/sse/{session}`` 解包后的对象。"""
    return gateway_studio_bridge_service.sse_gateway_bridge(token)


@router.get("/gateway-bridge/token")
async def gateway_bridge_token() -> dict[str, str]:
    """返回与 ``ingest`` 校验、``gateway-bridge/sse`` 订阅共用的密钥（同源开发用）。"""
    return {"token": gateway_studio_bridge_service.get_bridge_secret()}


@router.post("/internal/gateway-studio-event")
async def gateway_studio_event_ingest(request: Request) -> dict[str, Any]:
    """仅供本机网关子进程调用：投递一条扁平 Hermes 事件至所有 bridge SSE 客户端。"""
    return await gateway_studio_bridge_service.ingest_gateway_studio_event(request)


@router.get("/heartbeat/sse")
async def heartbeat_sse() -> StreamingResponse:
    """SSE：心跳推理结果实时推送，事件格式为 ``{type: "heartbeat.reasoning", ...}``。"""
    return gateway_studio_bridge_service.sse_heartbeat()


@router.post("/orchestrated")
async def orchestrated_chat(body: OrchestratedChatRequest) -> dict:
    """Bungalow 风格编排：用户 handoff 时行为同 ``/prompt``；否则主轮结束后解析 assistant ``@`` 并投递同伴。"""
    try:
        atts = body.attachments if body.attachments else None
        result = await asyncio.to_thread(
            orchestrated_chat_sync,
            body.sessionId,
            body.text,
            attachments=atts,
            cols=body.cols,
            auto_peer=body.autoPeer,
            complete_timeout=body.completeTimeout,
        )
        if not result.get("ok"):
            prim = result.get("primary")
            detail = (
                str(prim.get("error"))
                if isinstance(prim, dict) and prim.get("error")
                else str(result.get("error") or "orchestrated_failed")
            )
            raise HTTPException(status_code=500, detail=detail)
        return result
    except ValueError as e:
        detail = str(e)
        if "会话不存在" in detail:
            raise SessionNotFoundError(body.sessionId) from e
        raise ValidationError(detail) from e
    except RuntimeError as e:
        raise SessionNotFoundError(body.sessionId) from e


@router.post("/orchestrated/run")
async def orchestrated_run(body: OrchestratedChatRequest) -> dict:
    """立即返回 ``run_id``；编排进度与最终结果经 ``GET /orchestrated/stream`` SSE 推送（缩短首包阻塞）。"""
    if not body.sessionId:
        raise HTTPException(status_code=400, detail="sessionId 必填")
    mgr = _get_manager()
    if mgr.find_agent_by_session(body.sessionId) is None:
        raise HTTPException(status_code=404, detail="会话不存在")
    atts = body.attachments if body.attachments else None
    run_id = start_orchestrated_background_run(
        body.sessionId,
        body.text,
        attachments=atts,
        cols=body.cols,
        auto_peer=body.autoPeer,
        complete_timeout=body.completeTimeout,
    )
    return {"ok": True, "run_id": run_id}


@router.get("/orchestrated/stream")
async def orchestrated_stream(run_id: str = Query(..., min_length=1)) -> StreamingResponse:
    """SSE：编排阶段事件（``orch_phase``、``orch_delegation_*`` 等）与最终 ``orch_done``。"""
    return StreamingResponse(
        orchestrated_control_stream(run_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/orchestrated/delegation_ready")
async def orchestrated_delegation_ready(body: DelegationReadyRequest) -> dict:
    """Studio：主 Agent 已走到目标 Agent 旁并朝向后，解锁后端 ``@`` 同伴 relay。"""
    tok = (body.delegationToken or "").strip()
    if not tok:
        raise HTTPException(status_code=400, detail="delegationToken 必填")
    return {"ok": notify_delegation_ready(tok)}


@router.get("/orchestrated/pending")
async def orchestrated_pending_route(run_id: str = Query(..., min_length=1)) -> dict:
    """可选轮询：是否已结束（与 Bungalow ``pending`` 类似）。"""
    return orchestrated_pending(run_id)


@router.post("/prompt")
async def submit_prompt(body: SubmitPromptRequest) -> dict:
    """接收用户输入并提交给指定会话的 Agent 子进程。"""
    try:
        return chat_service.submit_prompt(
            body.sessionId,
            body.text,
            attachments=body.attachments if body.attachments else None,
        )
    except ValueError as e:
        detail = str(e)
        if "会话不存在" in detail:
            raise SessionNotFoundError(body.sessionId) from e
        raise ValidationError(detail) from e
    except RuntimeError as e:
        raise SessionNotFoundError(body.sessionId) from e


@router.post("/interrupt/{session_id}")
async def interrupt_session(session_id: str) -> dict:
    """中断指定会话正在进行的模型推理。"""
    ok = chat_service.interrupt_session(session_id)
    return {"ok": ok}


@router.post("/plan-chain/start")
async def plan_chain_start(body: PlanChainStartRequest) -> dict:
    """在服务端按顺序向模型投递各步用户消息，进度经该会话 SSE 推送（plan_chain.*）。"""
    sid = (body.sessionId or "").strip()
    if not sid:
        raise HTTPException(status_code=400, detail="sessionId 必填")
    mgr = _get_manager()
    info = mgr.find_agent_by_session(sid)
    if info is None:
        raise HTTPException(status_code=404, detail="会话不存在")
    agent_id = info.agent_id or ""
    steps_payload = [
        {
            "title": s.title,
            "action": s.action,
            "filePath": s.filePath,
            "id": s.id,
        }
        for s in body.steps
    ]
    ok, msg, artifact_id = await asyncio.to_thread(
        chat_service.start_plan_chain,
        sid,
        int(body.planAnchorTs),
        body.planSummary,
        steps_payload,
        step_timeout=float(body.stepTimeout or 900.0),
        name=body.name,
        raw_text=body.rawText,
        agent_id=agent_id,
    )
    if not ok and msg == "plan_chain_already_running":
        raise HTTPException(status_code=409, detail=msg)
    if not ok:
        raise HTTPException(status_code=400, detail=msg)
    return {"ok": True, "status": msg, "artifactId": artifact_id}


@router.post("/plan-chain/cancel/{session_id}")
async def plan_chain_cancel(session_id: str) -> dict:
    """仅取消规划链循环（不中断当前模型回合时可在步间停止）；通常与 /interrupt 联用。"""
    from backend.services.plan_chain import cancel_plan_chain

    cancel_plan_chain(session_id)
    return {"ok": True}


class PlanRegenerateRequest(BaseModel):
    sessionId: str
    originalText: str
    templatePrompt: str


@router.post("/plan/regenerate")
async def plan_regenerate(body: PlanRegenerateRequest) -> dict:
    """注入 JSON 模板提示词，让模型重新推理生成结构化规划。"""
    sid = (body.sessionId or "").strip()
    if not sid:
        raise HTTPException(status_code=400, detail="sessionId 必填")

    mgr = _get_manager()
    info = mgr.find_agent_by_session(sid)
    if info is None:
        raise HTTPException(status_code=404, detail="会话不存在")

    injected_text = f"{body.originalText.strip()}\n\n{body.templatePrompt}"

    result = await asyncio.to_thread(
        chat_service.submit_prompt,
        sid,
        injected_text,
        None,
    )
    return {"ok": True, "result": result}


@router.get("/feishu/sessions")
async def feishu_sessions_list(
    limit: int = Query(30, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> dict:
    """只读：消息网关 ``HERMES_HOME/state.db`` 中 ``source=feishu`` 的会话列表。"""
    return feishu_transcript_service.list_feishu_sessions(limit=limit, offset=offset)


@router.get("/feishu/sessions/{session_id}/messages")
async def feishu_session_messages(
    session_id: str,
    rich: bool = Query(False, description="为 true 时返回完整 transcript（含 tool 行、reasoning、tool_calls）"),
) -> dict:
    """只读：指定飞书会话消息；``rich=true`` 时与网关 ``SessionDB.get_messages`` 一致。"""
    if rich:
        out = feishu_transcript_service.get_feishu_session_transcript_rich(session_id)
    else:
        out = feishu_transcript_service.get_feishu_session_messages(session_id)
    err = str(out.get("error") or "")
    if out.get("ok"):
        return out
    if err == "database_busy":
        raise HTTPException(
            status_code=503,
            detail=out.get("hint") or "state.db 暂时被占用",
        )
    if err in ("session_not_found", "not_feishu_session", "empty_session_id"):
        raise HTTPException(status_code=404, detail=err)
    return out


@router.get("/history/{session_id}")
async def session_history(session_id: str) -> dict:
    """获取指定会话的所有历史消息。"""
    try:
        return {"messages": chat_service.get_session_history(session_id)}
    except ValueError as e:
        raise SessionNotFoundError(session_id) from e


@router.get("/sessions/{session_id}/file-history")
async def session_history_from_file(session_id: str) -> dict:
    """直接从 Agent 的 sessions/*.jsonl 文件读取会话历史（不经过 state.db）。"""
    try:
        return {"messages": chat_service.get_session_history_from_file(session_id)}
    except ValueError as e:
        raise SessionNotFoundError(session_id) from e
    except FileNotFoundError:
        return {"messages": [], "hint": "JSONL file not found"}


@router.get("/sessions-files/{agent_id}")
async def list_session_files_endpoint(agent_id: str) -> dict:
    """列出 Agent sessions 目录下的会话文件（.jsonl / session_*.json）。"""
    try:
        return {"files": chat_service.list_session_files(agent_id)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/session-file/{agent_id}/{file_name:path}")
async def session_file_content(agent_id: str, file_name: str) -> dict:
    """读取指定会话文件的内容（兼容 .jsonl 和 session_*.json 格式）。"""
    try:
        return {"messages": chat_service.get_session_file_content(agent_id, file_name)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except FileNotFoundError:
        return {"messages": [], "hint": "Session file not found"}


@router.get("/sessions/{session_id}/chain")
async def get_session_chain(session_id: str, max_depth: int = Query(default=10, ge=1, le=50)) -> dict:
    """获取 session 的完整续接链（从最老到最新）。

    用于压缩上下文后新 session 续接旧对话。
    """
    from backend.services import agent_db
    chain = agent_db.get_session_chain(session_id, max_depth)
    return {"chain": chain, "current": session_id}


@router.post("/approval")
async def respond_approval(body: ApprovalRequest) -> dict:
    """响应 Agent 发起的工具调用审批请求。"""
    if not chat_service.respond_approval(body.session_id, body.choice, body.all):
        raise HTTPException(status_code=404, detail="会话不存在")
    return {"ok": True}


@router.post("/clarify")
async def respond_clarify(body: ClarifyRequest) -> dict:
    """响应 Agent 发起的澄清请求（多选一交互）。"""
    if not chat_service.respond_clarify(body.session_id, body.request_id, body.answer):
        raise HTTPException(status_code=404, detail="会话不存在")
    return {"ok": True}


@router.get("/sessions/last-active")
async def get_last_active_session() -> dict:
    """返回所有 agent 中最晚活跃的 session。若不在内存中则自动恢复。"""
    return chat_service.get_last_active_session()


@router.get("/sessions/{session_id}/chain-history")
async def get_session_chain_history(session_id: str, max_depth: int = Query(default=10, ge=1, le=50)) -> dict:
    """获取 session 完整续接链的历史消息（按时间从老到新排列）。

    用于上下文压缩后新 session 续接旧对话时获取完整对话历史。
    """
    try:
        messages = chat_service.get_full_session_chain_history(session_id, max_depth)
        return {"messages": messages}
    except ValueError as e:
        raise SessionNotFoundError(session_id) from e
