"""测试 记忆评分引擎 — 分数计算、冲突检测逻辑。"""
from __future__ import annotations

import time

from backend.services.memory_scoring import (
    _SOURCE_SCORES,
    MemoryScoringEngine,
    _MemoryConflictDetector,
    _CONFLICT_DETECTOR,
)


class TestSourceScores:
    """记忆来源权重常量验证。"""

    def test_source_scores_order(self):
        assert _SOURCE_SCORES["LLM抽取"] >= _SOURCE_SCORES["用户显式"]
        assert _SOURCE_SCORES["用户显式"] >= _SOURCE_SCORES["对话提取"]
        assert _SOURCE_SCORES["对话提取"] >= _SOURCE_SCORES["启动恢复"]


class TestCalculateScore:
    """calculate_score 纯逻辑测试（无需 DB）。"""

    def test_fresh_memory_scores_high(self):
        engine = MemoryScoringEngine()
        entry = {
            "created_at": time.time(),       # 刚创建
            "reinforcement": 5,
            "source": "LLM抽取",
            "access_count": 10,
        }
        score = engine.calculate_score(entry)
        assert score > 0.5
        assert score <= 1.0

    def test_old_memory_scores_low(self):
        engine = MemoryScoringEngine()
        entry = {
            "created_at": time.time() - 180 * 86400,  # 180 天前
            "reinforcement": 0,
            "source": "对话提取",
            "access_count": 0,
        }
        score = engine.calculate_score(entry)
        assert score <= 0.3

    def test_custom_weights(self):
        engine = MemoryScoringEngine(weights={"recency": 1.0, "reinforcement": 0, "source": 0, "access_count": 0})
        entry = {
            "created_at": time.time(),  # 刚创建 → recency 满分
            "reinforcement": 0,
            "source": "对话提取",
            "access_count": 0,
        }
        score = engine.calculate_score(entry)
        assert score >= 0.9  # recency 权重 100% 时近乎满分

    def test_recency_factor(self):
        engine = MemoryScoringEngine()
        r_recent = engine._calc_recency(time.time() - 3600)         # 1 小时前
        r_old = engine._calc_recency(time.time() - 30 * 86400)      # 30 天前
        assert r_recent > r_old


class TestConflictDetection:
    """_MemoryConflictDetector 纯文本检测测试。"""

    def test_detector_zh_negation_conflict(self):
        """是/不是 配对应产生 factual_negation 冲突。"""
        result = _CONFLICT_DETECTOR.detect_pair(
            snippet_a="Python 是动态类型语言",
            snippet_b="Python 不是动态类型语言",
        )
        assert result is not None
        assert result["conflict_type"] == "factual_negation"
        assert result["confidence"] >= 0.3

    def test_detector_same_text_generic_conflict(self):
        """相同文本有完全重叠，产生 generic 冲突（无否定标记但有主题重叠）。"""
        result = _CONFLICT_DETECTOR.detect_pair(
            snippet_a="Python 是动态类型语言",
            snippet_b="Python 是动态类型语言",
        )
        # 有完全重叠但无否定标记 → generic 类型冲突
        assert result is not None
        assert result["conflict_type"] == "generic"

    def test_detector_no_conflict_different_topics(self):
        result = _CONFLICT_DETECTOR.detect_pair(
            snippet_a="Python 是编程语言",
            snippet_b="今天天气不错",
            mem_id_a="m1",
            mem_id_b="m2",
        )
        assert result is None

    def test_detector_short_text_ignored(self):
        """太短的文本不应产生冲突。"""
        result = _CONFLICT_DETECTOR.detect_pair(
            snippet_a="是",
            snippet_b="不是",
        )
        assert result is None

    def test_extract_terms_basic(self):
        """_extract_terms 使用正则提取 >=2 字符的中文/英文词。"""
        detector = _MemoryConflictDetector()
        terms = detector._extract_terms("这是一个测试用例")
        assert len(terms) >= 1


class TestEnhancedConflictDetection:
    """detect_conflicts_enhanced 纯逻辑测试（向量搜索和 LLM 判定）。"""

    def test_enhanced_method_exists(self):
        """确保 MemoryScoringEngine 有增强检测方法。"""
        engine = MemoryScoringEngine()
        assert hasattr(engine, "detect_conflicts_enhanced")
        assert hasattr(engine, "check_write_conflict")
        assert hasattr(engine, "_vector_corroboration")
        assert hasattr(engine, "_llm_conflict_verdict")

    def test_vector_corroboration_empty_input(self):
        """空输入应返回 0 boost。"""
        import asyncio
        engine = MemoryScoringEngine()
        result = asyncio.run(engine._vector_corroboration(
            "test_agent", "", "",
        ))
        assert result == 0.0

    def test_vector_corroboration_max_boost_25(self):
        """boost 值不应超过 0.25。"""
        # 这个测试只校验返回值的上限，不依赖实际的 mos_search
        import asyncio
        engine = MemoryScoringEngine()
        # 空字符串返回 0，不抛异常
        result = asyncio.run(engine._vector_corroboration(
            "test_agent", "test", "test",
        ))
        assert 0.0 <= result <= 0.25

    def test_llm_verdict_conflict_words(self):
        """_llm_conflict_verdict 在 LLM 不可用时的 fallback 行为。"""
        import asyncio
        engine = MemoryScoringEngine()
        # LLM 可能不可用（无 API key），应返回合理默认值
        result = asyncio.run(engine._llm_conflict_verdict(
            "test_agent",
            "用户生日是5月1日",
            "用户生日是6月1日",
        ))
        assert isinstance(result, dict)
        assert "is_conflict" in result
        assert isinstance(result["is_conflict"], bool)

    def test_zh_date_conflict_pair_needs_vector_search(self):
        """同主题不同细节：关键词检测可能因重叠不足而返回 None。
        此场景正是 enhanced 模式设计的初衷（PRD AC-3.4 需向量搜索）。"""
        result = _CONFLICT_DETECTOR.detect_pair(
            snippet_a="用户 生日 是 五月 一日",
            snippet_b="用户 生日 是 六月 一日",
        )
        # 若关键词检测能捕获，应标记为 generic
        if result is not None:
            assert result["conflict_type"] in ("generic", "factual_negation")

    def test_can_do_keyword_conflict(self):
        """能/不能 配对应产生 factual_negation（需有共同词重叠）。"""
        result = _CONFLICT_DETECTOR.detect_pair(
            snippet_a="系统 能 支持 并发",
            snippet_b="系统 不能 支持 并发",
        )
        assert result is not None
        assert result["conflict_type"] == "factual_negation"

    def test_has_no_conflict(self):
        """有/没有 配对应产生 factual_negation（需有共同词）。"""
        result = _CONFLICT_DETECTOR.detect_pair(
            snippet_a="项目 有 设计 资源",
            snippet_b="项目 没有 设计 资源",
        )
        assert result is not None
        assert result["conflict_type"] == "factual_negation"

    def test_negation_boosts_confidence(self):
        """否定标记可使低重叠文本仍达到冲突置信度阈值。"""
        result = _CONFLICT_DETECTOR.detect_pair(
            snippet_a="系统 支持 并发",
            snippet_b="系统 不支持 并发",
        )
        assert result is not None
        assert result["conflict_type"] == "factual_negation"
        assert result["confidence"] >= 0.3

