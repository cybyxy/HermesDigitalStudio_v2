"""神经电流计算引擎 — 纯计算，无I/O依赖。

包含三类函数:
1. 核心电流计算（电压推导、传导深度、焦耳热）
2. 情绪→神经电流桥接（电压调制、电导偏置、饱食度修正）
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Optional

# ═══════════════ 核心电流常量 ═══════════════
MIN_VOLTAGE = 0.1
HOP_RESISTANCE = 1.0
HIGH_RESISTANCE = 0.2  # 低权重边阈值
HEDONIC_THRESHOLD_QUALITY = 0.8
HEDONIC_THRESHOLD_SATIETY = 85
HEDONIC_VOLTAGE_MULTIPLIER = 2.0
JOULE_HEAT_DECAY = 0.9  # 每分钟衰减率
METABOLIC_WASTE_DECAY = 0.95
JOULE_HEAT_THRESHOLD = 0.7  # 提前终止阈值
LOW_QUALITY_SATIETY_PENALTY = 0.15  # 暴食惩罚系数

# ═══════════════ 情绪→神经电流调制常量 ═══════════════
EMOTION_POSITIVE_VOLTAGE_BOOST = 0.25
EMOTION_NEGATIVE_VOLTAGE_DAMP = 0.15
EMOTION_AROUSAL_VOLTAGE_FACTOR = 0.20
EMOTION_MAX_VOLTAGE_MOD = 0.50  # ±50%
EMOTION_POSITIVE_CONDUCTANCE_BONUS = 0.10
EMOTION_NEGATIVE_CONDUCTANCE_PENALTY = 0.08
HIGH_SATIETY_PAD_STABILITY = 0.30
EMOTION_REFRACTORY_VOLTAGE_RATIO = 0.30


@dataclass
class ConductionResult:
    """传导深度计算结果"""
    remaining_voltage: float
    max_depth: int
    can_continue: bool
    decay_curve: list[float] = field(default_factory=list)


@dataclass
class VoltageResult:
    """电压计算结果"""
    base_voltage: float
    modulated_voltage: float
    overclock_applied: bool
    overclock_factor: float
    hedonic_override: bool
    is_refractory: bool


# ═══════════════ 1. 核心电流计算 ═══════════════


def compute_initial_voltage(
    satiety: int,
    bio_current: int,
    mode: str,
    task_complexity: str = "medium",
) -> float:
    """从能量状态推导初始电压。

    satiety: 0-100 饱食度
    bio_current: 0-10 生物电流
    mode: normal / power_save / surge / forced_discharge
    task_complexity: idle / simple / medium / large
    """
    # Step 1: 饱食度乘数
    if satiety < 10:
        satiety_mul = 2.5  # 极度饥饿（仅Idle模式）
    elif satiety < 30:
        satiety_mul = 1.5 + (30 - satiety) / 40  # 1.5~2.0
    elif satiety < 60:
        satiety_mul = 1.0 + (60 - satiety) / 60  # 1.0~1.5
    elif satiety < 85:
        satiety_mul = 1.0  # 正常
    else:
        satiety_mul = 0.7 - (satiety - 85) / 50  # 0.3~0.7

    # Step 2: mode修正
    mode = mode or "normal"
    if mode == "power_save":
        satiety_mul *= 0.3
    elif mode == "surge":
        satiety_mul *= 1.5
    elif mode == "forced_discharge":
        satiety_mul *= 2.0

    # Step 3: bio_current乘数
    if bio_current <= 3:
        bio_mul = 1.0
    elif bio_current <= 6:
        bio_mul = 1.5
    elif bio_current <= 8:
        bio_mul = 2.0
    else:
        bio_mul = 3.0

    # Step 4: 任务复杂度
    complexity_mul = {
        "idle": 0.5,
        "simple": 0.8,
        "medium": 1.0,
        "large": 1.5,
    }.get(task_complexity, 1.0)

    return 1.0 * satiety_mul * bio_mul * complexity_mul


def compute_conduction_depth(
    initial_voltage: float,
    edge_weights: list[float],
) -> ConductionResult:
    """逐跳电压衰减计算传导深度。

    formula: remaining = voltage * weight / (1 + HOP_RESISTANCE * (hop + 1))
    低权重边 (<0.2) 额外衰减 ×0.5
    电压降至 MIN_VOLTAGE (0.1) 以下时停止传导。
    """
    remaining = initial_voltage
    decay_curve: list[float] = []

    for hop, weight in enumerate(edge_weights):
        if weight < HIGH_RESISTANCE:
            remaining *= 0.5  # 低权重额外衰减

        remaining = remaining * weight / (1 + HOP_RESISTANCE * (hop + 1))
        decay_curve.append(remaining)

        if remaining < MIN_VOLTAGE:
            return ConductionResult(
                remaining_voltage=remaining,
                max_depth=hop,
                can_continue=False,
                decay_curve=decay_curve,
            )

    return ConductionResult(
        remaining_voltage=remaining,
        max_depth=len(edge_weights),
        can_continue=True,
        decay_curve=decay_curve,
    )


def compute_activation_voltage(
    signal_alignment: float,
    neuron_expression: float,
    initial_voltage: float,
) -> float:
    """单个神经元激活电压 = 信号匹配度 × 表达强度 × 初始电压"""
    return initial_voltage * signal_alignment * (0.5 + neuron_expression)


def check_hedonic_override(
    satiety: int,
    prompt_quality: float,
) -> tuple[bool, float]:
    """甜点效应检测。

    条件: prompt_quality >= 0.8 AND satiety >= 85
    返回: (is_override, override_voltage_multiplier)
    """
    if prompt_quality >= HEDONIC_THRESHOLD_QUALITY and satiety >= HEDONIC_THRESHOLD_SATIETY:
        return True, HEDONIC_VOLTAGE_MULTIPLIER
    return False, 1.0


def accumulate_joule_heat(edge_weights: list[float], hops_taken: int) -> float:
    """低权重路径产热计算。

    热 = sum((1 - weight) * 0.15 for weight in traversed_weights)
    低权重边产生更多热。
    """
    if not edge_weights:
        return 0.0
    heat = sum((1.0 - min(w, 1.0)) * 0.15 for w in edge_weights)
    # 跳数越多，额外产热
    heat += hops_taken * 0.02
    return min(1.0, heat)


def compute_metabolic_waste(
    consecutive_low_quality: int,
    satiety: int,
) -> float:
    """暴食惩罚代谢废物。

    waste = consecutive_low_quality * 0.15 * (1.0 + (100 - satiety) / 100)
    低质量交互越连续+satiety越高，废物越多。
    """
    base = consecutive_low_quality * LOW_QUALITY_SATIETY_PENALTY
    satiety_penalty = 1.0 + max(0, (satiety - 60)) / 100  # 饱食时惩罚加重
    return min(1.0, base * satiety_penalty)


def compute_prompt_quality(text: str) -> float:
    """启发式评估输入质量 0-1。

    基于: 长度、标点、关键词多样性
    """
    if not text.strip():
        return 0.0

    t = text.strip()
    length = len(t)

    # 长度评分: 0-50字=0.3, 50-200字=0.5-0.8, 200+=0.8-1.0
    if length < 20:
        length_score = 0.3
    elif length < 50:
        length_score = 0.5
    elif length < 200:
        length_score = 0.5 + (length - 50) / 150 * 0.3
    else:
        length_score = min(1.0, 0.8 + (length - 200) / 500 * 0.2)

    # 标点多样性: 问号+感叹号 = 高质量
    question_count = t.count("?") + t.count("？")
    exclaim_count = t.count("!") + t.count("！")
    punct_score = min(0.3, (question_count + exclaim_count) * 0.05)

    # 词汇多样性
    words = re.split(r"\s+", t)
    unique_ratio = len(set(words)) / max(1, len(words))
    vocab_score = min(0.3, unique_ratio * 0.5)

    return min(1.0, length_score + punct_score + vocab_score)


def compute_joule_heat_decay(current_heat: float, elapsed_minutes: float) -> float:
    """焦耳热指数衰减。

    new = current * JOULE_HEAT_DECAY ^ elapsed_minutes
    """
    return current_heat * (JOULE_HEAT_DECAY ** elapsed_minutes)


def compute_metabolic_waste_decay(current_waste: float, elapsed_minutes: float) -> float:
    """代谢废物指数衰减。"""
    return current_waste * (METABOLIC_WASTE_DECAY ** elapsed_minutes)


# ═══════════════ 2. 情绪→神经电流桥接 ═══════════════


def compute_emotion_voltage_modulation(
    base_voltage: float,
    pad: tuple[float, float, float],
    is_refractory: bool = False,
) -> float:
    """情绪→神经电压调制。

    正面情绪增强电压（最多+50%），负面情绪抑制（最多-50%）。
    不应期强制降至30%。

    Args:
        base_voltage: 基础电压
        pad: (valence, arousal, dominance) 各 ∈ [-1, 1]
        is_refractory: 是否处于冷却不应期
    """
    v, a, d = pad

    # 不应期强制低压
    if is_refractory:
        return base_voltage * EMOTION_REFRACTORY_VOLTAGE_RATIO

    # 愉悦度调制: v>0 增益, v<0 抑制
    valence_mod = 1.0 + v * EMOTION_POSITIVE_VOLTAGE_BOOST
    # 唤醒度乘数（仅正向生效）
    arousal_mod = 1.0 + max(0.0, a) * EMOTION_AROUSAL_VOLTAGE_FACTOR
    # 支配度（自信增强电压）
    dominance_mod = 1.0 + max(0.0, d) * 0.10

    modulated = base_voltage * valence_mod * arousal_mod * dominance_mod

    # Clamp 到 [base*0.5, base*1.5]
    return max(base_voltage * 0.5, min(base_voltage * 1.5, modulated))


def compute_emotion_conductance_bias(pad: tuple[float, float, float]) -> float:
    """情绪→边电导偏置。

    正面情绪降低电阻（提升探索广度），负面情绪增加电阻（限制新路径）。

    Returns:
        负值 = 降低电阻（增加电导），正值 = 增加电阻（降低电导）
    """
    v, _, _ = pad
    if v >= 0:
        return -abs(v) * EMOTION_POSITIVE_CONDUCTANCE_BONUS
    else:
        return abs(v) * EMOTION_NEGATIVE_CONDUCTANCE_PENALTY


def compute_emotion_satiety_modifier(pad: tuple[float, float, float], satiety: int) -> float:
    """情绪→饱食度消耗修正。

    负面情绪加速消耗，高唤醒额外消耗，高饱食度稳定缓冲。

    Returns:
        消耗乘数（1.0 = 正常速率）。最小 0.2。
    """
    v, a, _ = pad

    negative_penalty = max(0.0, -v) * 1.5
    arousal_penalty = max(0.0, a) * 0.5

    stability_bonus = 0.0
    if satiety > 60:
        stability_bonus = (satiety - 60) / 40 * HIGH_SATIETY_PAD_STABILITY

    modifier = 1.0 + negative_penalty + arousal_penalty - stability_bonus
    return max(0.2, modifier)


def compute_emotion_hedonic_threshold(pad: tuple[float, float, float], satiety: int) -> bool:
    """情绪享乐覆盖判断：正面高情绪可覆盖饱食度限制。

    条件: valence > 0.5 AND arousal > 0.5
    """
    v, a, _ = pad
    return v > 0.5 and a > 0.5


# ═══════════════ 3. 完整电压计算管线 ═══════════════


def compute_full_voltage_pipeline(
    satiety: int,
    bio_current: int,
    mode: str,
    task_complexity: str,
    pad: tuple[float, float, float],
    is_refractory: bool,
    prompt_quality: float,
    overclock_factor: float = 1.0,
    hedonic_override_applied: bool = False,
    hedonic_voltage_multiplier: float = 1.0,
) -> VoltageResult:
    """完整电压计算管线：能量 → 情绪调制 → 内驱力 → 享乐覆盖。

    返回 VoltageResult 包含中间计算结果。
    """
    # Step 1: 基础电压
    base = compute_initial_voltage(satiety, bio_current, mode, task_complexity)

    # Step 2: 情绪调制
    modulated = compute_emotion_voltage_modulation(base, pad, is_refractory)

    # Step 3: 享乐覆盖
    hedonic = hedonic_override_applied
    if hedonic and hedonic_voltage_multiplier > 1.0:
        modulated *= hedonic_voltage_multiplier

    # Step 4: 内驱力超频
    if overclock_factor > 1.0:
        modulated *= overclock_factor
        # 超频上限 = base * 1.8
        modulated = min(modulated, base * 1.8)

    return VoltageResult(
        base_voltage=base,
        modulated_voltage=modulated,
        overclock_applied=overclock_factor > 1.0,
        overclock_factor=overclock_factor,
        hedonic_override=hedonic,
        is_refractory=is_refractory,
    )
