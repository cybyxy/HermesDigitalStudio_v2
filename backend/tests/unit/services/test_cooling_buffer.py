"""冷却缓冲区单元测试"""
from __future__ import annotations

from backend.services.cooling_buffer import (
    CoolingBufferState,
    accumulate_heat,
    natural_cooldown,
    check_refractory,
    can_activate,
    update_cooling_state,
    TEMPERATURE_MAX,
    REFRACTORY_THRESHOLD,
    REFRACTORY_EXIT,
    BURST_COOLDOWN_EXTRA,
    ACTIVATION_HEAT_PER_RUN,
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


class TestAccumulateHeat:
    def test_basic_heat(self):
        t = accumulate_heat(0.0, 1.0)
        assert t == _approx(ACTIVATION_HEAT_PER_RUN)

    def test_with_burst(self):
        t = accumulate_heat(0.0, 1.0, is_burst=True)
        assert t == _approx(ACTIVATION_HEAT_PER_RUN + BURST_COOLDOWN_EXTRA)

    def test_no_intensity(self):
        t = accumulate_heat(0.0, 0.0)
        assert t == 0.0

    def test_clamp_to_max(self):
        t = accumulate_heat(0.95, 1.0, is_burst=True)
        assert t == TEMPERATURE_MAX


class TestNaturalCooldown:
    def test_basic_cooling(self):
        t = natural_cooldown(0.5, 10.0)
        assert t == _approx(0.5 - 0.05 * 10.0)

    def test_no_below_zero(self):
        t = natural_cooldown(0.01, 10.0)
        assert t == 0.0

    def test_no_elapsed(self):
        assert natural_cooldown(0.5, 0.0) == 0.5


class TestCheckRefractory:
    def test_enter_refractory(self):
        is_ref, transition = check_refractory(REFRACTORY_THRESHOLD, False)
        assert is_ref is True
        assert transition == "enter"

    def test_stay_refractory(self):
        is_ref, transition = check_refractory(REFRACTORY_THRESHOLD, True)
        assert is_ref is True
        assert transition == "stay"

    def test_exit_refractory(self):
        is_ref, transition = check_refractory(REFRACTORY_EXIT, True)
        assert is_ref is False
        assert transition == "exit"

    def test_no_transition(self):
        is_ref, transition = check_refractory(0.5, False)
        assert is_ref is False
        assert transition == "none"


class TestCanActivate:
    def test_cold_can_activate(self):
        assert can_activate(0.0, False) is True

    def test_hot_cannot_activate(self):
        assert can_activate(REFRACTORY_THRESHOLD, False) is False

    def test_refractory_cannot_activate(self):
        assert can_activate(0.5, True) is False  # 不应期，温度高于退出阈值

    def test_refractory_cooled_can_activate(self):
        assert can_activate(REFRACTORY_EXIT, True) is True


class TestUpdateCoolingState:
    def test_full_cycle(self):
        state = CoolingBufferState()
        # 高强度活动
        state = update_cooling_state(state, intensity=1.0, is_burst=False, elapsed_minutes=0.0)
        assert state.temperature > 0.0

    def test_cooling_then_activate(self):
        state = CoolingBufferState(temperature=0.5)
        # 先冷却
        state = update_cooling_state(state, intensity=0.0, is_burst=False, elapsed_minutes=10.0)
        assert state.temperature == 0.0
        # 再加热
        state = update_cooling_state(state, intensity=1.0, is_burst=True, elapsed_minutes=0.0)
        assert state.temperature > 0.0

    def test_peak_tracking(self):
        state = CoolingBufferState()
        state = update_cooling_state(state, intensity=1.0, is_burst=True, elapsed_minutes=0.0)
        peak1 = state.peak_temperature
        state = update_cooling_state(state, intensity=0.0, is_burst=False, elapsed_minutes=10.0)
        assert state.peak_temperature == peak1  # 峰值应保持
