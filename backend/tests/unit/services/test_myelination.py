"""测试 髓鞘化引擎 — 状态机、阶段推进、dataclass 验证。"""
from __future__ import annotations

import time

from backend.services.myelination import (
    MyelinationStage,
    MyelinationEntry,
    MyelinationEngine,
)


class TestMyelinationStage:
    """MyelinationStage 枚举值验证。"""

    def test_stage_order(self):
        assert MyelinationStage.NOVEL < MyelinationStage.LEARNING
        assert MyelinationStage.LEARNING < MyelinationStage.CONSOLIDATING
        assert MyelinationStage.CONSOLIDATING < MyelinationStage.INSTINCT

    def test_stage_values(self):
        assert MyelinationStage.NOVEL.value == 0
        assert MyelinationStage.LEARNING.value == 1
        assert MyelinationStage.CONSOLIDATING.value == 2
        assert MyelinationStage.INSTINCT.value == 3

    def test_stage_name_to_lower(self):
        assert MyelinationStage.INSTINCT.name.lower() == "instinct"
        assert MyelinationStage.NOVEL.name.lower() == "novel"


class TestMyelinationEntry:
    """MyelinationEntry dataclass 测试。"""

    def test_create_entry(self):
        now = time.time()
        entry = MyelinationEntry(
            key="hello_zh",
            stage=MyelinationStage.LEARNING,
            access_count=2,
            first_access=now - 3600,
            last_access=now,
            cached_response="你好！",
            confidence=0.85,
        )
        assert entry.key == "hello_zh"
        assert entry.stage == MyelinationStage.LEARNING
        assert entry.access_count == 2
        assert entry.confidence == 0.85


class TestMyelinationEngineConstants:
    """引擎级常量验证。"""

    def test_stage_thresholds_progressive(self):
        t = MyelinationEngine.STAGE_THRESHOLDS
        assert t["novel_to_learning"] >= 1
        assert t["learning_to_consolidating"] >= t["novel_to_learning"]
        assert t["consolidating_to_instinct"] >= t["learning_to_consolidating"]

    def test_degrade_threshold_is_7_days(self):
        assert MyelinationEngine.DEGRADE_THRESHOLD_SECONDS == 7 * 86400

    def test_cache_ttl_is_1_day(self):
        assert MyelinationEngine.CACHE_TTL_SECONDS == 86400

    def test_max_cached_per_agent(self):
        assert MyelinationEngine.MAX_CACHED_PER_AGENT == 200

    def test_cache_hit_rate_threshold(self):
        assert 0.0 <= MyelinationEngine.CACHE_HIT_RATE_THRESHOLD <= 1.0
