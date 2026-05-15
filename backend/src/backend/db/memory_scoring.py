"""记忆评分 DAO — 评分元数据的持久化层。

在 HermesDigitalStudio.db 中维护 ``memory_scoring_meta`` 表，
记录每条记忆的评分相关元数据（创建时间、来源、增强次数、访问次数等），
支持记忆评分引擎的查询和淘汰操作。

记忆的实际内容存储在 MemOS (Qdrant) 中，本表仅存储评分元数据。
"""

from __future__ import annotations

import logging
import sqlite3
import time
from typing import Any, Optional, Sequence

_log = logging.getLogger(__name__)


class MemoryScoringDAO:
    """记忆评分元数据的 DAL（数据访问层）。

    采用静态方法 + get_connection() 模式，与现有 DAO（如 AgentPersonalityDAO）保持一致。
    """

    @staticmethod
    def ensure_schema(conn: Optional[sqlite3.Connection] = None) -> None:
        """创建记忆评分元数据表（幂等操作）。"""
        do_close = conn is None
        if conn is None:
            from backend.db.connection import get_connection
            conn = get_connection()

        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS memory_scoring_meta (
                    id              TEXT PRIMARY KEY,
                    agent_id        TEXT NOT NULL,
                    content_hash    TEXT NOT NULL,
                    content_snippet TEXT DEFAULT '',
                    source          TEXT NOT NULL DEFAULT '对话提取',
                    created_at      REAL NOT NULL,
                    reinforcement_count INTEGER DEFAULT 0,
                    access_count    INTEGER DEFAULT 0,
                    importance_score REAL DEFAULT 0.0,
                    updated_at      REAL NOT NULL,
                    FOREIGN KEY (agent_id) REFERENCES agent_avatars(agent_id) ON DELETE CASCADE
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_scoring_meta_agent
                ON memory_scoring_meta(agent_id, importance_score DESC)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_scoring_meta_hash
                ON memory_scoring_meta(agent_id, content_hash)
            """)
            conn.commit()
        finally:
            if do_close:
                try:
                    conn.close()
                except Exception:
                    pass

    @staticmethod
    def get_all_meta(agent_id: str) -> list[sqlite3.Row]:
        """获取指定 Agent 的所有记忆评分元数据，按评分降序。"""
        from backend.db.connection import get_connection
        conn = get_connection()
        try:
            return conn.execute(
                "SELECT * FROM memory_scoring_meta WHERE agent_id = ? "
                "ORDER BY importance_score DESC",
                (agent_id,),
            ).fetchall()
        except sqlite3.OperationalError:
            return []
        finally:
            conn.close()

    @staticmethod
    def get_count(agent_id: str) -> int:
        """获取指定 Agent 的记忆总数。"""
        from backend.db.connection import get_connection
        conn = get_connection()
        try:
            row = conn.execute(
                "SELECT COUNT(*) FROM memory_scoring_meta WHERE agent_id = ?",
                (agent_id,),
            ).fetchone()
            return row[0] if row else 0
        except sqlite3.OperationalError:
            return 0
        finally:
            conn.close()

    @staticmethod
    def upsert_meta(
        meta_id: str,
        agent_id: str,
        content_hash: str,
        content_snippet: str = "",
        source: str = "对话提取",
        reinforcement_count: int = 0,
        access_count: int = 0,
        importance_score: float = 0.0,
    ) -> None:
        """插入或更新一条记忆评分元数据。"""
        from backend.db.connection import get_connection
        conn = get_connection()
        now = time.time()
        try:
            conn.execute(
                """INSERT INTO memory_scoring_meta
                   (id, agent_id, content_hash, content_snippet, source,
                    created_at, reinforcement_count, access_count,
                    importance_score, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(id) DO UPDATE SET
                    reinforcement_count=excluded.reinforcement_count,
                    access_count=excluded.access_count,
                    importance_score=excluded.importance_score,
                    updated_at=excluded.updated_at""",
                (meta_id, agent_id, content_hash, content_snippet[:200], source,
                 now, reinforcement_count, access_count, importance_score, now),
            )
            conn.commit()
        except Exception as e:
            _log.debug("memory_scoring: upsert_meta failed: %s", e)
        finally:
            conn.close()

    @staticmethod
    def update_score(meta_id: str, importance_score: float) -> None:
        """更新单条记忆的评分。"""
        from backend.db.connection import get_connection
        conn = get_connection()
        now = time.time()
        try:
            conn.execute(
                "UPDATE memory_scoring_meta SET importance_score = ?, updated_at = ? WHERE id = ?",
                (importance_score, now, meta_id),
            )
            conn.commit()
        except Exception as e:
            _log.debug("memory_scoring: update_score failed: %s", e)
        finally:
            conn.close()

    @staticmethod
    def increment_access(meta_id: str) -> None:
        """增加一条记忆的访问计数。"""
        from backend.db.connection import get_connection
        conn = get_connection()
        now = time.time()
        try:
            conn.execute(
                "UPDATE memory_scoring_meta SET access_count = access_count + 1, updated_at = ? WHERE id = ?",
                (now, meta_id),
            )
            conn.commit()
        except Exception as e:
            _log.debug("memory_scoring: increment_access failed: %s", e)
        finally:
            conn.close()

    @staticmethod
    def delete_meta(meta_ids: list[str]) -> int:
        """批量删除记忆评分元数据，返回删除数量。"""
        if not meta_ids:
            return 0
        from backend.db.connection import get_connection
        conn = get_connection()
        try:
            placeholders = ",".join("?" * len(meta_ids))
            cursor = conn.execute(
                f"DELETE FROM memory_scoring_meta WHERE id IN ({placeholders})",
                meta_ids,
            )
            conn.commit()
            return cursor.rowcount
        except Exception as e:
            _log.debug("memory_scoring: delete_meta failed: %s", e)
            return 0
        finally:
            conn.close()

    @staticmethod
    def get_lowest_scored(agent_id: str, limit: int = 10) -> list[sqlite3.Row]:
        """获取评分最低的 N 条记忆（用于淘汰建议）。"""
        from backend.db.connection import get_connection
        conn = get_connection()
        try:
            return conn.execute(
                "SELECT * FROM memory_scoring_meta WHERE agent_id = ? "
                "ORDER BY importance_score ASC LIMIT ?",
                (agent_id, limit),
            ).fetchall()
        except sqlite3.OperationalError:
            return []
        finally:
            conn.close()
