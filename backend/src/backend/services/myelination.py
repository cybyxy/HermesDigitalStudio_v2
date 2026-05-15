"""髓鞘化引擎 — 高频知识路径固化为本能反应的三阶段状态机。"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from enum import IntEnum
from typing import ClassVar

_log = logging.getLogger(__name__)


class MyelinationStage(IntEnum):
    NOVEL = 0
    LEARNING = 1
    CONSOLIDATING = 2
    INSTINCT = 3


@dataclass
class MyelinationEntry:
    key: str
    stage: MyelinationStage
    access_count: int
    first_access: float
    last_access: float
    cached_response: str
    confidence: float


class MyelinationEngine:
    """三阶段状态机：NOVEL → LEARNING → CONSOLIDATING → INSTINCT"""

    STAGE_THRESHOLDS: ClassVar[dict[str, int]] = {
        "novel_to_learning": 1,
        "learning_to_consolidating": 2,
        "consolidating_to_instinct": 4,
    }

    DEGRADE_THRESHOLD_SECONDS: ClassVar[int] = 7 * 86400  # 7 天
    CACHE_TTL_SECONDS: ClassVar[int] = 86400              # 24 小时
    MAX_CACHED_PER_AGENT: ClassVar[int] = 200
    CACHE_HIT_RATE_THRESHOLD: ClassVar[float] = 0.9

    # 调用次数计数器（为 get_stats 准备）
    _llm_calls_saved: dict[str, int] = {}
    _tokens_saved: dict[str, int] = {}

    async def get_path_stage(self, agent_id: str, key: str) -> str:
        """查询知识路径当前阶段。"""
        from backend.db.myelination import MyelinationDAO
        entry = MyelinationDAO.get(agent_id, key)
        if entry:
            return MyelinationStage(entry["stage"]).name.lower()
        return MyelinationStage.NOVEL.name.lower()

    async def record_access(self, agent_id: str, key: str,
                            query_text: str = "") -> MyelinationEntry:
        """记录一次访问，自动推进阶段。"""
        from backend.db.myelination import MyelinationDAO

        now = time.time()
        existing = MyelinationDAO.get(agent_id, key)

        if existing:
            new_count = existing["access_count"] + 1
            new_stage = existing["stage"]

            # 自动推进
            if new_stage < MyelinationStage.LEARNING and new_count >= self.STAGE_THRESHOLDS["novel_to_learning"]:
                new_stage = MyelinationStage.LEARNING
            if new_stage < MyelinationStage.CONSOLIDATING and new_count >= self.STAGE_THRESHOLDS["learning_to_consolidating"]:
                new_stage = MyelinationStage.CONSOLIDATING
            if new_stage < MyelinationStage.INSTINCT and new_count >= self.STAGE_THRESHOLDS["consolidating_to_instinct"]:
                new_stage = MyelinationStage.INSTINCT

            entry_data = {
                "key": key,
                "stage": new_stage,
                "access_count": new_count,
                "first_access": existing["first_access"],
                "last_access": now,
                "cached_response": existing.get("cached_response", ""),
                "confidence": existing.get("confidence", 0.0),
            }
        else:
            entry_data = {
                "key": key,
                "stage": MyelinationStage.NOVEL,
                "access_count": 1,
                "first_access": now,
                "last_access": now,
                "cached_response": "",
                "confidence": 0.0,
            }

        MyelinationDAO.upsert(agent_id, entry_data)

        return MyelinationEntry(
            key=key,
            stage=MyelinationStage(entry_data["stage"]),
            access_count=entry_data["access_count"],
            first_access=entry_data["first_access"],
            last_access=entry_data["last_access"],
            cached_response=entry_data["cached_response"],
            confidence=entry_data["confidence"],
        )

    async def get_cache(self, agent_id: str, key: str) -> str | None:
        """获取 instinct 阶段的缓存答案。仅 stage >= CONSOLIDATING 且 TTL 有效。"""
        from backend.db.myelination import MyelinationDAO

        entry = MyelinationDAO.get(agent_id, key)
        if not entry:
            return None

        stage = entry["stage"]
        if stage < MyelinationStage.CONSOLIDATING:
            return None

        # TTL 检查
        now = time.time()
        if now - entry["last_access"] > self.CACHE_TTL_SECONDS:
            return None

        cached = entry.get("cached_response", "")
        if cached:
            # 统计节省的调用
            self._llm_calls_saved[agent_id] = self._llm_calls_saved.get(agent_id, 0) + 1
            self._tokens_saved[agent_id] = self._tokens_saved.get(agent_id, 0) + len(cached) // 2

        return cached or None

    async def set_cache(self, agent_id: str, key: str, answer: str) -> None:
        """设置缓存答案。"""
        from backend.db.myelination import MyelinationDAO

        existing = MyelinationDAO.get(agent_id, key)
        if existing:
            existing["cached_response"] = answer
            MyelinationDAO.upsert(agent_id, existing)
        else:
            MyelinationDAO.upsert(agent_id, {
                "key": key,
                "stage": MyelinationStage.LEARNING,
                "access_count": 1,
                "first_access": time.time(),
                "last_access": time.time(),
                "cached_response": answer,
                "confidence": 0.5,
            })

    async def invalidate_cache(self, agent_id: str, key: str) -> None:
        """使指定路径的缓存失效。"""
        from backend.db.myelination import MyelinationDAO
        MyelinationDAO.delete(agent_id, key)

    async def run_maintenance(self, agent_id: str) -> int:
        """维护循环：降级过期路径、清理低质量条目。"""
        from backend.db.myelination import MyelinationDAO

        entries = MyelinationDAO.list_all(agent_id)
        now = time.time()
        cleaned = 0

        for entry in entries:
            # 7 天无访问 → 降级
            if now - entry["last_access"] > self.DEGRADE_THRESHOLD_SECONDS:
                if entry["stage"] > MyelinationStage.LEARNING:
                    entry["stage"] = max(entry["stage"] - 1, MyelinationStage.LEARNING)
                    MyelinationDAO.upsert(agent_id, entry)
                    cleaned += 1

        # 如果条目超过上限，删除最少访问的
        total = MyelinationDAO.count(agent_id)
        if total > self.MAX_CACHED_PER_AGENT:
            removed = MyelinationDAO.prune_oldest(agent_id, total - self.MAX_CACHED_PER_AGENT + 50)
            cleaned += removed

        if cleaned:
            _log.info("myelination: agent=%s maintenance cleaned %d entries", agent_id, cleaned)

        return cleaned

    async def get_stats(self, agent_id: str) -> dict:
        """获取统计信息。"""
        from backend.db.myelination import MyelinationDAO

        entries = MyelinationDAO.list_all(agent_id)
        total = len(entries)
        by_stage: dict[str, int] = {s.name.lower(): 0 for s in MyelinationStage}

        for entry in entries:
            try:
                stage_name = MyelinationStage(entry["stage"]).name.lower()
                by_stage[stage_name] = by_stage.get(stage_name, 0) + 1
            except (ValueError, KeyError):
                pass

        return {
            "total_paths": total,
            "by_stage": by_stage,
            "cache_entry_count": total,
            "llm_calls_saved": self._llm_calls_saved.get(agent_id, 0),
            "tokens_saved": self._tokens_saved.get(agent_id, 0),
        }