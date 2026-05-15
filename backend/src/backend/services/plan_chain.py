"""服务端规划链：顺序向推理会话投递每步任务，经现有 SSE 推送进度与时间线状态。"""

from __future__ import annotations

import logging
import threading
import time as _time
from typing import Any

_log = logging.getLogger(__name__)

_CHAIN_LOCK = threading.Lock()
_RUNNING: set[str] = set()
_CANCEL: dict[str, threading.Event] = {}


def cancel_plan_chain(session_id: str) -> None:
    """向指定会话的规划链发送取消信号。"""
    ev = _CANCEL.get(session_id)
    if ev is not None:
        ev.set()


def _emit(gw: Any, session_id: str, typ: str, payload: dict[str, Any]) -> None:
    """通过 SSE 向前端推送规划链事件。"""
    try:
        gw.dispatch_synthetic_event(session_id, typ, payload)
    except Exception as exc:
        _log.debug("plan_chain emit %s: %s", typ, exc)


def _build_step_prompt(
    *,
    plan_summary: str,
    step_index: int,
    step_total: int,
    title: str,
    action: str,
    file_path: str | None,
) -> str:
    fp = (file_path or "").strip()
    fp_line = f"\n相关路径：`{fp}`" if fp else ""
    summ = (plan_summary or "").strip()
    summ_block = f"\n总览：{summ}\n" if summ else "\n"
    return (
        "【Hermes Digital Studio · 规划链自动执行】\n"
        f"正在执行第 {step_index + 1}/{step_total} 步。不要输出 JSON 规划代码块；"
        "直接完成本步工作并简明汇报结果。\n"
        f"{summ_block}"
        f"本步标题：{title}\n"
        f"本步动作：{action}"
        f"{fp_line}"
    )


def _run_chain(
    session_id: str,
    plan_anchor_ts: int,
    plan_summary: str,
    steps: list[dict[str, Any]],
    step_timeout: float,
    artifact_id: int | None = None,
    name: str = "",
) -> None:
    from backend.services.agent import _get_manager
    from backend.services.agent_chat_bridge import submit_with_hint, await_submit_and_complete

    cancel_ev = _CANCEL.get(session_id)
    mgr = _get_manager()
    info = mgr.find_agent_by_session(session_id)
    if info is None:
        _log.warning("plan_chain: session not found %s", session_id)
        return
    gw = info.gateway
    step_executor = info.agent_id
    n = len(steps)
    source_session_id = session_id

    # ── DB helpers (lazy import, avoids circular) ──────────────────────────────
    def _update_artifact(**kw):
        if artifact_id is None:
            return
        try:
            from backend.services import plan_db as _db
            _db.update_plan_artifact_status(artifact_id, **kw)
        except Exception:
            _log.debug("plan_artifact status update failed", exc_info=True)

    def _update_step(idx: int, **kw):
        if artifact_id is None:
            return
        try:
            from backend.services import plan_db as _db
            _db.update_plan_step_status(artifact_id, idx, **kw)
        except Exception:
            _log.debug("plan_step status update failed", exc_info=True)

    def _dispatch(typ: str, payload: dict[str, Any]) -> None:
        payload = {**payload, "planAnchorTs": plan_anchor_ts, "sourceSessionId": source_session_id}
        if artifact_id is not None:
            payload["artifactId"] = artifact_id
        _emit(gw, session_id, typ, payload)

    try:
        _update_artifact(status="running")
        _dispatch(
            "plan_chain.started",
            {"total": n, "planSummary": plan_summary, "name": name},
        )
        for i, step in enumerate(steps):
            if cancel_ev is not None and cancel_ev.is_set():
                _dispatch("plan_chain.aborted", {"atIndex": i, "reason": "cancelled"})
                _update_artifact(status="aborted")
                return
            title = str(step.get("title") or "").strip() or f"步骤 {i + 1}"
            action = str(step.get("action") or "").strip() or "—"
            fp = step.get("filePath") or step.get("file_path")
            fp_s = str(fp).strip() if fp else None

            _update_artifact(current_step=i)
            _update_step(i, status="active", executor=step_executor, session_id=session_id)
            _dispatch(
                "plan_chain.step_begin",
                {"index": i, "total": n, "title": title, "action": action},
            )

            prompt = _build_step_prompt(
                plan_summary=plan_summary,
                step_index=i,
                step_total=n,
                title=title,
                action=action,
                file_path=fp_s,
            )

            wait = await_submit_and_complete(
                gw,
                session_id,
                timeout=step_timeout,
                submit_fn=lambda: submit_with_hint(session_id, prompt, None),
            )
            ok = bool(wait.get("ok"))
            err = str(wait.get("error") or "")
            reply = str(wait.get("reply") or "")
            _update_step(
                i,
                status="done" if ok else "failed",
                error=err if not ok else None,
                executor=step_executor,
                session_id=session_id,
                completed_at=_time.time(),
                result=reply if ok else None,
            )
            _dispatch(
                "plan_chain.step_end",
                {
                    "index": i,
                    "total": n,
                    "ok": ok,
                    "error": err,
                },
            )
            if not ok:
                _dispatch("plan_chain.error", {"index": i, "message": err or "step_failed"})
                return

        # 最后一步：汇总交付物清单
        _dispatch("plan_chain.step_begin", {
            "index": n,
            "total": n + 1,
            "title": "汇总交付物",
            "action": "列出所有创建的文件和目录"
        })
        _update_step(n, status="active", executor=step_executor, session_id=session_id)

        deliverable_prompt = (
            "【Hermes Digital Studio · 规划链自动执行】\n"
            "所有功能步骤已完成。请执行以下汇总任务：\n\n"
            "1. 列出本项目创建的所有文件（含路径），格式如下：\n"
            "```\n"
            "[文件]\n"
            "  path/to/file1.ext\n"
            "  path/to/file2.ext\n"
            "...\n"
            "```\n\n"
            "2. 列出本项目创建的所有目录（不含 node_modules/.venv 等依赖目录），格式如下：\n"
            "```\n"
            "[目录]\n"
            "  path/to/dir1/\n"
            "  path/to/dir2/\n"
            "...\n"
            "```\n\n"
            "3. 如果有重要说明（如启动方式、端口、依赖等），请在最后补充。\n"
            "4. 不要输出 JSON 规划代码块，直接输出汇总内容。\n"
        )

        wait = await_submit_and_complete(
            gw,
            session_id,
            timeout=step_timeout,
            submit_fn=lambda: submit_with_hint(session_id, deliverable_prompt, None),
        )
        ok = bool(wait.get("ok"))
        err = str(wait.get("error") or "")
        reply = str(wait.get("reply") or "")
        _update_step(
            n,
            status="done" if ok else "failed",
            error=err if not ok else None,
            executor=step_executor,
            session_id=session_id,
            completed_at=_time.time(),
            result=reply if ok else None,
        )
        _dispatch("plan_chain.step_end", {
            "index": n,
            "total": n + 1,
            "ok": ok,
            "error": err,
        })

        _update_artifact(status="completed")
        _dispatch("plan_chain.complete", {
            "total": n + 1,
            "deliverable": reply if ok else None,
            "deliverable_summary": "交付物清单" if ok else None
        })
    except Exception as exc:
        _log.exception("plan_chain failed session=%s", session_id)
        _update_artifact(status="aborted")
        _emit(
            gw,
            session_id,
            "plan_chain.error",
            {"message": str(exc), "fatal": True},
        )
    finally:
        with _CHAIN_LOCK:
            _RUNNING.discard(session_id)
            _CANCEL.pop(session_id, None)


def start_plan_chain_background(
    session_id: str,
    plan_anchor_ts: int,
    plan_summary: str,
    steps: list[dict[str, Any]],
    *,
    step_timeout: float = 900.0,
    artifact_id: int | None = None,
    name: str = "",
) -> tuple[bool, str]:
    """若本会话尚无运行中的链，则启动后台线程顺序执行各步。返回 (ok, message)。"""
    sid = (session_id or "").strip()
    if not sid:
        return False, "sessionId 必填"
    if not steps:
        return False, "steps 为空"
    with _CHAIN_LOCK:
        if sid in _RUNNING:
            return False, "plan_chain_already_running"
        _RUNNING.add(sid)
        _CANCEL[sid] = threading.Event()

    t = threading.Thread(
        target=_run_chain,
        args=(sid, int(plan_anchor_ts), plan_summary, steps, float(step_timeout), artifact_id, name),
        daemon=True,
        name=f"plan-chain-{sid[:8]}",
    )
    t.start()
    return True, "started"
