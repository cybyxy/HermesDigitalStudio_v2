"""测试 模型路由 — 隐私检测、复杂度评估、路由决策逻辑。"""
from __future__ import annotations

from backend.services.model_router import (
    ModelRouter,
    RoutingDecision,
)


class TestRoutingDecision:
    """RoutingDecision dataclass 验证。"""

    def test_create_decision(self):
        d = RoutingDecision(
            tier="small",
            model="gpt-4o-mini",
            provider="openai",
            reason="low complexity",
            privacy_sensitive=False,
        )
        assert d.tier == "small"
        assert d.model == "gpt-4o-mini"
        assert d.provider == "openai"
        assert not d.privacy_sensitive

    def test_privacy_sensitive_default_false(self):
        d = RoutingDecision(
            tier="medium",
            model="gpt-4o",
            provider="openai",
            reason="medium complexity",
        )
        assert d.privacy_sensitive is False


class TestPrivacyDetection:
    """has_privacy_sensitive_content 静态方法测试。"""

    def test_sensitive_zh(self):
        assert ModelRouter.has_privacy_sensitive_content("我的身份证号是110101199001011234")

    def test_sensitive_en(self):
        assert ModelRouter.has_privacy_sensitive_content("my password is abc123")

    def test_sensitive_token(self):
        assert ModelRouter.has_privacy_sensitive_content("please use this api_key: sk-abc123")

    def test_not_sensitive_normal(self):
        assert not ModelRouter.has_privacy_sensitive_content("今天天气怎么样")

    def test_not_sensitive_code(self):
        assert not ModelRouter.has_privacy_sensitive_content("写一个 Python 函数计算斐波那契数列")

    def test_empty_text(self):
        assert not ModelRouter.has_privacy_sensitive_content("")


class TestComplexityAssessment:
    """assess_complexity 静态方法测试。

    计分规则：每个 COMPLEXITY_KEYWORDS 匹配 +0.1，
    加上 len(text)/50 的长度分（上限 1.0）。
    """

    def test_complex_zh_scores_above_simple(self):
        """复杂问题得分应显著高于简单问题。"""
        simple_score = ModelRouter.assess_complexity("你好")
        complex_score = ModelRouter.assess_complexity("分析分布式系统的架构设计并评估性能瓶颈")
        assert complex_score > simple_score

    def test_complex_en_scores_above_simple(self):
        simple_score = ModelRouter.assess_complexity("hi")
        complex_score = ModelRouter.assess_complexity("Please analyze the system design and optimize the architecture")
        assert complex_score > simple_score

    def test_simple_returns_low(self):
        score = ModelRouter.assess_complexity("你好")
        assert score <= ModelRouter.COMPLEXITY_LOW + 0.05  # 允许长度分

    def test_medium_returns_between(self):
        score = ModelRouter.assess_complexity("帮我解释一下什么是递归")
        assert 0.0 <= score <= 1.0

    def test_score_increases_with_keywords(self):
        one_kw = ModelRouter.assess_complexity("分析一下")
        three_kw = ModelRouter.assess_complexity("分析设计评估这个问题")
        assert three_kw > one_kw

    def test_empty_text(self):
        score = ModelRouter.assess_complexity("")
        assert score == 0.0


class TestRoute:
    """route 静态方法集成测试。"""

    def test_route_privacy_to_local(self):
        decision = ModelRouter.route("agent_1", "我的密码是123456")
        assert decision.tier == "local"
        assert decision.privacy_sensitive is True

    def test_route_simple_to_small(self):
        decision = ModelRouter.route("agent_1", "你好")
        assert decision.tier in ("local", "small")

    def test_route_complex_to_large(self):
        long_complex = "分析 " * 20 + "设计架构" + "优化重构"
        decision = ModelRouter.route("agent_1", long_complex)
        assert decision.tier in ("medium", "large")

    def test_route_returns_valid_decision(self):
        decision = ModelRouter.route("agent_1", "帮我写一个排序函数")
        assert decision.tier in ("local", "small", "medium", "large")
        assert decision.model
        assert decision.provider
        assert decision.reason
