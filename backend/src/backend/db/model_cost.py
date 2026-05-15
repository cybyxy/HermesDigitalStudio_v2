"""模型调用成本追踪 DAO — 记录每次 LLM 调用的 token 消耗和成本信息。"""

from __future__ import annotations

import logging
import sqlite3
import time
from typing import Optional

_log = logging.getLogger(__name__)


class ModelCostDAO:
    """模型调用成本数据访问层。

    表 ``model_cost_log`` 记录每次 LLM 调用的：
    - agent_id, provider, model, routing_tier
    - prompt/ completion token 数
    - 是否缓存命中
    - 时间戳
    """

    _TABLE_INITIALIZED = False

    @staticmethod
    def ensure_schema(conn: Optional[sqlite3.Connection] = None) -> None:
        """创建成本日志表（幂等操作）。"""
        if ModelCostDAO._TABLE_INITIALIZED:
            return
        do_close = conn is None
        if conn is None:
            from backend.db.connection import get_connection
            conn = get_connection()

        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS model_cost_log (
                    id                INTEGER PRIMARY KEY AUTOINCREMENT,
                    agent_id          TEXT NOT NULL,
                    provider          TEXT NOT NULL,
                    model             TEXT NOT NULL,
                    routing_tier      TEXT NOT NULL,
                    prompt_tokens     INTEGER DEFAULT 0,
                    completion_tokens INTEGER DEFAULT 0,
                    cached            INTEGER DEFAULT 0,
                    error             TEXT,
                    timestamp         REAL NOT NULL
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_model_cost_agent
                ON model_cost_log(agent_id, timestamp DESC)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_model_cost_tier
                ON model_cost_log(routing_tier, timestamp DESC)
            """)
            conn.commit()
        finally:
            if do_close:
                try:
                    conn.close()
                except Exception:
                    pass
        ModelCostDAO._TABLE_INITIALIZED = True

    @staticmethod
    def record(
        agent_id: str,
        provider: str,
        model: str,
        routing_tier: str,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        cached: int = 0,
        error: str | None = None,
    ) -> None:
        """记录一次 LLM 调用。"""
        from backend.db.connection import get_connection
        conn = get_connection()
        try:
            conn.execute(
                """INSERT INTO model_cost_log
                   (agent_id, provider, model, routing_tier, prompt_tokens,
                    completion_tokens, cached, error, timestamp)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (agent_id, provider, model, routing_tier,
                 prompt_tokens, completion_tokens, cached, error, time.time()),
            )
            conn.commit()
        except Exception as e:
            _log.debug("ModelCostDAO.record(%s) failed: %s", agent_id, e)
        finally:
            conn.close()

    @staticmethod
    def get_stats(agent_id: str, period_days: int = 7) -> dict:
        """获取指定 agent 在 period_days 内的成本统计。"""
        from backend.db.connection import get_connection
        conn = get_connection()
        cutoff = time.time() - period_days * 86400.0
        try:
            rows = conn.execute(
                """SELECT routing_tier, provider,
                          SUM(prompt_tokens) as total_prompt,
                          SUM(completion_tokens) as total_completion,
                          COUNT(*) as call_count
                   FROM model_cost_log
                   WHERE agent_id = ? AND timestamp >= ?
                   GROUP BY routing_tier, provider""",
                (agent_id, cutoff),
            ).fetchall()
            conn.close()

            if not rows:
                return {
                    "total_calls": 0,
                    "by_tier": {},
                    "by_provider": {},
                    "total_tokens": 0,
                    "estimated_cost": 0.0,
                    "period_days": period_days,
                }
        except Exception as e:
            _log.debug("ModelCostDAO.get_stats(%s) failed: %s", agent_id, e)
            try:
                conn.close()
            except Exception:
                pass
            return {
                "total_calls": 0,
                "by_tier": {},
                "by_provider": {},
                "total_tokens": 0,
                "estimated_cost": 0.0,
                "period_days": period_days,
            }

        by_tier: dict[str, int] = {}
        by_provider: dict[str, int] = {}
        total_tokens = 0

        for row in rows:
            tier = row[0]
            prov = row[1]
            tokens = (row[2] or 0) + (row[3] or 0)
            count = row[4] or 0
            by_tier[tier] = by_tier.get(tier, 0) + count
            by_provider[prov] = by_provider.get(prov, 0) + count
            total_tokens += tokens

        return {
            "total_calls": sum(by_tier.values()),
            "by_tier": by_tier,
            "by_provider": by_provider,
            "total_tokens": total_tokens,
            "estimated_cost": 0.0,  # 由 service 层计算
            "period_days": period_days,
        }

    @staticmethod
    def get_global_stats(period_days: int = 7) -> dict:
        """获取所有 agent 的聚合成本统计。"""
        from backend.db.connection import get_connection
        conn = get_connection()
        cutoff = time.time() - period_days * 86400.0
        try:
            rows = conn.execute(
                """SELECT routing_tier, provider,
                          SUM(prompt_tokens) as total_prompt,
                          SUM(completion_tokens) as total_completion,
                          COUNT(*) as call_count
                   FROM model_cost_log
                   WHERE timestamp >= ?
                   GROUP BY routing_tier, provider""",
                (cutoff,),
            ).fetchall()
            conn.close()

            if not rows:
                return {
                    "total_calls": 0,
                    "by_tier": {},
                    "by_provider": {},
                    "total_tokens": 0,
                    "estimated_cost": 0.0,
                    "period_days": period_days,
                }
        except Exception as e:
            _log.debug("ModelCostDAO.get_global_stats failed: %s", e)
            try:
                conn.close()
            except Exception:
                pass
            return {
                "total_calls": 0,
                "by_tier": {},
                "by_provider": {},
                "total_tokens": 0,
                "estimated_cost": 0.0,
                "period_days": period_days,
            }

        by_tier: dict[str, int] = {}
        by_provider: dict[str, int] = {}
        total_tokens = 0

        for row in rows:
            tier = row[0]
            prov = row[1]
            tokens = (row[2] or 0) + (row[3] or 0)
            count = row[4] or 0
            by_tier[tier] = by_tier.get(tier, 0) + count
            by_provider[prov] = by_provider.get(prov, 0) + count
            total_tokens += tokens

        return {
            "total_calls": sum(by_tier.values()),
            "by_tier": by_tier,
            "by_provider": by_provider,
            "total_tokens": total_tokens,
            "estimated_cost": 0.0,
            "period_days": period_days,
        }

    @staticmethod
    def get_recent(agent_id: str, limit: int = 20) -> list[dict]:
        """获取最近 N 条调用记录。"""
        from backend.db.connection import get_connection
        conn = get_connection()
        try:
            rows = conn.execute(
                """SELECT agent_id, provider, model, routing_tier,
                          prompt_tokens, completion_tokens, cached, error, timestamp
                   FROM model_cost_log
                   WHERE agent_id = ?
                   ORDER BY timestamp DESC
                   LIMIT ?""",
                (agent_id, limit),
            ).fetchall()
            conn.close()
            return [
                {
                    "agent_id": r[0],
                    "provider": r[1],
                    "model": r[2],
                    "routing_tier": r[3],
                    "prompt_tokens": r[4],
                    "completion_tokens": r[5],
                    "cached": bool(r[6]),
                    "error": r[7],
                    "timestamp": r[8],
                }
                for r in rows
            ]
        except Exception as e:
            _log.debug("ModelCostDAO.get_recent(%s) failed: %s", agent_id, e)
            try:
                conn.close()
            except Exception:
                pass
            return []
