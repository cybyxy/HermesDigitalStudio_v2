"""内驱力博弈 (Drive Competition) — 生理驱动 vs 情绪驱动

纯计算模块，不依赖 I/O。

情绪驱动触发条件: valence > 0.5 AND arousal > 0.5
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class DriveResult:
    """驱力竞争结果"""

    source: str  # "physiological" | "emotional"
    override_applied: bool
    overclock_factor: float  # 1.0 ~ 1.35
    ceiling_voltage: float


def _compute_physiological_ceiling(satiety: int) -> float:
    """基于饱食度的生理电压上限。

    satiety:  0-100
    return:   0.3 ~ 2.5
    """
    # 饥饿 (0-30): 高上限 2.0-2.5，鼓励探索
    if satiety <= 30:
        return 2.5 - (satiety / 30) * 0.5
    # 适中 (30-70): 正常范围
    elif satiety <= 70:
        return 2.0 - ((satiety - 30) / 40) * 1.0
    # 饱足 (70-100): 低压上限
    else:
        return max(0.3, 1.0 - ((satiety - 70) / 30) * 0.7)


def resolve_drive_competition(
    pad: tuple[float, float, float],
    satiety: int,
    is_refractory: bool,
) -> DriveResult:
    """解析生理驱动与情绪驱动的竞争。

    Args:
        pad: (valence, arousal, dominance)
        satiety: 饱食度 0-100
        is_refractory: 是否处于不应期

    Returns:
        DriveResult 竞争结果
    """
    v, a, _d = pad
    phys_ceiling = _compute_physiological_ceiling(satiety)

    # 不应期强制回归生理驱动
    if is_refractory:
        return DriveResult(
            source="physiological",
            override_applied=False,
            overclock_factor=1.0,
            ceiling_voltage=phys_ceiling,
        )

    # 情绪驱动触发条件
    if v > 0.5 and a > 0.5:
        # Overclock factor: 1.0 + (v-0.5)*0.5 + (a-0.5)*0.3
        # Range: 1.0 ~ 1.35
        overclock = 1.0 + (v - 0.5) * 0.5 + (a - 0.5) * 0.3
        overclock = min(1.35, overclock)

        # 饥饿放大 (satiety < 30)
        if satiety < 30:
            hunger_factor = 1.0 + (30 - satiety) / 30 * 0.15
            overclock = min(1.35, overclock * hunger_factor)

        # 情绪驱动可突破生理上限
        emotional_ceiling = phys_ceiling * overclock

        return DriveResult(
            source="emotional",
            override_applied=True,
            overclock_factor=overclock,
            ceiling_voltage=emotional_ceiling,
        )

    # 纯生理驱动
    return DriveResult(
        source="physiological",
        override_applied=False,
        overclock_factor=1.0,
        ceiling_voltage=phys_ceiling,
    )
