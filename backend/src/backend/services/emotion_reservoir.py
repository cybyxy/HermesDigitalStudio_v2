"""情绪蓄水池 (Emotion Reservoir) — 指数平滑 + 缓冲区爆发 + 稳态回归

纯计算模块，不依赖 I/O。
"""
from __future__ import annotations

from dataclasses import dataclass

# 指数平滑率（日常小步更新）
INERTIA_RATE = 0.15

# 缓冲区爆发阈值
BURST_THRESHOLD = 0.30

# 爆发时释放累积 delta 的比例
BURST_RELEASE_RATIO = 0.50

# 每小时稳态回归量
HOMEOSTASIS_RATE = 0.01

# 长期基线漂移率
BASELINE_SHIFT_RATE = 0.001


def smooth_update(current: float, target: float, rate: float = INERTIA_RATE) -> float:
    """指数平滑更新: new = current × (1-rate) + target × rate"""
    return current * (1.0 - rate) + target * rate


def accumulate_buffer(
    buffer_value: float, delta: float, threshold: float = BURST_THRESHOLD
) -> tuple[float, bool, float]:
    """累积缓冲区，超过阈值时触发爆发释放。

    Args:
        buffer_value: 当前缓冲区值 (可为正或负)
        delta: 新增情绪变化量
        threshold: 爆发阈值

    Returns:
        (new_buffer, is_burst, released)
        - new_buffer: 更新后的缓冲区值
        - is_burst: 是否触发了爆发
        - released: 实际释放的绝对值
    """
    new_buffer = buffer_value + delta

    if abs(new_buffer) >= threshold:
        # 爆发释放 BURST_RELEASE_RATIO 比例的累积 delta
        released = abs(new_buffer) * BURST_RELEASE_RATIO
        new_buffer = new_buffer * (1.0 - BURST_RELEASE_RATIO)
        return new_buffer, True, released

    return new_buffer, False, 0.0


def apply_homeostasis(
    current: float, baseline: float, elapsed_hours: float
) -> float:
    """稳态回归：向基线移动 HOMEOSTASIS_RATE * hours。

    Args:
        current: 当前值
        baseline: 基线值（趋向目标）
        elapsed_hours: 已过小时数

    Returns:
        回归后的值
    """
    rate = min(1.0, HOMEOSTASIS_RATE * elapsed_hours)
    return smooth_update(current, baseline, rate)


def shift_baseline(
    baseline: float, long_term_avg: float, rate: float = BASELINE_SHIFT_RATE
) -> float:
    """长期情绪均值缓慢漂移基线（性格演化）。

    Args:
        baseline: 当前基线
        long_term_avg: 长期情绪均值
        rate: 漂移率

    Returns:
        新基线值
    """
    return smooth_update(baseline, long_term_avg, rate)


@dataclass
class EmotionReservoirState:
    """情绪蓄水池完整状态（三个 PAD 维度）。"""

    v_current: float = 0.0
    v_buffer: float = 0.0
    v_baseline: float = 0.0

    a_current: float = 0.0
    a_buffer: float = 0.0
    a_baseline: float = 0.0

    d_current: float = 0.0
    d_buffer: float = 0.0
    d_baseline: float = 0.0

    burst_count: int = 0


def update_reservoir(
    state: EmotionReservoirState,
    delta: tuple[float, float, float],
    elapsed_hours: float = 0.0,
) -> tuple[EmotionReservoirState, list[str]]:
    """一次完整的蓄水池更新循环。

    1. delta 进入 buffer 累积
    2. 当前值通过指数平滑小步更新
    3. buffer 累积超阈值 → 爆发释放
    4. 稳态回归

    Args:
        state: 当前蓄水池状态
        delta: (v_delta, a_delta, d_delta) 情绪变化量
        elapsed_hours: 从上一次更新到现在的小时数

    Returns:
        (new_state, events) — events 包含触发的爆发事件描述
    """
    dv, da, dd = delta
    events: list[str] = []

    for dim, d in [("v", dv), ("a", da), ("d", dd)]:
        current = getattr(state, f"{dim}_current")
        buff = getattr(state, f"{dim}_buffer")
        baseline = getattr(state, f"{dim}_baseline")

        # Step 1: 缓冲累积 + 爆发检查
        new_buff, burst, released = accumulate_buffer(buff, d)
        setattr(state, f"{dim}_buffer", new_buff)

        if burst:
            state.burst_count += 1
            events.append(f"burst_{dim}:{released:.3f}")

        # Step 2: 指数平滑小步更新（使用目标 = 当前 + delta）
        target = current + d
        new_current = smooth_update(current, target)
        setattr(state, f"{dim}_current", new_current)

        # Step 4: 稳态回归
        if elapsed_hours > 0:
            new_current = apply_homeostasis(new_current, baseline, elapsed_hours)
            setattr(state, f"{dim}_current", new_current)

    return state, events
