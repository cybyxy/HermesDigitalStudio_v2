"""情绪状态机单元测试"""
from __future__ import annotations

from backend.services.emotion_state_machine import (
    EmotionState,
    determine_state,
)


class TestTransitions:
    def test_calm_to_activated(self):
        state = determine_state((0.4, 0.4, 0.0), False, EmotionState.CALM)
        assert state == EmotionState.ACTIVATED

    def test_calm_stays_calm(self):
        """低情绪应保持 CALM。"""
        state = determine_state((0.2, 0.1, 0.0), False, EmotionState.CALM)
        assert state == EmotionState.CALM

    def test_activated_to_peak(self):
        state = determine_state((0.7, 0.6, 0.0), False, EmotionState.ACTIVATED)
        assert state == EmotionState.PEAK

    def test_activated_stays_activated(self):
        """不够高时应保持 ACTIVATED。"""
        state = determine_state((0.4, 0.4, 0.0), False, EmotionState.ACTIVATED)
        assert state == EmotionState.ACTIVATED

    def test_peak_to_decaying(self):
        """两帧下降应从 PEAK → DECAYING。"""
        state = determine_state(
            (0.3, 0.3, 0.0), False, EmotionState.PEAK,
            prev_pad=(0.7, 0.6, 0.0),
        )
        assert state == EmotionState.DECAYING

    def test_peak_no_decay_if_not_dropping(self):
        """未下降应保持 PEAK。"""
        state = determine_state(
            (0.8, 0.7, 0.0), False, EmotionState.PEAK,
            prev_pad=(0.7, 0.6, 0.0),
        )
        assert state == EmotionState.PEAK

    def test_decaying_to_recovering(self):
        state = determine_state((0.2, 0.2, 0.0), False, EmotionState.DECAYING)
        assert state == EmotionState.RECOVERING

    def test_decaying_stays_decaying(self):
        state = determine_state((0.4, 0.4, 0.0), False, EmotionState.DECAYING)
        assert state == EmotionState.DECAYING

    def test_recovering_to_calm(self):
        state = determine_state((0.1, 0.1, 0.0), False, EmotionState.RECOVERING)
        assert state == EmotionState.CALM

    def test_refractory_override(self):
        """任何状态遇到不应期应立即进入 REFRACTORY。"""
        state = determine_state((0.8, 0.8, 0.0), True, EmotionState.ACTIVATED)
        assert state == EmotionState.REFRACTORY

    def test_refractory_to_recovering(self):
        """从不应期恢复应进入 RECOVERING。"""
        state = determine_state((0.2, 0.2, 0.0), False, EmotionState.REFRACTORY)
        assert state == EmotionState.RECOVERING
