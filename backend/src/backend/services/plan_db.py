"""Plan Artifact SQLite persistence (delegated to DAO layer).

所有操作委托给 ``backend.db.plan`` 中的 DAO 类。
保留本文件仅用于向后兼容。
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading

from backend.core.config import get_config
from backend.db.plan import PlanArtifactDAO, PlanArtifactStepDAO
from backend.db.connection import ensure_schema, get_connection

_log = logging.getLogger(__name__)
_lock = threading.Lock()

# ── 路径解析 ──────────────────────────────────────────────────────────

_DATA_DIR = get_config().studio_data_dir
_DB_PATH = _DATA_DIR / "HermesDigitalStudio.db"


def _get_conn() -> sqlite3.Connection:
    """向后兼容：获取数据库连接（不自动初始化 schema）。"""
    with _lock:
        conn = sqlite3.connect(str(_DB_PATH), check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL")
        return conn


def _ensure_artifacts_schema(conn: sqlite3.Connection) -> None:
    """保留向后兼容的 schema 检查（委托给 connection 层）。"""
    from backend.db.connection import _ensure_plan_artifacts_schema
    _ensure_plan_artifacts_schema(conn)


def _ensure_steps_schema(conn: sqlite3.Connection) -> None:
    """保留向后兼容的 schema 检查（委托给 connection 层）。"""
    from backend.db.connection import _ensure_plan_artifact_steps_schema
    _ensure_plan_artifact_steps_schema(conn)


# ── Artifact ──────────────────────────────────────────────────────────────────

def upsert_plan_artifact(
    *,
    session_id: str,
    agent_id: str,
    name: str,
    plan_summary: str,
    steps_json: str,
    raw_text: str | None = None,
    status: str = "pending",
    current_step: int = -1,
    created_at: float | None = None,
) -> int | None:
    return PlanArtifactDAO.upsert(
        session_id=session_id,
        agent_id=agent_id,
        name=name,
        plan_summary=plan_summary,
        steps_json=steps_json,
        raw_text=raw_text,
        status=status,
        current_step=current_step,
        created_at=created_at,
    )


def update_plan_artifact_status(
    artifact_id: int,
    *,
    status: str | None = None,
    current_step: int | None = None,
) -> bool:
    return PlanArtifactDAO.update_status(artifact_id, status=status, current_step=current_step)


def upsert_plan_steps(
    artifact_id: int,
    steps: list[dict],
    executor: str = "",
    session_id: str = "",
) -> bool:
    return PlanArtifactStepDAO.upsert_batch(artifact_id, steps, executor, session_id)


def update_plan_step_status(
    artifact_id: int,
    step_index: int,
    *,
    status: str | None = None,
    error: str | None = None,
    executor: str | None = None,
    session_id: str | None = None,
    completed_at: float | None = None,
    result: str | None = None,
) -> bool:
    return PlanArtifactStepDAO.update_status(
        artifact_id, step_index,
        status=status, error=error, executor=executor,
        session_id=session_id, completed_at=completed_at, result=result,
    )


def get_plan_artifacts_for_session(session_id: str, limit: int = 50) -> list[dict]:
    return PlanArtifactDAO.list_for_session(session_id, limit=limit)


def get_plan_steps_for_artifact(artifact_id: int) -> list[dict]:
    return PlanArtifactStepDAO.list_for_artifact(artifact_id)


def get_plan_artifact_by_id(artifact_id: int) -> dict | None:
    return PlanArtifactDAO.get_by_id(artifact_id)


def get_plan_artifacts_for_agent(agent_id: str, limit: int = 500) -> list[dict]:
    return PlanArtifactDAO.list_for_agent(agent_id, limit=limit)


def delete_plan_artifact(artifact_id: int) -> bool:
    return PlanArtifactDAO.delete(artifact_id)


def delete_all_plans() -> dict[str, int]:
    return PlanArtifactDAO.delete_all()
