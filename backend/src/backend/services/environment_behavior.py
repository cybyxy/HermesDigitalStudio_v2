"""环境驱动行为生成 (Environment-Driven Behavior Generation)

选择环境焦点 → 向量关联 → LLM 生成动态行为
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field


@dataclass
class PADDelta:
    """PAD 情绪变化量"""
    v: float = 0.0
    a: float = 0.0
    d: float = 0.0


@dataclass
class BehaviorResult:
    """行为生成结果"""

    action: str  # e.g. "轻轻推开窗户，感受微风拂面"
    self_talk: str  # e.g. "今天天气真不错呢..."
    emotion_delta: PADDelta = field(default_factory=PADDelta)
    duration_seconds: int = 30  # 默认 30 秒
    move_to: tuple[float, float] | None = None  # 如需移动到特定坐标
    focus_item_name: str = ""


# ═══════════════ 环境焦点选择 ═══════════════


def select_environment_focus(
    nearby_items: list[tuple],
    recent_focuses: list[str] | None = None,
) -> dict | None:
    """从附近物品中选择焦点。

    策略：距离加权 + 情绪新颖性（避免重复关注同一物品）。

    Args:
        nearby_items: [(item_dict, distance), ...]
            item_dict 需包含: name, mood_tags
        recent_focuses: 最近关注过的物品名列表

    Returns:
        选中的 item_dict 或 None
    """
    if not nearby_items:
        return None

    if recent_focuses is None:
        recent_focuses = []

    scored: list[tuple[dict, float]] = []
    for item_data, distance in nearby_items:
        score = 1.0 / max(1.0, distance / 50)  # 距离越近分数越高

        # 情绪新颖性加分
        tags = item_data.get("mood_tags", [])
        if isinstance(tags, list) and tags:
            score *= (1.0 + len(tags) * 0.1)

        # 避免重复
        name = item_data.get("name", "")
        if name in recent_focuses:
            score *= 0.3  # 最近关注过的物品降权

        scored.append((item_data, score))

    # 加权随机选择（分数越高选中概率越大）
    if not scored:
        return None

    total = sum(s for _, s in scored)
    if total <= 0:
        return scored[0][0]

    r = random.random() * total
    cumulative = 0.0
    for item_data, score in scored:
        cumulative += score
        if r <= cumulative:
            return item_data

    return scored[-1][0]


# ═══════════════ LLM 行为生成提示词 ═══════════════


ENVIRONMENT_BEHAVIOR_PROMPT = """你是一个数字生命 Agent，正在虚拟环境中自主活动。

【你的当前状态】
性格特点：{personality}
当前情绪：愉悦度 {valence:.2f} / 唤醒度 {arousal:.2f} / 支配度 {dominance:.2f}
能量状态：饱食度 {satiety}

【当前环境感知】
{environment_perception}

【环境焦点】
你注意到了「{focus_name}」。{focus_description}
环境情绪标签：{mood_tags}

【联想内容】
这让你想起了：{association}

【可能触发的情绪】
{triggered_emotions}

请生成一个符合你性格和当前情绪的自然行为：
1. 一个具体的动作（可以是与环境物品互动，也可以是简单的姿态变化）
2. 一句自言自语（口语化、不超过20字）
3. 这个行为让你产生的情绪微小变化

请按以下 JSON 格式返回：
{{
  "action": "你的动作描述",
  "self_talk": "你的自言自语",
  "emotion_delta": {{
    "valence": 0.05,
    "arousal": -0.02,
    "dominance": 0.0
  }},
  "duration_seconds": 30
}}

要求：动作自然不夸张；语言具有个性；不重复常见模式；每次可以不同。"""


def build_environment_behavior_prompt(
    personality: str,
    valence: float,
    arousal: float,
    dominance: float,
    satiety: int,
    environment_perception: str,
    focus_name: str,
    focus_description: str,
    mood_tags: list[str],
    association: str,
    triggered_emotions: str,
) -> str:
    """构建环境行为生成的 LLM 提示词。

    Args:
        personality: 性格描述文本
        valence, arousal, dominance: 当前 PAD 值
        satiety: 饱食度 0-100
        environment_perception: 环境感知文本
        focus_name: 焦点物品名称
        focus_description: 焦点物品描述
        mood_tags: 环境情绪标签列表
        association: 联想内容文本
        triggered_emotions: 可能触发的情绪描述

    Returns:
        LLM prompt 字符串
    """
    return ENVIRONMENT_BEHAVIOR_PROMPT.format(
        personality=personality,
        valence=valence,
        arousal=arousal,
        dominance=dominance,
        satiety=satiety,
        environment_perception=environment_perception,
        focus_name=focus_name,
        focus_description=focus_description,
        mood_tags=", ".join(mood_tags) if mood_tags else "无",
        association=association or "无特别联想",
        triggered_emotions=triggered_emotions or "无",
    )


# ═══════════════ 行为响应解析 ═══════════════


def parse_behavior_response(response: str) -> BehaviorResult:
    """解析 LLM 输出为结构化行为结果。

    Args:
        response: LLM 返回的 JSON 字符串

    Returns:
        BehaviorResult (解析失败时返回默认行为)
    """
    import json

    try:
        data = json.loads(response)

        action = str(data.get("action", ""))
        self_talk = str(data.get("self_talk", ""))

        ed = data.get("emotion_delta", {})
        emotion_delta = PADDelta(
            v=float(ed.get("valence", 0.0)),
            a=float(ed.get("arousal", 0.0)),
            d=float(ed.get("dominance", 0.0)),
        )

        duration = int(data.get("duration_seconds", 30))

        return BehaviorResult(
            action=action,
            self_talk=self_talk,
            emotion_delta=emotion_delta,
            duration_seconds=duration,
        )

    except (json.JSONDecodeError, KeyError, TypeError, ValueError):
        # 解析失败时返回默认行为
        return BehaviorResult(
            action="环顾四周，若有所思",
            self_talk="这里挺安静的...",
            emotion_delta=PADDelta(),
            duration_seconds=15,
        )
