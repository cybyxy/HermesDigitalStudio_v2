"""模型路由器 — 多模型智能路由决策引擎。"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import ClassVar

_log = logging.getLogger(__name__)


@dataclass
class RoutingDecision:
    """路由决策结果。"""
    tier: str           # 'local' | 'small' | 'medium' | 'large'
    model: str          # 推荐模型名
    provider: str       # 推荐提供商
    reason: str         # 路由原因
    privacy_sensitive: bool = False


class ModelRouter:
    """多模型智能路由决策引擎。

    根据输入文本的复杂度和隐私内容，自动选择最合适的模型层级。
    """

    PRIVACY_KEYWORDS: ClassVar[set[str]] = {
        "密码", "密钥", "身份证", "手机号", "银行卡", "私钥", "token",
        "password", "secret", "credential", "private key", "api_key",
        "信用卡", "社保", "住址", "身份证号",
    }

    COMPLEXITY_KEYWORDS: ClassVar[set[str]] = {
        "分析", "设计", "评估", "解释", "总结", "优化", "重构",
        "analyze", "design", "evaluate", "explain", "optimize",
        "架构", "系统设计", "分布式", "实现", "开发", "排查",
    }

    # 复杂度阈值
    COMPLEXITY_LOW: ClassVar[float] = 0.3
    COMPLEXITY_HIGH: ClassVar[float] = 0.7

    # 模型映射
    TIER_MODELS: ClassVar[dict[str, dict[str, str]]] = {
        "local":  {"provider": "ollama",    "model": "llama3.2"},
        "small":  {"provider": "openai",    "model": "gpt-4o-mini"},
        "medium": {"provider": "openai",    "model": "gpt-4o"},
        "large":  {"provider": "openai",    "model": "gpt-4o"},
    }

    @staticmethod
    def has_privacy_sensitive_content(text: str) -> bool:
        """检测文本是否包含隐私敏感关键词。"""
        text_lower = text.lower()
        for kw in ModelRouter.PRIVACY_KEYWORDS:
            if kw.lower() in text_lower:
                return True
        return False

    @staticmethod
    def assess_complexity(text: str) -> float:
        """评估文本复杂度 (0.0 ~ 1.0)。

        基于：
        - 关键词密度
        - 文本长度
        - 结构标记（代码块、表格等）
        """
        score = 0.0

        # 关键词贡献
        text_lower = text.lower()
        kw_count = sum(1 for kw in ModelRouter.COMPLEXITY_KEYWORDS if kw.lower() in text_lower)
        kw_score = min(kw_count / 5.0, 0.4)  # 最多贡献 0.4
        score += kw_score

        # 文本长度贡献
        length = len(text)
        if length > 500:
            score += 0.15
        elif length > 200:
            score += 0.08
        elif length > 50:
            score += 0.03

        # 结构标记：代码块、表格、列表
        structural_indicators = ["```", "| ", "|-", "1. ", "- [", "=="]
        structure_count = sum(1 for ind in structural_indicators if ind in text)
        score += min(structure_count * 0.08, 0.2)

        # 问号数量（多问号 = 复杂查询）
        qmark_count = text.count("?") + text.count("？")
        score += min(qmark_count * 0.04, 0.15)

        return min(score, 1.0)

    @staticmethod
    def route(agent_id: str, text: str) -> RoutingDecision:
        """为指定 Agent 和输入文本生成路由决策。

        决策顺序：
        1. 隐私敏感 → force local
        2. 复杂度 < 0.3 → small
        3. 复杂度 ≥ 0.7 → large
        4. 否则 → medium
        """
        # 1. 隐私检查 — 最高优先级
        if ModelRouter.has_privacy_sensitive_content(text):
            tier_info = ModelRouter.TIER_MODELS["local"]
            _log.info("model_router: agent=%s privacy_sensitive → local (%s/%s)",
                      agent_id, tier_info["provider"], tier_info["model"])
            return RoutingDecision(
                tier="local",
                model=tier_info["model"],
                provider=tier_info["provider"],
                reason="privacy_sensitive_content",
                privacy_sensitive=True,
            )

        # 2. 复杂度评估
        complexity = ModelRouter.assess_complexity(text)

        if complexity < ModelRouter.COMPLEXITY_LOW:
            tier = "small"
            reason = f"low_complexity({complexity:.2f})"
        elif complexity >= ModelRouter.COMPLEXITY_HIGH:
            tier = "large"
            reason = f"high_complexity({complexity:.2f})"
        else:
            tier = "medium"
            reason = f"medium_complexity({complexity:.2f})"

        tier_info = ModelRouter.TIER_MODELS[tier]
        _log.info("model_router: agent=%s → %s (complexity=%.2f, %s/%s)",
                  agent_id, tier, complexity, tier_info["provider"], tier_info["model"])
        return RoutingDecision(
            tier=tier,
            model=tier_info["model"],
            provider=tier_info["provider"],
            reason=reason,
        )