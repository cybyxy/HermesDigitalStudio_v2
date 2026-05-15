"""冷却缓冲区 (Cooling Buffer) — 温度模型 + 不应期 + 自然降温

纯计算模块，不依赖 I/O。
"""
from __future__ import annotations

from dataclasses import dataclass, field

# 最高温度
TEMPERATURE_MAX = 1.0

# 每分钟自然降温系数
NATURAL_COOLING_RATE = 0.05

# 每次高强度激活升温
ACTIVATION_HEAT_PER_RUN = 0.15

# 低强度活动升温
IDLE_HEAT_PER_CYCLE = 0.02

# 进入不应期的温度阈值
REFRACTORY_THRESHOLD = 0.75

# 退出不应期的温度阈值
REFRACTORY_EXIT = 0.30

# 情绪爆发额外升温
BURST_COOLDOWN_EXTRA = 0.10


@dataclass
class CoolingBufferState:
    """冷却缓冲区状态"""

    temperature: float = 0.0
    is_refractory: bool = False
    peak_temperature: float = 0.0


def accumulate_heat(
    temperature: float,
    intensity: float,
    is_burst: bool = False,
) -> float:
    """累积热量。

    Args:
        temperature: 当前温度
        intensity: 活动强度 (0.0~1.0)
        is_burst: 是否情绪爆发

    Returns:
        新温度值 (clampped to [0, TEMPERATURE_MAX])
    """
    heat = intensity * ACTIVATION_HEAT_PER_RUN
    if is_burst:
        heat += BURST_COOLDOWN_EXTRA
    return min(TEMPERATURE_MAX, temperature + heat)


def natural_cooldown(temperature: float, elapsed_minutes: float) -> float:
    """自然降温。

    Args:
        temperature: 当前温度
        elapsed_minutes: 经过的分钟数

    Returns:
        降温后的温度 (不低于 0)
    """
    return max(0.0, temperature - NATURAL_COOLING_RATE * elapsed_minutes)


def check_refractory(
    temperature: float, was_refractory: bool
) -> tuple[bool, str]:
    """检查不应期状态变化。

    Args:
        temperature: 当前温度
        was_refractory: 之前是否处于不应期

    Returns:
        (is_refractory, transition)
        transition 为: "enter" / "exit" / "stay" / "none"
    """
    if was_refractory:
        if temperature <= REFRACTORY_EXIT:
            return False, "exit"
        return True, "stay"
    else:
        if temperature >= REFRACTORY_THRESHOLD:
            return True, "enter"
        return False, "none"


def can_activate(temperature: float, is_refractory: bool) -> bool:
    """判断是否可以激活。

    Args:
        temperature: 当前温度
        is_refractory: 是否处于不应期

    Returns:
        True 如果可以激活
    """
    if is_refractory:
        return temperature <= REFRACTORY_EXIT
    return temperature < REFRACTORY_THRESHOLD


def update_cooling_state(
    state: CoolingBufferState,
    intensity: float,
    is_burst: bool,
    elapsed_minutes: float,
) -> CoolingBufferState:
    """一次完整冷却缓冲区更新。

    1. 自然降温
    2. 累积热量
    3. 不应期检查
    4. 更新峰值

    Args:
        state: 当前冷却状态
        intensity: 活动强度 (0.0~1.0)
        is_burst: 是否情绪爆发
        elapsed_minutes: 从上一次更新到现在的分钟数

    Returns:
        更新后的状态
    """
    # Step 1: 自然降温
    state.temperature = natural_cooldown(state.temperature, elapsed_minutes)

    # Step 2: 累积热量
    if intensity > 0:
        state.temperature = accumulate_heat(state.temperature, intensity, is_burst)

    # Step 3: 不应期检查
    state.is_refractory, _ = check_refractory(state.temperature, state.is_refractory)

    # Step 4: 更新峰值
    if state.temperature > state.peak_temperature:
        state.peak_temperature = state.temperature

    return state
