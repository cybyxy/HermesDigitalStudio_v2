"""Agent 数据访问对象：头像、性别、办公室位姿、性格设定。

所有对 ``agent_avatars`` / ``agent_personality`` 表的操作须经此类。
"""

from __future__ import annotations

import logging
import sqlite3
from typing import Any

from backend.db.connection import get_connection

_log = logging.getLogger(__name__)

_VALID_FACING = frozenset({"down", "up", "left", "right"})


class AgentAvatarDAO:
    """Agent 头像 / 性别 / 办公室位姿 DAO。"""

    # ── Avatar ─────────────────────────────────────────────────────────────

    @staticmethod
    def get_avatar(agent_id: str) -> str | None:
        try:
            conn = get_connection()
            cur = conn.execute(
                "SELECT avatar FROM agent_avatars WHERE agent_id = ?",
                (agent_id,),
            )
            row = cur.fetchone()
            conn.close()
            return row[0] if row else None
        except Exception:
            _log.warning("DAO query failed", exc_info=True)
            return None

    @staticmethod
    def set_avatar(agent_id: str, avatar: str, gender: str | None = None) -> None:
        try:
            conn = get_connection()
            if gender is not None:
                conn.execute(
                    "INSERT INTO agent_avatars (agent_id, avatar, gender) VALUES (?, ?, ?) "
                    "ON CONFLICT(agent_id) DO UPDATE SET avatar = excluded.avatar, gender = excluded.gender",
                    (agent_id, avatar, gender),
                )
            else:
                conn.execute(
                    "INSERT INTO agent_avatars (agent_id, avatar) VALUES (?, ?) "
                    "ON CONFLICT(agent_id) DO UPDATE SET avatar = excluded.avatar",
                    (agent_id, avatar),
                )
            conn.commit()
            conn.close()
        except Exception:
            _log.warning("DAO operation failed", exc_info=True)

    # ── Gender ────────────────────────────────────────────────────────────

    @staticmethod
    def get_gender(agent_id: str) -> str:
        try:
            conn = get_connection()
            cur = conn.execute(
                "SELECT gender FROM agent_avatars WHERE agent_id = ?",
                (agent_id,),
            )
            row = cur.fetchone()
            conn.close()
            return row[0] if row and row[0] else 'male'
        except Exception:
            _log.warning('DAO get_gender failed', exc_info=True)
            return 'male'

    @staticmethod
    def set_gender(agent_id: str, gender: str) -> None:
        try:
            conn = get_connection()
            conn.execute(
                "INSERT INTO agent_avatars (agent_id, gender) VALUES (?, ?) "
                "ON CONFLICT(agent_id) DO UPDATE SET gender = excluded.gender",
                (agent_id, gender),
            )
            conn.commit()
            conn.close()
        except Exception:
            _log.warning("DAO operation failed", exc_info=True)

    # ── Office Pose ────────────────────────────────────────────────────────

    @staticmethod
    def get_office_pose(agent_id: str) -> dict[str, float | str] | None:
        try:
            conn = get_connection()
            cur = conn.execute(
                "SELECT office_x, office_y, facing FROM agent_avatars WHERE agent_id = ?",
                (agent_id,),
            )
            row = cur.fetchone()
            conn.close()
            if not row or row[0] is None or row[1] is None:
                return None
            f = str(row[2] or "down").lower()
            if f not in _VALID_FACING:
                f = "down"
            return {"x": float(row[0]), "y": float(row[1]), "facing": f}
        except Exception:
            _log.warning("DAO query failed", exc_info=True)
            return None

    @staticmethod
    def upsert_office_poses(poses: dict[str, dict]) -> None:
        if not poses:
            return
        try:
            conn = get_connection()
            for aid, p in poses.items():
                if not aid or not isinstance(p, dict):
                    continue
                x = float(p.get("x", 0.0))
                y = float(p.get("y", 0.0))
                f = str(p.get("facing", "down") or "down").lower()
                if f not in _VALID_FACING:
                    f = "down"
                row = conn.execute(
                    "SELECT avatar, gender FROM agent_avatars WHERE agent_id = ?",
                    (aid,),
                ).fetchone()
                avatar = row[0] if row and row[0] else "badboy"
                gender = row[1] if row and row[1] else "male"
                conn.execute(
                    """
                    INSERT INTO agent_avatars (agent_id, avatar, gender, office_x, office_y, facing)
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(agent_id) DO UPDATE SET
                        office_x = excluded.office_x,
                        office_y = excluded.office_y,
                        facing = excluded.facing
                    """,
                    (aid, avatar, gender, x, y, f),
                )
            conn.commit()
            conn.close()
        except Exception:
            _log.warning("DAO operation failed", exc_info=True)

    # ── Model config ────────────────────────────────────────────────────────

    @staticmethod
    def get_agent_model(agent_id: str) -> dict[str, str]:
        """Returns {model, model_provider, model_base_url} for an agent (all may be empty)."""
        try:
            conn = get_connection()
            cur = conn.execute(
                "SELECT model, model_provider, model_base_url FROM agent_avatars WHERE agent_id = ?",
                (agent_id,),
            )
            row = cur.fetchone()
            conn.close()
            if row:
                return {
                    "model": row[0] or "",
                    "model_provider": row[1] or "",
                    "model_base_url": row[2] or "",
                }
        except Exception as e:
            _log.warning("AgentAvatarDAO.get_agent_model(%s) failed: %s", agent_id, e)
        return {"model": "", "model_provider": "", "model_base_url": ""}

    @staticmethod
    def set_agent_model(
        agent_id: str,
        model: str = "",
        model_provider: str = "",
        model_base_url: str = "",
    ) -> None:
        """Persist per-agent model config to the DB (upsert)."""
        try:
            conn = get_connection()
            conn.execute(
                """
                INSERT INTO agent_avatars (agent_id, model, model_provider, model_base_url)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(agent_id) DO UPDATE SET
                    model          = excluded.model,
                    model_provider = excluded.model_provider,
                    model_base_url = excluded.model_base_url
                """,
                (agent_id, model, model_provider, model_base_url),
            )
            conn.commit()
            conn.close()
        except Exception as e:
            _log.warning("AgentAvatarDAO.set_agent_model(%s) failed: %s", agent_id, e)

    # ── Batch read ────────────────────────────────────────────────────────

    @staticmethod
    def list_agents() -> dict[str, str]:
        try:
            conn = get_connection()
            cur = conn.execute("SELECT agent_id, avatar FROM agent_avatars")
            rows = cur.fetchall()
            conn.close()
            return {row[0]: row[1] for row in rows}
        except Exception as e:
            _log.warning("AgentAvatarDAO.list_agents failed: %s", e)
            return {}

    @staticmethod
    def list_agents_with_gender() -> dict[str, tuple[str, str]]:
        try:
            conn = get_connection()
            cur = conn.execute("SELECT agent_id, avatar, gender FROM agent_avatars")
            rows = cur.fetchall()
            conn.close()
            return {row[0]: (row[1], row[2] if len(row) > 2 else 'male') for row in rows}
        except Exception as e:
            _log.warning("AgentAvatarDAO.list_agents_with_gender failed: %s", e)
            return {}

    # ── Delete ─────────────────────────────────────────────────────────────

    @staticmethod
    def delete_agent(agent_id: str) -> None:
        """删除 Agent 的所有相关记录（头像、性格、关联规划、session）。"""
        try:
            conn = get_connection()
            conn.execute(
                """
                DELETE FROM plan_artifact_steps
                WHERE artifact_id IN (SELECT id FROM plan_artifacts WHERE agent_id = ?)
                """,
                (agent_id,),
            )
            conn.execute("DELETE FROM plan_artifacts WHERE agent_id = ?", (agent_id,))
            conn.execute("DELETE FROM agent_sessions WHERE agent_id = ?", (agent_id,))
            conn.execute("DELETE FROM agent_avatars WHERE agent_id = ?", (agent_id,))
            conn.execute("DELETE FROM agent_personality WHERE agent_id = ?", (agent_id,))
            conn.commit()
            conn.close()
        except Exception:
            _log.warning("DAO operation failed", exc_info=True)


class AgentSessionDAO:
    """Agent ↔ Session 映射 DAO，支持 session 持久化和重启恢复。"""

    @staticmethod
    def register_session(agent_id: str, session_id: str, parent_session_id: str | None = None, session_key: str | None = None) -> None:
        """注册/更新 agent 的 session 记录，同时更新 last_used_at。

        Args:
            agent_id: Agent ID
            session_id: Session ID (8-char hex, used as _sessions dict key)
            parent_session_id: 若不为空，表示该 session 是从另一个 session 压缩/续接而来的
            session_key: SessionDB 主键 (date-based format), 对应 state.db 和磁盘文件名
        """
        try:
            conn = get_connection()
            now = __import__("time").time()
            conn.execute(
                """
                INSERT INTO agent_sessions (agent_id, session_id, session_key, created_at, last_used_at, is_active, parent_session_id)
                VALUES (?, ?, ?, ?, ?, 1, ?)
                ON CONFLICT(agent_id, session_id) DO UPDATE SET
                    session_key = COALESCE(excluded.session_key, session_key),
                    last_used_at = excluded.last_used_at,
                    is_active = 1,
                    parent_session_id = COALESCE(excluded.parent_session_id, parent_session_id)
                """,
                (agent_id, session_id, session_key, now, now, parent_session_id),
            )
            # 将同一 agent 的其他 session 标记为非活跃
            conn.execute(
                "UPDATE agent_sessions SET is_active = 0 WHERE agent_id = ? AND session_id != ?",
                (agent_id, session_id),
            )
            conn.commit()
            conn.close()
        except Exception as e:
            _log.warning("AgentSessionDAO.register_session failed: %s", e)

    @staticmethod
    def get_active_session(agent_id: str) -> str | None:
        """获取 agent 当前活跃的 session_id。"""
        try:
            conn = get_connection()
            cur = conn.execute(
                """
                SELECT session_id FROM agent_sessions
                WHERE agent_id = ? AND is_active = 1
                ORDER BY last_used_at DESC
                LIMIT 1
                """,
                (agent_id,),
            )
            row = cur.fetchone()
            conn.close()
            return row[0] if row else None
        except Exception as e:
            _log.warning("AgentSessionDAO.get_active_session failed: %s", e)
            return None

    @staticmethod
    def list_agent_sessions(agent_id: str) -> list[dict]:
        """列出 agent 所有 session（按最后活跃时间倒序）。"""
        try:
            conn = get_connection()
            cur = conn.execute(
                """
                SELECT session_id, session_key, created_at, last_used_at, is_active, parent_session_id
                FROM agent_sessions
                WHERE agent_id = ?
                ORDER BY last_used_at DESC
                """,
                (agent_id,),
            )
            rows = cur.fetchall()
            conn.close()
            return [
                {
                    "session_id": r[0],
                    "session_key": r[1],
                    "created_at": r[2],
                    "last_used_at": r[3],
                    "is_active": bool(r[4]),
                    "parent_session_id": r[5] if len(r) > 5 else None,
                }
                for r in rows
            ]
        except Exception as e:
            _log.warning("AgentSessionDAO.list_agent_sessions failed: %s", e)
            return []

    @staticmethod
    def list_all_sessions() -> list[dict]:
        """列出所有 session（按最后活跃时间倒序）。"""
        try:
            conn = get_connection()
            cur = conn.execute(
                """
                SELECT s.session_id, s.agent_id, s.created_at, s.last_used_at, s.is_active, s.parent_session_id, s.session_key
                FROM agent_sessions s
                ORDER BY s.last_used_at DESC
                LIMIT 50
                """,
            )
            rows = cur.fetchall()
            conn.close()
            return [
                {
                    "sessionId": r[0],
                    "agentId": r[1],
                    "createdAt": r[2],
                    "lastUsedAt": r[3],
                    "isActive": bool(r[4]),
                    "parentSessionId": r[5] if len(r) > 5 else None,
                    "sessionKey": r[6] if len(r) > 6 else None,
                }
                for r in rows
            ]
        except Exception as e:
            _log.warning("AgentSessionDAO.list_all_sessions failed: %s", e)
            return []

    @staticmethod
    def get_parent_session(session_id: str) -> str | None:
        """获取指定 session 的父 session ID（用于压缩上下文后新 session 续接）。"""
        try:
            conn = get_connection()
            cur = conn.execute(
                "SELECT parent_session_id FROM agent_sessions WHERE session_id = ?",
                (session_id,),
            )
            row = cur.fetchone()
            conn.close()
            return row[0] if row and row[0] else None
        except Exception as e:
            _log.warning("AgentSessionDAO.get_parent_session failed: %s", e)
            return None

    @staticmethod
    def get_session_chain(session_id: str, max_depth: int = 10) -> list[str]:
        """获取 session 的完整续接链（从最老到最新）。"""
        chain = []
        current = session_id
        visited = set()
        for _ in range(max_depth):
            if current in visited:
                break
            visited.add(current)
            chain.append(current)
            parent = AgentSessionDAO.get_parent_session(current)
            if not parent:
                break
            current = parent
        return chain

    @staticmethod
    def touch_session(agent_id: str, session_id: str) -> None:
        """更新 session 的 last_used_at。"""
        try:
            conn = get_connection()
            now = __import__("time").time()
            conn.execute(
                "UPDATE agent_sessions SET last_used_at = ? WHERE agent_id = ? AND session_id = ?",
                (now, agent_id, session_id),
            )
            conn.commit()
            conn.close()
        except Exception as e:
            _log.warning("AgentSessionDAO.touch_session failed: %s", e)

    @staticmethod
    def delete_session(agent_id: str, session_id: str) -> None:
        """删除指定的 session 记录。"""
        try:
            conn = get_connection()
            conn.execute(
                "DELETE FROM agent_sessions WHERE agent_id = ? AND session_id = ?",
                (agent_id, session_id),
            )
            conn.commit()
            conn.close()
        except Exception as e:
            _log.warning("AgentSessionDAO.delete_session failed: %s", e)

    @staticmethod
    def set_active_session(agent_id: str, session_id: str) -> None:
        """将指定 session 标记为活跃，其他 session 标记为非活跃。"""
        try:
            conn = get_connection()
            now = __import__("time").time()
            # 先把所有该 agent 的 session 设为非活跃
            conn.execute(
                "UPDATE agent_sessions SET is_active = 0 WHERE agent_id = ?",
                (agent_id,),
            )
            # 再把目标 session 设为活跃
            conn.execute(
                """
                UPDATE agent_sessions SET is_active = 1, last_used_at = ?
                WHERE agent_id = ? AND session_id = ?
                """,
                (now, agent_id, session_id),
            )
            conn.commit()
            conn.close()
        except Exception as e:
            _log.warning("AgentSessionDAO.set_active_session failed: %s", e)


class AgentPersonalityDAO:
    """Agent 性格设定 DAO。"""

    @staticmethod
    def get_personality(agent_id: str) -> dict[str, str]:
        try:
            conn = get_connection()
            cur = conn.execute(
                "SELECT personality, catchphrases, memes, backtalk_intensity FROM agent_personality WHERE agent_id = ?",
                (agent_id,),
            )
            row = cur.fetchone()
            conn.close()
            if row:
                return {
                    "personality": row[0] or "",
                    "catchphrases": row[1] or "",
                    "memes": row[2] or "",
                    "backtalk_intensity": str(row[3]) if row[3] is not None else "0",
                }
        except Exception as e:
            _log.warning("AgentPersonalityDAO.get_personality(%s) failed: %s", agent_id, e)
        return {"personality": "", "catchphrases": "", "memes": "", "backtalk_intensity": "0"}

    @staticmethod
    def upsert_personality(
        agent_id: str,
        personality: str = "",
        catchphrases: str = "",
        memes: str = "",
        backtalk_intensity: int = 0,
    ) -> None:
        try:
            conn = get_connection()
            conn.execute(
                """
                INSERT INTO agent_personality (agent_id, personality, catchphrases, memes, backtalk_intensity)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(agent_id) DO UPDATE SET
                    personality        = excluded.personality,
                    catchphrases       = excluded.catchphrases,
                    memes              = excluded.memes,
                    backtalk_intensity = excluded.backtalk_intensity
                """,
                (agent_id, personality, catchphrases, memes, backtalk_intensity),
            )
            conn.commit()
            conn.close()
        except Exception as e:
            _log.warning("AgentPersonalityDAO.upsert_personality(%s) failed: %s", agent_id, e)
