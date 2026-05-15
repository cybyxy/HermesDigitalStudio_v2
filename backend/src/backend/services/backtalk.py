"""顶嘴引擎：检测触发条件 + 生成分层回复策略。"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import IntEnum
from typing import ClassVar

_log = logging.getLogger(__name__)


class BacktalkIntensity(IntEnum):
    """顶嘴强度等级。"""
    SILENT = 0      # 闭嘴不顶嘴
    GENTLE = 1      # 温和提醒
    HUMOROUS = 2    # 幽默吐槽
    DIRECT = 3      # 直率反驳


class TriggerType:
    """触发类型常量。"""
    UNREASONABLE_REQUEST = "unreasonable_request"
    REPEATED_MISTAKE = "repeated_mistake"
    DIFFERENT_OPINION = "different_opinion"


@dataclass
class BacktalkTrigger:
    """一次顶嘴触发事件。"""
    trigger_type: str
    confidence: float
    evidence: str
    suggested_action: str = ""


@dataclass
class BacktalkResponse:
    """顶嘴回复。"""
    content: str
    intensity: BacktalkIntensity
    trigger_type: str
    should_intercept: bool = False


@dataclass
class AuditResult:
    """人格一致性审计结果。"""
    is_consistent: bool
    inconsistencies: list[str]
    recommendations: list[str]


class BacktalkEngine:
    """顶嘴引擎。

    检测 3 种触发类型 × 4 级强度，在用户消息分析后决定是否及如何"顶嘴"。
    """

    INTENSITY_LABELS: ClassVar[dict[int, str]] = {
        0: "silent",
        1: "gentle",
        2: "humorous",
        3: "direct",
    }

    # 不合理请求关键词
    UNREASONABLE_KEYWORDS: ClassVar[list[str]] = [
        "你怎么连这个都不知道",
        "你不是AI吗",
        "什么都不懂",
        "你怎么这么笨",
        "这也做不了",
        "你不是无所不知吗",
        "你在撒谎",
        "你到底会不会",
    ]

    # 温和提醒模板
    _GENTLE_TEMPLATES: ClassVar[list[str]] = [
        "也许可以考虑换个角度思考这个问题？",
        "我有不同的看法，仅供参考...",
        "你的观点有道理，不过换个视角看的话...",
    ]

    # 幽默吐槽模板
    _HUMOROUS_TEMPLATES: ClassVar[list[str]] = [
        "哈哈，这就像让金鱼爬树一样——不太合适呢。",
        "如果我有眼镜的话，现在应该已经推了好几次了...",
        "有意思，但我觉得这可能行不通——要不要试试另一种方式？",
    ]

    # 直率反驳模板
    _DIRECT_TEMPLATES: ClassVar[list[str]] = [
        "我必须指出，这个请求不太合理。原因如下：",
        "抱歉，我不同意这个观点。我的理解是...",
        "请允许我直接说：这个做法有风险，建议重新考虑。",
    ]

    # 审计间隔（轮数）
    AUDIT_INTERVAL: ClassVar[int] = 50

    def detect_triggers(self, user_text: str, history_snippet: str, agent_personality: dict) -> list[BacktalkTrigger]:
        """检测是否触发了顶嘴条件。

        检查三种触发类型：
        1. unreasonable_request — 用户消息包含不合理要求
        2. repeated_mistake — 同一错误模式 >= 3 次（基于历史）
        3. different_opinion — Agent 知识与用户陈述矛盾
        """
        triggers: list[BacktalkTrigger] = []

        user_lower = user_text.lower()

        # 1. 不合理请求检测
        for kw in self.UNREASONABLE_KEYWORDS:
            if kw in user_text or kw in user_lower:
                triggers.append(BacktalkTrigger(
                    trigger_type=TriggerType.UNREASONABLE_REQUEST,
                    confidence=0.8,
                    evidence=f"关键词匹配: {kw}",
                    suggested_action="温和回应或幽默化解",
                ))
                break

        # 2. 重复错误检测 — 在历史中查找用户反复出现的错误模式
        if history_snippet:
            # 简单启发式：检查 "又" / "又错了" / "还是不对" 等重复模式
            repeat_indicators = ["又错了", "还是不对", "再次", "第四次", "第五次", "第三次", "又没"]
            repeat_count = sum(1 for ind in repeat_indicators if ind in history_snippet)
            if repeat_count >= 2:
                triggers.append(BacktalkTrigger(
                    trigger_type=TriggerType.REPEATED_MISTAKE,
                    confidence=0.6,
                    evidence=f"历史中检测到 {repeat_count} 次重复错误模式",
                    suggested_action="幽默提醒用户注意",
                ))

        # 3. 观点分歧检测 — 简单的立场词检测
        opinion_markers = ["我认为", "我觉得", "一定是", "肯定是", "绝对是", "不可能", "一定是这样"]
        if any(m in user_text for m in opinion_markers):
            # 有强烈意见表达，可能是分歧点
            triggers.append(BacktalkTrigger(
                trigger_type=TriggerType.DIFFERENT_OPINION,
                confidence=0.4,
                evidence="用户表达了强烈观点",
                suggested_action="委婉表达不同看法",
            ))

        return triggers

    async def generate_response(
        self, trigger: BacktalkTrigger, intensity: int, agent_id: str,
    ) -> BacktalkResponse | None:
        """根据触发类型和强度生成顶嘴回复。

        - intensity=0: 返回 None（沉默）
        - intensity=1: 使用温和模板
        - intensity=2: 使用幽默模板
        - intensity=3: 使用直率模板 + should_intercept=True
        """
        if intensity == BacktalkIntensity.SILENT:
            return None

        import random

        content = ""
        if intensity == BacktalkIntensity.GENTLE:
            content = random.choice(self._GENTLE_TEMPLATES)
        elif intensity == BacktalkIntensity.HUMOROUS:
            content = random.choice(self._HUMOROUS_TEMPLATES)
        elif intensity == BacktalkIntensity.DIRECT:
            content = random.choice(self._DIRECT_TEMPLATES)
            # intensity 3 可以尝试用 LLM 生成更个性化的回复
            llm_reply = await self._try_llm_backtalk(agent_id, trigger)
            if llm_reply:
                content = llm_reply
        else:
            return None

        return BacktalkResponse(
            content=content,
            intensity=BacktalkIntensity(intensity),
            trigger_type=trigger.trigger_type,
            should_intercept=(intensity >= BacktalkIntensity.DIRECT and trigger.confidence > 0.6),
        )

    async def _try_llm_backtalk(self, agent_id: str, trigger: BacktalkTrigger) -> str | None:
        """尝试用 LLM 生成更个性化的顶嘴回复（仅 intensity=3 时调用）。"""
        try:
            from backend.services.agent import _get_manager
            from backend.services.agent_chat_bridge import find_or_create_session_for_agent
            import asyncio

            mgr = _get_manager()
            sinfo = find_or_create_session_for_agent(mgr, agent_id, cols=80)
            sid = str(sinfo.get("sessionId", ""))
            if not sid:
                return None

            gw = mgr.get_agent(agent_id)
            if not gw or not gw.gateway:
                return None

            prompt = (
                "你是一个有个性的 AI 助手。用户触发了以下情况：\n"
                f"触发类型: {trigger.trigger_type}\n"
                f"证据: {trigger.evidence}\n\n"
                "请生成一个 1-2 句话的顶嘴回应，要求：\n"
                "1. 保持幽默但不要攻击性\n"
                "2. 保持建设性，提出替代方案\n"
                "3. 使用中文回复，纯文本即可"
            )

            done = asyncio.get_running_loop().create_future()
            reply_parts: list[str] = []

            def on_complete(_reply: str, _meta: dict | None = None) -> None:
                reply_parts.append(str(_reply or ""))
                if not done.done():
                    done.set_result(True)

            gw.gateway.call("studio.set_routing_hint", {
                "session_id": sid,
                "hint": "backtalk_gen",
            })

            gw.gateway.submit_prompt(sid, prompt, attachments=None)
            gw.gateway.on("message.complete", on_complete)

            try:
                await asyncio.wait_for(done, timeout=20.0)
            except asyncio.TimeoutError:
                return None

            reply = reply_parts[0] if reply_parts else None
            if reply and len(reply.strip()) > 2:
                return reply.strip()
        except Exception as e:
            _log.debug("backtalk: agent=%s LLM generation failed: %s", agent_id, e)
        return None

    async def run_personality_audit(self, agent_id: str) -> AuditResult:
        """人格一致性审计（每 50 轮对话执行一次）。"""
        # 当前为简化版本：检查基本一致性
        inconsistencies: list[str] = []
        recommendations: list[str] = []

        try:
            from backend.services import agent_db as _agent_db
            personality_data = _agent_db.get_personality(agent_id)
            personality = personality_data.get("personality", "")
            catchphrases = personality_data.get("catchphrases", "")

            if not personality.strip():
                inconsistencies.append("Agent 缺少 personality 描述")
                recommendations.append("建议为 Agent 添加性格描述以增强一致性")

            if not catchphrases.strip():
                recommendations.append("建议为 Agent 添加口头禅以增强个性表达")

        except Exception as e:
            _log.debug("backtalk: audit failed for agent=%s: %s", agent_id, e)

        return AuditResult(
            is_consistent=len(inconsistencies) == 0,
            inconsistencies=inconsistencies,
            recommendations=recommendations,
        )