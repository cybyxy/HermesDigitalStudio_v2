"""规划（Plan）业务逻辑层：封装 plan_db 的原子操作，向上为路由层提供业务用例。

对应 Spring Boot Service 层。
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from backend.services import plan_db as _plan_db

_log = logging.getLogger(__name__)


def save_plan_artifact(
    session_id: str,
    agent_id: str,
    name: str,
    plan_summary: str,
    steps: list[dict],
    raw_text: str | None = None,
    created_at: float | None = None,
) -> int | None:
    """将 PlanArtifact（含步骤列表）写入 SQLite。

    写入顺序：先插 artifact 主表行，再批量写入步骤子表。
    返回 artifact 自增 id，失败返回 None。
    """
    artifact_id = _plan_db.upsert_plan_artifact(
        session_id=session_id,
        agent_id=agent_id,
        name=name,
        plan_summary=plan_summary,
        steps_json=json.dumps(steps, ensure_ascii=False),
        raw_text=raw_text,
        created_at=created_at,
    )
    if artifact_id is None:
        return None
    if steps:
        _plan_db.upsert_plan_steps(artifact_id, steps, executor=agent_id)
    return artifact_id


def get_plan_artifacts(session_id: str, limit: int = 50) -> list[dict]:
    """读取指定会话的规划历史（不含步骤子表）。"""
    return _plan_db.get_plan_artifacts_for_session(session_id, limit=limit)


def get_plan_artifacts_for_agent(agent_id: str, limit: int = 500) -> list[dict]:
    """读取某 Agent 主导或参与的所有规划（含步骤执行状态），按创建时间降序。"""
    return _plan_db.get_plan_artifacts_for_agent(agent_id, limit=limit)


def get_plan_artifact_with_steps(artifact_id: int) -> dict | None:
    """读取某 artifact 及其全部步骤子表记录。"""
    artifact = _plan_db.get_plan_artifact_by_id(artifact_id)
    if artifact is None:
        return None
    artifact["steps"] = _plan_db.get_plan_steps_for_artifact(artifact_id)
    return artifact


def update_plan_chain_step(
    artifact_id: int,
    step_index: int,
    *,
    status: str | None = None,
    error: str | None = None,
    executor: str | None = None,
    completed_at: float | None = None,
) -> bool:
    """更新规划链中某一步的状态。"""
    return _plan_db.update_plan_step_status(
        artifact_id, step_index, status=status, error=error, executor=executor, completed_at=completed_at
    )


def update_plan_artifact_status(
    artifact_id: int,
    *,
    status: str | None = None,
    current_step: int | None = None,
) -> bool:
    """更新规划主表的执行状态。"""
    return _plan_db.update_plan_artifact_status(
        artifact_id, status=status, current_step=current_step
    )


def delete_plan_artifact(artifact_id: int) -> bool:
    """删除指定主键的规划及其所有步骤（子表先删）。返回 True 表示删除成功。"""
    return _plan_db.delete_plan_artifact(artifact_id)


def delete_all_plans() -> dict[str, int]:
    """删除全部任务规划记录（主表 plan_artifacts + 子表 plan_artifact_steps）。返回删除数量。"""
    return _plan_db.delete_all_plans()


def resolve_agent_id_for_session(session_id: str) -> str:
    """根据 session_id 解析对应的 agent_id。"""
    from backend.services.agent import _get_manager
    mgr = _get_manager()
    info = mgr.find_agent_by_session(session_id)
    return info.agent_id if info else ""


def get_step_result(session_id: str, completed_at: float) -> dict:
    """根据 session_id 和 completed_at（秒）查找该时间点最近的一条助手推理结果。

    优先通过运行中的 Agent gateway RPC 读取；若 Agent 已关闭，则直接从 Hermes 数据库读取。
    """
    from backend.services.agent import _get_manager

    _log.info("get_step_result: session_id=%s, completed_at=%s", session_id, completed_at)

    mgr = _get_manager()
    info = mgr.find_agent_by_session(session_id)
    _log.info("get_step_result: info=%s", "found" if info is not None else "None")
    history: list[dict] = []

    if info is not None:
        _log.info("get_step_result: trying gateway RPC")
        history = info.gateway.session_history(session_id) or []
        _log.info("get_step_result: gateway RPC returned %d rows", len(history))

    if not history:
        _log.info("get_step_result: trying Hermes DB")
        history = _get_history_from_hermes_db(session_id, completed_at)
        _log.info("get_step_result: Hermes DB returned %d rows", len(history))

    best: dict | None = None
    best_diff = float("inf")
    for msg in history:
        ts = msg.get("timestamp")
        if msg.get("role") == "assistant" and ts is not None:
            diff = abs(float(ts) - completed_at)
            if diff < best_diff:
                best_diff = diff
                best = msg

    _log.info("get_step_result: best_match diff=%s, best=%s", best_diff, "found" if best else "None")

    if best is None:
        return {"ok": True, "result": None, "sessionId": session_id}
    return {
        "ok": True,
        "result": {
            "text": best.get("text", ""),
            "timestamp": best.get("timestamp"),
            "role": best.get("role"),
        },
        "sessionId": session_id,
    }


def _get_history_from_hermes_db(session_id: str, completed_at: float | None = None) -> list[dict]:
    """直接从 Hermes state.db 读取会话历史。

    优先通过 session_id 查询；若查询结果为空或已关闭 Agent，则通过时间戳范围搜索。
    """
    try:
        import sqlite3

        try:
            from hermes_constants import get_hermes_home
            db_path = get_hermes_home() / "state.db"
        except ImportError:
            db_path = Path.home() / ".hermes" / "state.db"

        _log.info("_get_history_from_hermes_db: session_id=%s, completed_at=%s, db_path=%s", session_id, completed_at, db_path)

        if not db_path.exists():
            _log.warning("_get_history_from_hermes_db: DB not found at %s", db_path)
            return []

        conn = sqlite3.connect(str(db_path))

        cursor = conn.execute(
            """
            SELECT role, content, timestamp
            FROM messages
            WHERE session_id = ? AND role = 'assistant'
            ORDER BY timestamp ASC
            """,
            (session_id,),
        )
        rows = cursor.fetchall()
        _log.info("_get_history_from_hermes_db: session_id query found %d rows", len(rows))

        if not rows and completed_at is not None:
            time_min = completed_at - 60
            time_max = completed_at + 60
            cursor = conn.execute(
                """
                SELECT session_id, role, content, timestamp
                FROM messages
                WHERE timestamp BETWEEN ? AND ? AND role = 'assistant'
                ORDER BY timestamp ASC
                """,
                (time_min, time_max),
            )
            rows = cursor.fetchall()
            _log.info("_get_history_from_hermes_db: time-based query found %d rows (range: %s - %s)", len(rows), time_min, time_max)
            if rows:
                _log.info("_get_history_from_hermes_db: Found session_id=%s", rows[0][0])

        conn.close()

        history = []
        for row in rows:
            if len(row) == 4:
                _, role, content, timestamp = row
            else:
                role, content, timestamp = row[0], row[1], row[2]
            if content:
                try:
                    parsed = json.loads(content)
                    text = parsed.get("text", "") if isinstance(parsed, dict) else str(parsed)
                except (json.JSONDecodeError, TypeError):
                    text = str(content) if content else ""
                history.append({
                    "role": role,
                    "text": text,
                    "timestamp": timestamp,
                })
        _log.info("_get_history_from_hermes_db: returning %d history entries", len(history))
        return history
    except Exception as e:
        _log.error("_get_history_from_hermes_db: error: %s", e)
        return []
