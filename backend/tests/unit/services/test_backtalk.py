"""测试 顶嘴引擎 — 触发检测、关键词匹配、强度枚举。"""
from __future__ import annotations

from backend.services.backtalk import (
    BacktalkEngine,
    BacktalkIntensity,
    BacktalkTrigger,
    BacktalkResponse,
    AuditResult,
    TriggerType,
)


class TestBacktalkIntensity:
    """BacktalkIntensity 枚举验证。"""

    def test_enum_values(self):
        assert BacktalkIntensity.SILENT.value == 0
        assert BacktalkIntensity.GENTLE.value == 1
        assert BacktalkIntensity.HUMOROUS.value == 2
        assert BacktalkIntensity.DIRECT.value == 3

    def test_intensity_labels(self):
        assert BacktalkEngine.INTENSITY_LABELS[0] == "silent"
        assert BacktalkEngine.INTENSITY_LABELS[3] == "direct"


class TestTriggerType:
    """TriggerType 常量验证。"""

    def test_trigger_types(self):
        assert TriggerType.UNREASONABLE_REQUEST == "unreasonable_request"
        assert TriggerType.REPEATED_MISTAKE == "repeated_mistake"
        assert TriggerType.DIFFERENT_OPINION == "different_opinion"


class TestBacktalkTrigger:
    """BacktalkTrigger dataclass 测试。"""

    def test_create_trigger(self):
        t = BacktalkTrigger(
            trigger_type=TriggerType.UNREASONABLE_REQUEST,
            confidence=0.85,
            evidence="用户说：你怎么连这个都不知道",
            suggested_action="gentle_correction",
        )
        assert t.trigger_type == "unreasonable_request"
        assert t.confidence == 0.85

    def test_default_suggested_action(self):
        t = BacktalkTrigger(
            trigger_type=TriggerType.DIFFERENT_OPINION,
            confidence=0.5,
            evidence="用户不同意建议",
        )
        assert t.suggested_action == ""


class TestBacktalkResponse:
    """BacktalkResponse dataclass 测试。"""

    def test_create_response(self):
        r = BacktalkResponse(
            content="建议您再考虑一下",
            intensity=BacktalkIntensity.GENTLE,
            trigger_type=TriggerType.DIFFERENT_OPINION,
            should_intercept=True,
        )
        assert r.content == "建议您再考虑一下"
        assert r.intensity == BacktalkIntensity.GENTLE
        assert r.should_intercept is True

    def test_default_should_intercept(self):
        r = BacktalkResponse(
            content="ok",
            intensity=BacktalkIntensity.SILENT,
            trigger_type=TriggerType.UNREASONABLE_REQUEST,
        )
        assert r.should_intercept is False


class TestAuditResult:
    """AuditResult dataclass 测试。"""

    def test_consistent_agent(self):
        r = AuditResult(
            is_consistent=True,
            inconsistencies=[],
            recommendations=[],
        )
        assert r.is_consistent
        assert len(r.inconsistencies) == 0

    def test_inconsistent_agent(self):
        r = AuditResult(
            is_consistent=False,
            inconsistencies=["设定 A 与设定 B 矛盾"],
            recommendations=["建议统一语气风格"],
        )
        assert not r.is_consistent
        assert len(r.recommendations) == 1


class TestDetectTriggers:
    """detect_triggers 纯文本检测测试（无需 LLM）。"""

    def test_unreasonable_keyword_triggers(self):
        engine = BacktalkEngine()
        triggers = engine.detect_triggers(
            user_text="你怎么连这个都不知道，你不是AI吗？",
            history_snippet="",
            agent_personality={},
        )
        assert len(triggers) > 0
        assert any(t.trigger_type == TriggerType.UNREASONABLE_REQUEST for t in triggers)

    def test_no_triggers_for_normal_text(self):
        engine = BacktalkEngine()
        triggers = engine.detect_triggers(
            user_text="请帮我写一个排序算法",
            history_snippet="",
            agent_personality={},
        )
        assert len(triggers) == 0

    def test_empty_text_no_triggers(self):
        engine = BacktalkEngine()
        triggers = engine.detect_triggers(
            user_text="",
            history_snippet="",
            agent_personality={},
        )
        assert len(triggers) == 0

    def test_single_keyword_triggers(self):
        """直接使用关键词表中的任意一个词应触发。"""
        engine = BacktalkEngine()
        triggers = engine.detect_triggers(
            user_text="你在撒谎",
            history_snippet="",
            agent_personality={},
        )
        assert len(triggers) > 0
        assert any(t.trigger_type == TriggerType.UNREASONABLE_REQUEST for t in triggers)

    def test_trigger_confidence_range(self):
        engine = BacktalkEngine()
        triggers = engine.detect_triggers(
            user_text="你怎么这么笨，什么都不懂",
            history_snippet="",
            agent_personality={},
        )
        for t in triggers:
            assert 0.0 <= t.confidence <= 1.0


class TestUnreasonableKeywords:
    """不合理关键词表验证。"""

    def test_keywords_non_empty(self):
        assert len(BacktalkEngine.UNREASONABLE_KEYWORDS) > 0

    def test_keywords_match_trigger(self):
        engine = BacktalkEngine()
        for keyword in BacktalkEngine.UNREASONABLE_KEYWORDS[:3]:
            triggers = engine.detect_triggers(
                user_text=keyword,
                history_snippet="",
                agent_personality={},
            )
            assert len(triggers) > 0, f"Keyword '{keyword}' should trigger"


class TestBacktalkAuditInterval:
    """审计间隔常量。"""

    def test_audit_interval(self):
        assert BacktalkEngine.AUDIT_INTERVAL > 0
        assert BacktalkEngine.AUDIT_INTERVAL == 50
