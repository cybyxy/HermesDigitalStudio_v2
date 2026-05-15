"""记忆相关数据访问对象：压缩映射、会话摘要缓存。

所有对 per-agent 分表 ``smry_{agent_id}`` / ``cmap_{agent_id}`` 的操作须经此类。

采用分表策略：每个 Agent 拥有独立的记忆表，Agent 删除时 DROP TABLE 即可完全清理。
"""

from __future__ import annotations

import logging
import re

from backend.db.connection import get_connection, ensure_agent_memory_tables

_log = logging.getLogger(__name__)

_SAFE_ID_RE = re.compile(r"\W")


def _safe_agent_id(agent_id: str) -> str:
    """将 agent_id 转换为 DB 表名安全形式。"""
    return _SAFE_ID_RE.sub("_", agent_id).strip("_") or "unknown"


# ── SessionSummaryDAO ─────────────────────────────────────────────────────────


class SessionSummaryDAO:
    """会话摘要缓存 DAO — 操作 ``smry_{agent_id}`` 表。

    在 session 结束时将 Agent 的对话摘要写入缓存，供后续 session 的
    ``build_session_startup_context()`` 快速读取。
    """

    @classmethod
    def ensure_table(cls, agent_id: str) -> None:
        """确保 ``smry_{agent_id}`` 表已创建（幂等）。"""
        safid = _safe_agent_id(agent_id)
        conn = get_connection()
        try:
            ensure_agent_memory_tables(agent_id, conn)
        finally:
            conn.close()

    @classmethod
    def save_summary(
        cls,
        agent_id: str,
        session_id: str,
        summary: str,
        token_count: int = 0,
        model: str = "",
    ) -> None:
        """保存或更新会话摘要。"""
        import time

        safid = _safe_agent_id(agent_id)
        conn = get_connection()
        try:
            ensure_agent_memory_tables(agent_id, conn)
            now = time.time()
            conn.execute(
                f"INSERT OR REPLACE INTO smry_{safid} "
                f"(session_id, summary, token_count, generated_at, model) "
                f"VALUES (?, ?, ?, ?, ?)",
                (session_id, summary, token_count, now, model),
            )
            conn.commit()
        except Exception as e:
            _log.warning("SessionSummaryDAO.save_summary(%s) failed: %s", agent_id, e)
        finally:
            conn.close()

    @classmethod
    def get_recent(cls, agent_id: str, n: int = 3) -> list[dict]:
        """获取最近 N 个会话摘要（按时间倒序）。"""
        safid = _safe_agent_id(agent_id)
        conn = get_connection()
        try:
            ensure_agent_memory_tables(agent_id, conn)
            cur = conn.execute(
                f"SELECT session_id, summary, token_count, generated_at, model "
                f"FROM smry_{safid} "
                f"ORDER BY generated_at DESC LIMIT ?",
                (n,),
            )
            rows = cur.fetchall()
            return [
                {
                    "session_id": r[0],
                    "summary": r[1] or "",
                    "token_count": r[2] or 0,
                    "generated_at": r[3],
                    "model": r[4] or "",
                }
                for r in rows
            ]
        except Exception as e:
            _log.debug("SessionSummaryDAO.get_recent(%s) failed (may be first use): %s", agent_id, e)
            return []
        finally:
            conn.close()

    @classmethod
    def get_by_session(cls, agent_id: str, session_id: str) -> dict | None:
        """按 session_id 查询摘要。"""
        safid = _safe_agent_id(agent_id)
        conn = get_connection()
        try:
            ensure_agent_memory_tables(agent_id, conn)
            cur = conn.execute(
                f"SELECT session_id, summary, token_count, generated_at, model "
                f"FROM smry_{safid} WHERE session_id = ?",
                (session_id,),
            )
            row = cur.fetchone()
            if row:
                return {
                    "session_id": row[0],
                    "summary": row[1] or "",
                    "token_count": row[2] or 0,
                    "generated_at": row[3],
                    "model": row[4] or "",
                }
        except Exception:
            pass
        finally:
            conn.close()
        return None


# ── CompressionMapDAO ─────────────────────────────────────────────────────────


class CompressionMapDAO:
    """压缩映射 DAO — 操作 ``cmap_{agent_id}`` 表。

    记录上下文压缩的映射关系，使 Agent 可以通过 session_search tool
    查询被压缩的原始会话记录。
    """

    @classmethod
    def ensure_table(cls, agent_id: str) -> None:
        """确保 ``cmap_{agent_id}`` 表已创建（幂等）。"""
        safid = _safe_agent_id(agent_id)
        conn = get_connection()
        try:
            ensure_agent_memory_tables(agent_id, conn)
        finally:
            conn.close()

    @classmethod
    def record_compression(
        cls,
        agent_id: str,
        compressed_session_id: str,
        original_session_id: str,
        *,
        message_range_start: int | None = None,
        message_range_end: int | None = None,
        summary: str = "",
        key_topics: str = "",
    ) -> None:
        """记录一次上下文压缩的映射关系。"""
        import time

        safid = _safe_agent_id(agent_id)
        conn = get_connection()
        try:
            ensure_agent_memory_tables(agent_id, conn)
            now = time.time()
            conn.execute(
                f"INSERT OR REPLACE INTO cmap_{safid} "
                f"(compressed_session_id, original_session_id, "
                f" message_range_start, message_range_end, "
                f" summary, key_topics, compressed_at) "
                f"VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    compressed_session_id,
                    original_session_id,
                    message_range_start,
                    message_range_end,
                    summary,
                    key_topics,
                    now,
                ),
            )
            conn.commit()
            _log.info(
                "compression map recorded: %s → %s (agent=%s)",
                original_session_id, compressed_session_id, agent_id,
            )
        except Exception as e:
            _log.warning("CompressionMapDAO.record_compression(%s) failed: %s", agent_id, e)
        finally:
            conn.close()

    @classmethod
    def get_by_compressed(
        cls,
        agent_id: str,
        compressed_session_id: str,
    ) -> list[dict]:
        """查询某个压缩后 session 的所有原始会话映射。"""
        safid = _safe_agent_id(agent_id)
        conn = get_connection()
        try:
            ensure_agent_memory_tables(agent_id, conn)
            cur = conn.execute(
                f"SELECT id, compressed_session_id, original_session_id, "
                f"message_range_start, message_range_end, summary, key_topics, compressed_at "
                f"FROM cmap_{safid} "
                f"WHERE compressed_session_id = ? "
                f"ORDER BY compressed_at DESC",
                (compressed_session_id,),
            )
            rows = cur.fetchall()
            return [
                {
                    "id": r[0],
                    "compressed_session_id": r[1],
                    "original_session_id": r[2],
                    "message_range_start": r[3],
                    "message_range_end": r[4],
                    "summary": r[5] or "",
                    "key_topics": r[6] or "",
                    "compressed_at": r[7],
                }
                for r in rows
            ]
        except Exception as e:
            _log.debug("CompressionMapDAO.get_by_compressed(%s) failed: %s", agent_id, e)
            return []
        finally:
            conn.close()

    @classmethod
    def get_compression_chain(
        cls,
        agent_id: str,
        session_id: str,
        max_depth: int = 5,
    ) -> list[dict]:
        """获取 session 的完整压缩链（从当前到最早）。"""
        chain = []
        current = session_id
        visited = set()
        for _ in range(max_depth):
            if current in visited:
                break
            visited.add(current)
            entries = cls.get_by_compressed(agent_id, current)
            if not entries:
                break
            entry = entries[0]  # 取最近的一个
            chain.append(entry)
            current = entry["original_session_id"]
        return chain
