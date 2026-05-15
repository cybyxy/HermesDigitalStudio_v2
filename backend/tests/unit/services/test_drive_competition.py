"""内驱力博弈单元测试"""
from __future__ import annotations

from backend.services.drive_competition import (
    DriveResult,
    resolve_drive_competition,
)


class _approx:
    def __init__(self, expected, rel=1e-6, abs=1e-12):
        self.expected = expected
        self.rel = rel
        self.abs_val = abs

    def __eq__(self, other):
        return abs(other - self.expected) <= max(
            self.rel * max(abs(other), abs(self.expected)), self.abs_val
        )

    def __ne__(self, other):
        return not self.__eq__(other)


class TestPhysiologicalDrive:
    def test_low_satiety_high_ceiling(self):
        """饥饿时电压上限偏高。"""
        result = resolve_drive_competition((0.0, 0.0, 0.0), 10, False)
        assert result.source == "physiological"
        assert result.override_applied is False
        assert result.ceiling_voltage > 2.0

    def test_high_satiety_low_ceiling(self):
        """饱足时电压上限偏低。"""
        result = resolve_drive_competition((0.0, 0.0, 0.0), 90, False)
        assert result.ceiling_voltage < 1.0

    def test_normal_satiety(self):
        result = resolve_drive_competition((0.0, 0.0, 0.0), 50, False)
        assert 1.0 <= result.ceiling_voltage <= 2.0


class TestEmotionalDrive:
    def test_trigger_emotional_override(self):
        """v>0.5 AND a>0.5 触发情绪驱动。"""
        result = resolve_drive_competition((0.8, 0.7, 0.0), 50, False)
        assert result.source == "emotional"
        assert result.override_applied is True
        assert result.overclock_factor > 1.0

    def test_overclock_factor_bounds(self):
        """overclock 在 [1.0, 1.35] 范围内。"""
        result = resolve_drive_competition((1.0, 1.0, 0.0), 50, False)
        assert 1.0 < result.overclock_factor <= 1.35

    def test_only_valence_not_enough(self):
        """仅 valence>0.5 不触发。"""
        result = resolve_drive_competition((0.8, 0.3, 0.0), 50, False)
        assert result.source == "physiological"

    def test_only_arousal_not_enough(self):
        """仅 arousal>0.5 不触发。"""
        result = resolve_drive_competition((0.3, 0.8, 0.0), 50, False)
        assert result.source == "physiological"


class TestRefractoryOverride:
    def test_refractory_forces_physiological(self):
        """不应期强制回归生理驱动。"""
        result = resolve_drive_competition((0.9, 0.9, 0.0), 50, True)
        assert result.source == "physiological"
        assert result.override_applied is False
        assert result.overclock_factor == 1.0


class TestHungerAmplification:
    def test_hunger_amplifies_emotional(self):
        """satiety<30 时饥饿放大情绪驱动。"""
        result_normal = resolve_drive_competition((0.8, 0.7, 0.0), 50, False)
        result_hungry = resolve_drive_competition((0.8, 0.7, 0.0), 10, False)
        assert result_hungry.overclock_factor >= result_normal.overclock_factor
