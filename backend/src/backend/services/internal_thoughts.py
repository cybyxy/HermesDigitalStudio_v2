"""小心思生成器：Agent 空闲时基于知识图谱和历史行为产生主动性推测和关怀表达。"""

from __future__ import annotations

import logging
import random
import time
import uuid
from dataclasses import dataclass, field
from typing import ClassVar

_log = logging.getLogger(__name__)


@dataclass
class SmallThought:
    """一条小心思。"""
    thought_id: str
    agent_id: str
    content: str
    trigger: str          # random_walk | emotional | energy
    confidence: float
    timestamp: float


@dataclass
class ThoughtQuality:
    """小心思质量评估结果。"""
    is_novel: bool
    is_contextual: bool
    is_coherent: bool
    overall_score: float


class InternalThoughtsService:
    """小心思生成器。

    在心跳空闲周期中，偶尔生成主动关怀/推测，通过 SSE 推送到前端。
    """

    TRIGGER_CONDITIONS: ClassVar[dict] = {
        "satiety_low": 40,
        "satiety_high": 70,
        "trigger_probability": 0.3,
        "min_confidence": 0.5,
    }

    # 每个 agent 最多保留最近几条小心思用于去重
    _MAX_RECENT_THOUGHTS: ClassVar[int] = 10

    # 单例
    _instance: InternalThoughtsService | None = None

    def __new__(cls) -> InternalThoughtsService:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._recent_thoughts: dict[str, list[str]] = {}
        return cls._instance

    # ── 公共接口 ───────────────────────────────────────────────────────

    async def should_generate(self, agent_id: str) -> bool:
        """判断当前是否应该为指定 agent 生成一条小心思。

        条件：
        - 饱食度在可触发区间内
        - 随机概率命中
        """
        try:
            from backend.services.energy import get_energy_service
            energy = await get_energy_service().get_energy(agent_id)
            satiety = energy.get("satiety", 50)
            if not (self.TRIGGER_CONDITIONS["satiety_low"] <= satiety <= self.TRIGGER_CONDITIONS["satiety_high"]):
                return False
        except Exception:
            # 能量服务不可用时默认允许
            pass

        return random.random() < self.TRIGGER_CONDITIONS["trigger_probability"]

    async def generate(self, agent_id: str, nodes: list[dict] | None = None) -> SmallThought | None:
        """基于当前知识图谱节点生成一条小心思。

        流程：
        1. 通过 LLM 生成 30 字以内的内心独白
        2. 评估质量（新颖性、连贯性、上下文相关性）
        3. 去重检查
        """
        # 构建节点文本
        if not nodes:
            nodes_text = "无特定知识碎片"
        else:
            snippets = []
            for n in nodes[:10]:
                label = n.get("label", "")
                name = n.get("name", "") or label
                props = n.get("properties", {})
                desc = props.get("description", "") if isinstance(props, dict) else ""
                if name or desc:
                    snippets.append(f"{name}: {desc}" if desc else name)
            nodes_text = "；".join(snippets) if snippets else "无特定知识碎片"

        # 用轻量级 prompt 生成小心思
        prompt = (
            "你是一个正在沉思的 AI 人格。基于以下知识碎片，生成一句 50 字以内的内心独白。\n"
            "要求：自然、温暖、有洞察力，不要重复、不要解释，只输出独白本身。\n\n"
            f"知识碎片：{nodes_text}"
        )

        thought_text = await self._call_llm(agent_id, prompt)
        if not thought_text:
            return None

        thought_text = thought_text.strip().strip('"').strip("'").strip("「").strip("」")
        if len(thought_text) < 4 or len(thought_text) > 100:
            return None

        # 质量评估
        recent = self._get_recent_thoughts(agent_id)
        quality = self._evaluate_quality(thought_text, recent)
        if not quality.is_novel:
            _log.debug("internal_thoughts: agent=%s thought rejected (not novel): %s", agent_id, thought_text[:40])
            return None
        if quality.overall_score < self.TRIGGER_CONDITIONS["min_confidence"]:
            _log.debug("internal_thoughts: agent=%s thought rejected (low confidence=%.2f)", agent_id, quality.overall_score)
            return None

        # 记录到最近列表
        self._recent_thoughts.setdefault(agent_id, []).append(thought_text)
        if len(self._recent_thoughts[agent_id]) > self._MAX_RECENT_THOUGHTS:
            self._recent_thoughts[agent_id] = self._recent_thoughts[agent_id][-self._MAX_RECENT_THOUGHTS:]

        return SmallThought(
            thought_id=uuid.uuid4().hex[:12],
            agent_id=agent_id,
            content=thought_text,
            trigger="random_walk",
            confidence=quality.overall_score,
            timestamp=time.time(),
        )

    # ── 内部方法 ──────────────────────────────────────────────────────

    def _get_recent_thoughts(self, agent_id: str, n: int = 10) -> list[str]:
        """获取 agent 最近生成的几条小心思文本，用于去重。"""
        return list(self._recent_thoughts.get(agent_id, []))[-n:]

    def _evaluate_quality(self, thought: str, recent: list[str]) -> ThoughtQuality:
        """评估一条小心思的质量。

        新颖性：与最近已生成的小心思的 Jaccard 相似度不超过 0.6。
        """
        is_coherent = 3 <= len(thought) <= 100

        # 新颖性检查 — 简单 Jaccard 相似度
        is_novel = True
        thought_set = set(thought)
        for old in recent:
            if not old:
                continue
            old_set = set(old)
            intersection = len(thought_set & old_set)
            union = len(thought_set | old_set)
            jaccard = intersection / max(union, 1)
            if jaccard > 0.6:
                is_novel = False
                break

        # 上下文相关性 — 有实质内容
        is_contextual = len(thought) >= 6 and not thought.startswith("//") and not thought.startswith("##")

        overall = (0.4 if is_novel else 0) + (0.3 if is_contextual else 0) + (0.3 if is_coherent else 0)

        return ThoughtQuality(
            is_novel=is_novel,
            is_contextual=is_contextual,
            is_coherent=is_coherent,
            overall_score=overall,
        )

    async def _call_llm(self, agent_id: str, prompt: str) -> str | None:
        """使用 Agent 自己的 gateway 调用 LLM 生成小心思文本。"""
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

            done = asyncio.get_running_loop().create_future()

            reply_parts: list[str] = []

            def on_complete(_reply: str, _meta: dict | None = None) -> None:
                reply_parts.append(str(_reply or ""))
                if not done.done():
                    done.set_result(True)

            gw.gateway.submit_prompt(sid, prompt, attachments=None)
            gw.gateway.on("message.complete", on_complete)

            try:
                await asyncio.wait_for(done, timeout=30.0)
            except asyncio.TimeoutError:
                _log.debug("internal_thoughts: agent=%s LLM call timed out", agent_id)
                return None

            return reply_parts[0] if reply_parts else None

        except Exception as e:
            _log.debug("internal_thoughts: agent=%s LLM call failed: %s", agent_id, e)
            return None