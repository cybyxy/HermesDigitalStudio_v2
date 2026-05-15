"""Plan Artifact / Step 数据访问对象。

所有对 ``plan_artifacts`` / ``plan_artifact_steps`` 表的操作须经此类。
"""

from __future__ import annotations

import json
import logging
import time as _time
from typing import Any

from backend.db.connection import get_connection

_log = logging.getLogger(__name__)

_ARTIFACT_STATUSES = frozenset({"pending", "running", "completed", "aborted"})
_STEP_STATUSES = frozenset({"pending", "active", "done", "failed"})


def _norm_artifact_status(v: str) -> str:
    return v if v in _ARTIFACT_STATUSES else "pending"


def _norm_step_status(v: str) -> str:
    return v if v in _STEP_STATUSES else "pending"


class PlanArtifactDAO:
    """Plan Artifact 主表 DAO。"""

    @staticmethod
    def upsert(
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
        try:
            conn = get_connection()
            now = created_at if created_at is not None else _time.time()
            cur = conn.execute(
                """
                INSERT INTO plan_artifacts
                    (session_id, agent_id, name, plan_summary, steps_json, raw_text, status, current_step, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id, agent_id, name, plan_summary, steps_json, raw_text,
                    _norm_artifact_status(status), current_step, now,
                ),
            )
            conn.commit()
            artifact_id = cur.lastrowid
            conn.close()
            return artifact_id
        except Exception:
            _log.exception("PlanArtifactDAO.upsert failed")
            return None

    @staticmethod
    def update_status(
        artifact_id: int,
        *,
        status: str | None = None,
        current_step: int | None = None,
    ) -> bool:
        try:
            conn = get_connection()
            fields, args = [], []
            if status is not None:
                fields.append("status = ?")
                args.append(_norm_artifact_status(status))
            if current_step is not None:
                fields.append("current_step = ?")
                args.append(current_step)
            if not fields:
                return True
            args.append(artifact_id)
            cur = conn.execute(
                f"UPDATE plan_artifacts SET {', '.join(fields)} WHERE id = ?",
                tuple(args),
            )
            conn.commit()
            ok = cur.rowcount > 0
            conn.close()
            return ok
        except Exception:
            _log.exception("PlanArtifactDAO.update_status failed")
            return False

    @staticmethod
    def get_by_id(artifact_id: int) -> dict | None:
        try:
            conn = get_connection()
            cur = conn.execute(
                """
                SELECT id, session_id, agent_id, name, plan_summary, steps_json,
                       raw_text, status, current_step, created_at
                FROM plan_artifacts
                WHERE id = ?
                LIMIT 1
                """,
                (artifact_id,),
            )
            r = cur.fetchone()
            conn.close()
            if not r:
                return None
            return {
                "id": r[0],
                "sessionId": r[1],
                "agentId": r[2],
                "name": r[3],
                "planSummary": r[4],
                "steps": json.loads(r[5]) if r[5] else [],
                "rawText": r[6],
                "status": r[7],
                "currentStep": r[8],
                "createdAt": r[9],
            }
        except Exception:
            _log.exception("PlanArtifactDAO.get_by_id failed")
            return None

    @staticmethod
    def list_for_session(session_id: str, limit: int = 50) -> list[dict]:
        try:
            conn = get_connection()
            cur = conn.execute(
                """
                SELECT a.id, a.session_id, a.agent_id, a.name, a.plan_summary, a.steps_json,
                       a.raw_text, a.status, a.current_step, a.created_at,
                       s.step_index, s.step_id, s.title, s.action, s.file_path,
                       s.executor, s.session_id, s.status, s.error, s.completed_at
                  FROM plan_artifacts a
             LEFT JOIN plan_artifact_steps s ON s.artifact_id = a.id
                 WHERE a.session_id = ?
              ORDER BY a.created_at DESC, s.step_index ASC
                """,
                (session_id,),
            )
            rows = cur.fetchall()
            conn.close()
            return _rows_to_artifacts(rows)
        except Exception:
            _log.exception("PlanArtifactDAO.list_for_session failed")
            return []

    @staticmethod
    def list_for_agent(agent_id: str, limit: int = 500) -> list[dict]:
        try:
            conn = get_connection()

            led_ids = {r[0] for r in conn.execute(
                "SELECT id FROM plan_artifacts WHERE agent_id = ?", (agent_id,),
            ).fetchall()}

            participated_ids = [r[0] for r in conn.execute(
                "SELECT DISTINCT artifact_id FROM plan_artifact_steps WHERE executor = ?",
                (agent_id,),
            ).fetchall()]

            all_ids = list(led_ids) + [pid for pid in participated_ids if pid not in led_ids]
            if not all_ids:
                conn.close()
                return []

            top_ids = [
                r[0] for r in conn.execute(
                    f"""
                    SELECT id FROM plan_artifacts
                     WHERE id IN ({",".join("?" * len(all_ids))})
                     ORDER BY created_at DESC
                     LIMIT ?
                    """,
                    all_ids + [limit],
                ).fetchall()
            ]
            if not top_ids:
                conn.close()
                return []

            placeholders = ",".join("?" * len(top_ids))
            rows = conn.execute(
                f"""
                SELECT a.id, a.session_id AS artifact_session_id, a.agent_id, a.name, a.plan_summary,
                       a.steps_json, a.raw_text, a.status AS artifact_status, a.current_step, a.created_at,
                       CASE WHEN a.agent_id = ? THEN 'led' ELSE 'participated' END AS participation,
                       s.step_index, s.step_id, s.title, s.action, s.file_path,
                       s.executor, s.session_id AS step_session_id, s.status AS step_status, s.error, s.completed_at,
                       s.result
                  FROM plan_artifacts a
             LEFT JOIN plan_artifact_steps s ON s.artifact_id = a.id
                 WHERE a.id IN ({placeholders})
                 ORDER BY a.created_at DESC, s.step_index ASC
                """,
                [agent_id] + top_ids,
            ).fetchall()
            conn.close()
            return _rows_to_artifacts(rows, participation_col=True)
        except Exception:
            _log.exception("PlanArtifactDAO.list_for_agent failed")
            return []

    @staticmethod
    def delete(artifact_id: int) -> bool:
        try:
            conn = get_connection()
            conn.execute("DELETE FROM plan_artifact_steps WHERE artifact_id = ?", (artifact_id,))
            cur = conn.execute("DELETE FROM plan_artifacts WHERE id = ?", (artifact_id,))
            deleted = cur.rowcount or 0
            conn.commit()
            conn.close()
            if deleted:
                _log.info("PlanArtifactDAO: deleted id=%s", artifact_id)
            return deleted > 0
        except Exception:
            _log.exception("PlanArtifactDAO.delete(%s) failed", artifact_id)
            return False

    @staticmethod
    def delete_all() -> dict[str, int]:
        try:
            conn = get_connection()
            conn.execute("PRAGMA wal_checkpoint(FULL)")
            cur_steps = conn.execute("DELETE FROM plan_artifact_steps")
            cur_art = conn.execute("DELETE FROM plan_artifacts")
            conn.commit()
            n_steps = cur_steps.rowcount if cur_steps.rowcount is not None and cur_steps.rowcount >= 0 else 0
            n_art = cur_art.rowcount if cur_art.rowcount is not None and cur_art.rowcount >= 0 else 0
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            conn.close()
            _log.info("PlanArtifactDAO.delete_all: artifacts=%s steps=%s", n_art, n_steps)
            return {"artifacts": n_art, "steps": n_steps}
        except Exception:
            _log.exception("PlanArtifactDAO.delete_all failed")
            return {"artifacts": 0, "steps": 0}


class PlanArtifactStepDAO:
    """Plan Artifact Step 子表 DAO。"""

    @staticmethod
    def upsert_batch(
        artifact_id: int,
        steps: list[dict],
        executor: str = "",
        session_id: str = "",
    ) -> bool:
        try:
            conn = get_connection()
            conn.execute("DELETE FROM plan_artifact_steps WHERE artifact_id = ?", (artifact_id,))
            for idx, s in enumerate(steps):
                conn.execute(
                    """
                    INSERT INTO plan_artifact_steps
                        (artifact_id, step_index, step_id, title, action, file_path, executor, session_id, status, completed_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending', NULL)
                    """,
                    (
                        artifact_id,
                        idx,
                        int(s.get("id") or 0),
                        str(s.get("title") or ""),
                        str(s.get("action") or ""),
                        str(s.get("filePath") or "") if s.get("filePath") else None,
                        executor,
                        session_id,
                    ),
                )
            conn.commit()
            conn.close()
            return True
        except Exception:
            _log.exception("PlanArtifactStepDAO.upsert_batch failed")
            return False

    @staticmethod
    def update_status(
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
        try:
            conn = get_connection()
            fields, args = [], []
            if status is not None:
                fields.append("status = ?")
                args.append(_norm_step_status(status))
            if error is not None:
                fields.append("error = ?")
                args.append(error)
            if executor is not None:
                fields.append("executor = ?")
                args.append(executor)
            if session_id is not None:
                fields.append("session_id = ?")
                args.append(session_id)
            if completed_at is not None:
                fields.append("completed_at = ?")
                args.append(completed_at)
            if result is not None:
                fields.append("result = ?")
                args.append(result)
            if not fields:
                return True
            args.extend([artifact_id, step_index])
            cur = conn.execute(
                f"UPDATE plan_artifact_steps SET {', '.join(fields)} "
                "WHERE artifact_id = ? AND step_index = ?",
                tuple(args),
            )
            conn.commit()
            ok = cur.rowcount > 0
            conn.close()
            return ok
        except Exception:
            _log.exception("PlanArtifactStepDAO.update_status failed")
            return False

    @staticmethod
    def list_for_artifact(artifact_id: int) -> list[dict]:
        try:
            conn = get_connection()
            cur = conn.execute(
                """
                SELECT id, artifact_id, step_index, step_id, title, action, file_path,
                       executor, session_id, status, error, completed_at
                FROM plan_artifact_steps
                WHERE artifact_id = ?
                ORDER BY step_index ASC
                """,
                (artifact_id,),
            )
            rows = cur.fetchall()
            conn.close()
            return [
                {
                    "id": r[0],
                    "artifactId": r[1],
                    "stepIndex": r[2],
                    "stepId": r[3],
                    "title": r[4],
                    "action": r[5],
                    "filePath": r[6],
                    "executor": r[7],
                    "sessionId": r[8],
                    "status": r[9],
                    "error": r[10],
                    "completedAt": r[11],
                }
                for r in rows
            ]
        except Exception:
            _log.exception("PlanArtifactStepDAO.list_for_artifact failed")
            return []


# ── Internal helpers ─────────────────────────────────────────────────────────

def _rows_to_artifacts(rows: list, participation_col: bool = False) -> list[dict]:
    """将 JOIN 查询结果按 artifact id 分组，组装成 dict 列表。"""
    by_artifact: dict[int, dict] = {}
    for r in rows:
        aid = r[0]
        if aid not in by_artifact:
            offset = 11 if participation_col else 10
            by_artifact[aid] = {
                "id": r[0],
                "sessionId": r[1],
                "agentId": r[2],
                "name": r[3],
                "planSummary": r[4],
                "steps": [],
                "rawText": r[6] if not participation_col else r[6],
                "status": r[7] if not participation_col else r[7],
                "currentStep": r[8] if not participation_col else r[8],
                "createdAt": r[9] if not participation_col else r[9],
            }
            if participation_col:
                by_artifact[aid]["participation"] = r[10]
        step_offset = 11 if participation_col else 10
        if r[step_offset] is not None:
            by_artifact[aid]["steps"].append({
                "stepIndex": r[step_offset],
                "stepId": r[step_offset + 1],
                "title": r[step_offset + 2] or "",
                "action": r[step_offset + 3] or "",
                "filePath": r[step_offset + 4],
                "executor": r[step_offset + 5],
                "sessionId": r[step_offset + 6],
                "stepStatus": r[step_offset + 7],
                "error": r[step_offset + 8],
                "completedAt": r[step_offset + 9],
            })
            if participation_col and len(r) > step_offset + 10:
                by_artifact[aid]["steps"][-1]["result"] = r[step_offset + 10]
    return list(by_artifact.values())
