"""测试 内心独白引擎 — dataclass 验证、质量评估逻辑。"""
from __future__ import annotations

import time

from backend.services.internal_thoughts import (
    SmallThought,
    ThoughtQuality,
    InternalThoughtsService,
)


class TestSmallThought:
    """SmallThought dataclass 验证。"""

    def test_create_thought(self):
        now = time.time()
        t = SmallThought(
            thought_id="thought_001",
            agent_id="agent_1",
            content="我在想...如果用户问这个问题，我该怎么回答呢？",
            trigger="random_walk",
            confidence=0.75,
            timestamp=now,
        )
        assert t.thought_id == "thought_001"
        assert t.agent_id == "agent_1"
        assert t.trigger == "random_walk"
        assert t.confidence == 0.75

    def test_trigger_values(self):
        # trigger 必须是三类之一: random_walk / emotional / energy
        t1 = SmallThought(
            thought_id="t1", agent_id="a1", content="x",
            trigger="random_walk", confidence=0.5, timestamp=time.time(),
        )
        t2 = SmallThought(
            thought_id="t2", agent_id="a1", content="x",
            trigger="emotional", confidence=0.5, timestamp=time.time(),
        )
        t3 = SmallThought(
            thought_id="t3", agent_id="a1", content="x",
            trigger="energy", confidence=0.5, timestamp=time.time(),
        )
        assert t1.trigger == "random_walk"
        assert t2.trigger == "emotional"
        assert t3.trigger == "energy"


class TestThoughtQuality:
    """ThoughtQuality dataclass 验证。"""

    def test_high_quality(self):
        q = ThoughtQuality(
            is_novel=True,
            is_contextual=True,
            is_coherent=True,
            overall_score=0.9,
        )
        assert q.is_novel
        assert q.is_contextual
        assert q.is_coherent
        assert q.overall_score == 0.9

    def test_low_quality(self):
        q = ThoughtQuality(
            is_novel=False,
            is_contextual=False,
            is_coherent=False,
            overall_score=0.2,
        )
        assert not q.is_novel
        assert q.overall_score == 0.2

    def test_overall_score_range(self):
        q = ThoughtQuality(
            is_novel=True, is_contextual=False, is_coherent=True,
            overall_score=0.5,
        )
        assert 0.0 <= q.overall_score <= 1.0


class TestInternalThoughtsServiceConstants:
    """InternalThoughtsService 常量验证。"""

    def test_trigger_conditions(self):
        c = InternalThoughtsService.TRIGGER_CONDITIONS
        assert c["satiety_low"] > 0
        assert c["satiety_high"] > c["satiety_low"]
        assert 0.0 <= c["trigger_probability"] <= 1.0
        assert 0.0 <= c["min_confidence"] <= 1.0

    def test_max_recent_thoughts(self):
        assert InternalThoughtsService._MAX_RECENT_THOUGHTS > 0


class TestQualityEvaluation:
    """_evaluate_quality 纯逻辑测试。"""

    def test_novel_thought_scores_high(self):
        svc = InternalThoughtsService()
        recent = ["之前想的是 A", "之前想的是 B", "之前想的是 C"]
        q = svc._evaluate_quality("这是一条全新的想法", recent)
        assert q.is_novel
        assert q.overall_score >= 0.3

    def test_repetitive_thought_not_novel(self):
        svc = InternalThoughtsService()
        recent = ["用户问了天气", "一直在下雨"]
        q = svc._evaluate_quality("用户问了天气", recent)
        assert not q.is_novel

    def test_empty_recent_no_repetition(self):
        svc = InternalThoughtsService()
        q = svc._evaluate_quality("一个新的想法", [])
        assert q.is_novel
