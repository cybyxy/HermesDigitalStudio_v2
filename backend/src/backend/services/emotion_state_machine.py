"""情绪状态机 (Emotion State Machine) — 6状态 PAD 驱动

纯计算模块，不依赖 I/O。

States: CALM | ACTIVATED | PEAK | DECAYING | RECOVERING | REFRACTORY
"""
from __future__ import annotations

from enum import StrEnum


class EmotionState(StrEnum):
    CALM = "CALM"
    ACTIVATED = "ACTIVATED"
    PEAK = "PEAK"
    DECAYING = "DECAYING"
    RECOVERING = "RECOVERING"
    REFRACTORY = "REFRACTORY"


def determine_state(
    pad: tuple[float, float, float],
    is_refractory: bool,
    prev_state: str,
    prev_pad: tuple[float, float, float] | None = None,
) -> str:
    """根据当前 PAD 与冷却状态计算情绪状态。

    State transition rules:
    - CALM → ACTIVATED:  |valence| > 0.3 AND arousal > 0.3
    - ACTIVATED → PEAK:   |valence| > 0.6 AND arousal > 0.5
    - PEAK → DECAYING:    (valence↓ && arousal↓) 连续两帧下降
    - DECAYING → RECOVERING: |valence| < 0.3 AND arousal < 0.3
    - RECOVERING → CALM:    |valence| < 0.15 AND arousal < 0.15
    - ANY → REFRACTORY:   is_refractory == True
    - REFRACTORY → RECOVERING: is_refractory == False

    Args:
        pad: 当前 (valence, arousal, dominance)
        is_refractory: 是否处于不应期
        prev_state: 上一帧状态
        prev_pad: 上一帧 (valence, arousal, dominance)，用于检测下降

    Returns:
        当前情绪状态字符串
    """
    v, a, _d = pad

    # 不应期优先
    if is_refractory:
        return EmotionState.REFRACTORY

    # 从不应期恢复
    if prev_state == EmotionState.REFRACTORY:
        return EmotionState.RECOVERING

    abs_v = abs(v)

    # CALM → ACTIVATED
    if prev_state in (EmotionState.CALM, EmotionState.RECOVERING):
        if abs_v > 0.3 and a > 0.3:
            return EmotionState.ACTIVATED
        if prev_state == EmotionState.RECOVERING and abs_v < 0.15 and a < 0.15:
            return EmotionState.CALM
        return prev_state

    # ACTIVATED → PEAK
    if prev_state == EmotionState.ACTIVATED:
        if abs_v > 0.6 and a > 0.5:
            return EmotionState.PEAK
        return EmotionState.ACTIVATED

    # PEAK → DECAYING
    if prev_state == EmotionState.PEAK:
        if prev_pad is not None:
            v_prev, a_prev, _ = prev_pad
            if abs(v) < abs(v_prev) and a < a_prev:
                return EmotionState.DECAYING
        return EmotionState.PEAK

    # DECAYING → RECOVERING
    if prev_state == EmotionState.DECAYING:
        if abs_v < 0.3 and a < 0.3:
            return EmotionState.RECOVERING
        return EmotionState.DECAYING

    return prev_state
