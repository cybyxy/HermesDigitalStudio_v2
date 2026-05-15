"""模型调用成本服务 — 记录 LLM 调用统计并提供成本估算。"""

from __future__ import annotations

import logging
from typing import ClassVar

_log = logging.getLogger(__name__)


class ModelCostService:
    """模型调用成本追踪服务（单例）。

    记录每次 LLM 调用并计算成本估算。
    费率基于 OpenAI 标准定价，本地模型免费。
    """

    # 费率表: (input $/1M tokens, output $/1M tokens)
    RATES: ClassVar[dict[str, tuple[float, float]]] = {
        "local":   (0.0,   0.0),
        "small":   (0.15,  0.60),
        "medium":  (2.50,  10.0),
        "large":   (5.00,  15.0),
    }

    _instance: ModelCostService | None = None

    @staticmethod
    def _cost_for_tokens(tier: str, prompt_tokens: int, completion_tokens: int) -> float:
        """根据 tier 和 token 数计算费用。"""
        rates = ModelCostService.RATES.get(tier, (0, 0))
        input_cost = prompt_tokens * rates[0] / 1_000_000
        output_cost = completion_tokens * rates[1] / 1_000_000
        return round(input_cost + output_cost, 4)

    def record_call(
        self,
        agent_id: str,
        provider: str,
        model: str,
        routing_tier: str,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        cached: bool = False,
        error: str | None = None,
    ) -> None:
        """记录一次 LLM 调用（非关键路径，失败静默）。"""
        try:
            from backend.db.model_cost import ModelCostDAO
            ModelCostDAO.record(
                agent_id=agent_id,
                provider=provider,
                model=model,
                routing_tier=routing_tier,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                cached=1 if cached else 0,
                error=error,
            )
        except Exception as e:
            _log.debug("ModelCostService.record_call(%s) failed: %s", agent_id, e)

    def get_stats(self, agent_id: str, period_days: int = 7) -> dict:
        """获取指定 agent 的成本统计（含费用估算）。"""
        from backend.db.model_cost import ModelCostDAO
        stats = ModelCostDAO.get_stats(agent_id, period_days)

        # 用 DAO 返回的 raw 数据重新查询以计算费用
        # 直接使用 DAO 层面计算
        from backend.db.connection import get_connection
        import time as _time
        conn = get_connection()
        cutoff = _time.time() - period_days * 86400.0
        estimated = 0.0
        total_calls = 0
        total_tokens = 0
        by_tier: dict[str, int] = {}
        by_provider: dict[str, int] = {}

        try:
            rows = conn.execute(
                """SELECT routing_tier, provider,
                          SUM(prompt_tokens), SUM(completion_tokens), COUNT(*)
                   FROM model_cost_log
                   WHERE agent_id = ? AND timestamp >= ?
                   GROUP BY routing_tier, provider""",
                (agent_id, cutoff),
            ).fetchall()
            conn.close()

            for row in rows:
                tier = row[0]
                prov = row[1]
                pt = row[2] or 0
                ct = row[3] or 0
                count = row[4] or 0
                by_tier[tier] = by_tier.get(tier, 0) + count
                by_provider[prov] = by_provider.get(prov, 0) + count
                total_tokens += pt + ct
                total_calls += count
                estimated += self._cost_for_tokens(tier, pt, ct)
        except Exception as e:
            _log.debug("ModelCostService.get_stats(%s) failed: %s", agent_id, e)
            try:
                conn.close()
            except Exception:
                pass

        return {
            "total_calls": total_calls,
            "by_tier": by_tier,
            "by_provider": by_provider,
            "total_tokens": total_tokens,
            "estimated_cost": round(estimated, 4),
            "period_days": period_days,
        }

    def get_global_stats(self, period_days: int = 7) -> dict:
        """获取所有 agent 的聚合成本统计。"""
        from backend.db.model_cost import ModelCostDAO
        stats = ModelCostDAO.get_global_stats(period_days)

        from backend.db.connection import get_connection
        import time as _time
        conn = get_connection()
        cutoff = _time.time() - period_days * 86400.0
        estimated = 0.0
        total_calls = 0
        total_tokens = 0
        by_tier: dict[str, int] = {}
        by_provider: dict[str, int] = {}

        try:
            rows = conn.execute(
                """SELECT routing_tier, provider,
                          SUM(prompt_tokens), SUM(completion_tokens), COUNT(*)
                   FROM model_cost_log
                   WHERE timestamp >= ?
                   GROUP BY routing_tier, provider""",
                (cutoff,),
            ).fetchall()
            conn.close()

            for row in rows:
                tier = row[0]
                prov = row[1]
                pt = row[2] or 0
                ct = row[3] or 0
                count = row[4] or 0
                by_tier[tier] = by_tier.get(tier, 0) + count
                by_provider[prov] = by_provider.get(prov, 0) + count
                total_tokens += pt + ct
                total_calls += count
                estimated += self._cost_for_tokens(tier, pt, ct)
        except Exception as e:
            _log.debug("ModelCostService.get_global_stats failed: %s", e)
            try:
                conn.close()
            except Exception:
                pass

        return {
            "total_calls": total_calls,
            "by_tier": by_tier,
            "by_provider": by_provider,
            "total_tokens": total_tokens,
            "estimated_cost": round(estimated, 4),
            "period_days": period_days,
        }


# ── 单例 ─────────────────────────────────────────────────────────────

_cost_service: ModelCostService | None = None


def get_cost_service() -> ModelCostService:
    """获取 ModelCostService 全局单例。"""
    global _cost_service
    if _cost_service is None:
        _cost_service = ModelCostService()
    return _cost_service
