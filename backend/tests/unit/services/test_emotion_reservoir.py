"""情绪蓄水池单元测试"""
from __future__ import annotations

from backend.services.emotion_reservoir import (
    EmotionReservoirState,
    smooth_update,
    accumulate_buffer,
    apply_homeostasis,
    shift_baseline,
    update_reservoir,
    INERTIA_RATE,
    BURST_THRESHOLD,
    BURST_RELEASE_RATIO,
    HOMEOSTASIS_RATE,
    BASELINE_SHIFT_RATE,
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


class TestSmoothUpdate:
    def test_convergence(self):
        """指数平滑应向目标收敛。"""
        v = 0.0
        for _ in range(20):
            v = smooth_update(v, 1.0)
        assert v > 0.9  # 逼近 1.0

    def test_no_change(self):
        """当前值等于目标值时不变。"""
        assert smooth_update(0.5, 0.5) == 0.5

    def test_full_step(self):
        """rate=1.0 时一步到达目标。"""
        assert smooth_update(0.0, 1.0, rate=1.0) == 1.0

    def test_zero_rate(self):
        """rate=0.0 时保持不变。"""
        assert smooth_update(0.3, 1.0, rate=0.0) == 0.3


class TestAccumulateBuffer:
    def test_below_threshold(self):
        new, burst, released = accumulate_buffer(0.0, 0.1)
        assert new == 0.1
        assert burst is False
        assert released == 0.0

    def test_at_threshold(self):
        new, burst, released = accumulate_buffer(0.0, BURST_THRESHOLD)
        assert burst is True
        assert released > 0.0
        assert new == _approx(BURST_THRESHOLD * (1 - BURST_RELEASE_RATIO))

    def test_above_threshold(self):
        new, burst, released = accumulate_buffer(0.0, 0.5)
        assert burst is True
        assert released > released * 0  # non-zero
        # 释放后剩余 = (buffer+delta) * (1 - release_ratio)
        assert abs(new) < abs(0.5)

    def test_negative_burst(self):
        """负向累积也可触发爆发。"""
        new, burst, released = accumulate_buffer(0.0, -BURST_THRESHOLD - 0.01)
        assert burst is True
        assert released > 0.0


class TestHomeostasis:
    def test_no_elapsed(self):
        assert apply_homeostasis(0.5, 0.0, 0.0) == 0.5

    def test_regression_toward_baseline(self):
        """正值应向零基线回归。"""
        v = apply_homeostasis(0.5, 0.0, 10.0)
        assert v < 0.5

    def test_clamp(self):
        """长时间不超 1.0 权重的回归。"""
        v = apply_homeostasis(1.0, 0.0, 1000.0)
        assert v >= 0.0


class TestShiftBaseline:
    def test_no_shift(self):
        assert shift_baseline(0.0, 0.0) == 0.0

    def test_slow_shift(self):
        """基线漂移应非常缓慢。"""
        b = shift_baseline(0.0, 1.0)
        assert b == _approx(BASELINE_SHIFT_RATE)


class TestUpdateReservoir:
    def test_basic_update(self):
        state = EmotionReservoirState()
        new_state, events = update_reservoir(state, (0.2, 0.1, 0.0))
        assert new_state.v_current > 0.0
        assert new_state.a_current > 0.0
        assert len(events) == 0

    def test_burst_trigger(self):
        state = EmotionReservoirState()
        # 大 delta 触发爆发
        new_state, events = update_reservoir(state, (0.5, 0.0, 0.0))
        assert len(events) > 0
        assert new_state.burst_count >= 1

    def test_with_homeostasis(self):
        state = EmotionReservoirState(v_current=0.5, v_baseline=0.0)
        new_state, _ = update_reservoir(state, (0.0, 0.0, 0.0), elapsed_hours=5.0)
        assert new_state.v_current < 0.5  # 向基线回归
