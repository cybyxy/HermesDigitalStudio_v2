"""髓鞘化 DAO — per-agent 知识路径存储。"""

from __future__ import annotations

import logging
import time
from typing import Any

from backend.db.connection import get_connection

_log = logging.getLogger(__name__)


class MyelinationDAO:
    """髓鞘化数据访问对象。

    每个 Agent 一个独立的 mpath_{agent_id} 表。
    """

    _META_TABLE_INITIALIZED = False

    @staticmethod
    def _table_name(agent_id: str) -> str:
        """安全表名 — 移除特殊字符。"""
        safe = "".join(c for c in agent_id if c.isalnum() or c in "-_")
        return f"mpath_{safe}"

    @staticmethod
    def ensure_meta_table(conn: Any) -> None:
        """确保元表存在（记录哪些 Agent 有髓鞘化数据）。"""
        if MyelinationDAO._META_TABLE_INITIALIZED:
            return
        conn.execute("""
            CREATE TABLE IF NOT EXISTS mpath_meta (
                agent_id TEXT PRIMARY KEY,
                created_at REAL NOT NULL
            )
        """)
        conn.commit()
        MyelinationDAO._META_TABLE_INITIALIZED = True

    @staticmethod
    def ensure_schema(conn: Any, agent_id: str) -> None:
        """确保 agent 的髓鞘化表存在。"""
        table = MyelinationDAO._table_name(agent_id)
        conn.execute(f"""
            CREATE TABLE IF NOT EXISTS {table} (
                key              TEXT PRIMARY KEY,
                stage            INTEGER NOT NULL DEFAULT 0,
                access_count     INTEGER NOT NULL DEFAULT 0,
                first_access     REAL NOT NULL,
                last_access      REAL NOT NULL,
                cached_response  TEXT NOT NULL DEFAULT '',
                confidence       REAL NOT NULL DEFAULT 0.0
            )
        """)
        conn.execute(
            "INSERT OR IGNORE INTO mpath_meta (agent_id, created_at) VALUES (?, ?)",
            (agent_id, time.time()),
        )
        conn.commit()

    @staticmethod
    def upsert(agent_id: str, entry: dict) -> None:
        try:
            conn = get_connection()
            MyelinationDAO.ensure_schema(conn, agent_id)
            table = MyelinationDAO._table_name(agent_id)
            conn.execute(
                f"""
                INSERT INTO {table} (key, stage, access_count, first_access, last_access, cached_response, confidence)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    stage           = excluded.stage,
                    access_count    = excluded.access_count,
                    last_access     = excluded.last_access,
                    cached_response = excluded.cached_response,
                    confidence      = excluded.confidence
                """,
                (
                    entry["key"],
                    entry.get("stage", 0),
                    entry.get("access_count", 0),
                    entry.get("first_access", time.time()),
                    entry.get("last_access", time.time()),
                    entry.get("cached_response", ""),
                    entry.get("confidence", 0.0),
                ),
            )
            conn.commit()
            conn.close()
        except Exception as e:
            _log.warning("MyelinationDAO.upsert(%s) failed: %s", agent_id, e)

    @staticmethod
    def get(agent_id: str, key: str) -> dict | None:
        try:
            conn = get_connection()
            MyelinationDAO.ensure_schema(conn, agent_id)
            table = MyelinationDAO._table_name(agent_id)
            row = conn.execute(
                f"SELECT key, stage, access_count, first_access, last_access, cached_response, confidence FROM {table} WHERE key = ?",
                (key,),
            ).fetchone()
            conn.close()
            if row:
                return {
                    "key": row[0],
                    "stage": row[1],
                    "access_count": row[2],
                    "first_access": row[3],
                    "last_access": row[4],
                    "cached_response": row[5],
                    "confidence": row[6],
                }
        except Exception as e:
            _log.warning("MyelinationDAO.get(%s) failed: %s", agent_id, e)
        return None

    @staticmethod
    def delete(agent_id: str, key: str) -> None:
        try:
            conn = get_connection()
            table = MyelinationDAO._table_name(agent_id)
            conn.execute(f"DELETE FROM {table} WHERE key = ?", (key,))
            conn.commit()
            conn.close()
        except Exception as e:
            _log.warning("MyelinationDAO.delete(%s) failed: %s", agent_id, e)

    @staticmethod
    def list_all(agent_id: str) -> list[dict]:
        try:
            conn = get_connection()
            MyelinationDAO.ensure_schema(conn, agent_id)
            table = MyelinationDAO._table_name(agent_id)
            rows = conn.execute(
                f"SELECT key, stage, access_count, first_access, last_access, cached_response, confidence FROM {table}"
            ).fetchall()
            conn.close()
            return [
                {
                    "key": r[0],
                    "stage": r[1],
                    "access_count": r[2],
                    "first_access": r[3],
                    "last_access": r[4],
                    "cached_response": r[5],
                    "confidence": r[6],
                }
                for r in rows
            ]
        except Exception as e:
            _log.warning("MyelinationDAO.list_all(%s) failed: %s", agent_id, e)
            return []

    @staticmethod
    def count(agent_id: str) -> int:
        try:
            conn = get_connection()
            table = MyelinationDAO._table_name(agent_id)
            row = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
            conn.close()
            return row[0] if row else 0
        except Exception:
            return 0

    @staticmethod
    def prune_oldest(agent_id: str, limit: int) -> int:
        """删除最旧的 N 条记录。"""
        try:
            conn = get_connection()
            table = MyelinationDAO._table_name(agent_id)
            conn.execute(
                f"DELETE FROM {table} WHERE key IN (SELECT key FROM {table} ORDER BY last_access ASC LIMIT ?)",
                (limit,),
            )
            conn.commit()
            conn.close()
            return limit
        except Exception as e:
            _log.warning("MyelinationDAO.prune_oldest(%s) failed: %s", agent_id, e)
            return 0