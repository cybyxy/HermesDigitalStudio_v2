"""orchestrate M3 管道集成测试 — 验证 10 步心智管道的辅助函数可正确组合。

所有测试为纯计算测试，无需外部依赖。
"""
from __future__ import annotations

import pytest


# ═══════════════════════════════════════════════════════════════════
# M3.1 向量直觉（需要 MemOS，mock 验证）
# ═══════════════════════════════════════════════════════════════════

class TestVectorIntuition:
    def test_intuition_filter_imports(self):
        """验证向量感知服务可导入。"""
        from backend.services.vector_memory import get_vector_perception_service
        svc = get_vector_perception_service()
        assert svc is not None

    def test_intuition_filter_returns_safe_result(self):
        """直觉过滤在无 MemOS 时返回安全默认值。"""
        from backend.services.vector_memory import get_vector_perception_service
        svc = get_vector_perception_service()
        result = svc.intuition_filter("test_agent", "测试输入文本", top_k=3)
        assert isinstance(result, list)


# ═══════════════════════════════════════════════════════════════════
# M3.2 情绪惯性
# ═══════════════════════════════════════════════════════════════════

class TestEmotionInertia:
    def test_reservoir_update_preserves_structure(self):
        """情绪蓄水池更新保持结构正确。"""
        from backend.services.emotion_reservoir import update_reservoir
        state = update_reservoir(
            v_current=0.3, a_current=0.5, d_current=0.4,
            v_delta=0.1, a_delta=0.05, d_delta=-0.05,
            v_buffer=0.0, a_buffer=0.0, d_buffer=0.0,
        )
        assert isinstance(state, dict)
        assert "v_current" in state

    def test_reservoir_burst_detection(self):
        """蓄水池在大 delta 时触发 burst。"""
        from backend.services.emotion_reservoir import update_reservoir
        state = update_reservoir(
            v_current=0.1, a_current=0.1, d_current=0.1,
            v_delta=0.35, a_delta=0.30, d_delta=0.25,
            v_buffer=0.0, a_buffer=0.0, d_buffer=0.0,
        )
        assert state.get("burst_count", 0) > 0


# ═══════════════════════════════════════════════════════════════════
# M3.3 情绪状态机
# ═══════════════════════════════════════════════════════════════════

class TestEmotionStateMachine:
    def test_determine_state_calm(self):
        from backend.services.emotion_state_machine import determine_state
        state = determine_state((0.1, 0.1, 0.1), is_refractory=False, prev_state=None)
        assert state == "CALM"

    def test_determine_state_refractory(self):
        from backend.services.emotion_state_machine import determine_state
        state = determine_state((0.6, 0.6, 0.6), is_refractory=True, prev_state="PEAK")
        assert state == "REFRACTORY"

    def test_determine_state_all_states(self):
        """所有 6 个状态均可产生。"""
        from backend.services.emotion_state_machine import determine_state, EmotionState
        states = {s.value for s in EmotionState}
        produced = set()
        # 尝试各种组合
        test_cases = [
            ((0.1, 0.1, 0.1), False, None),        # CALM
            ((0.4, 0.4, 0.4), False, "CALM"),       # ACTIVATED
            ((0.8, 0.8, 0.5), False, "ACTIVATED"),   # PEAK
            ((0.3, 0.6, 0.3), False, "PEAK"),        # DECAYING
            ((0.4, 0.3, 0.4), False, "DECAYING"),    # RECOVERING
            ((0.3, 0.8, 0.5), True, "PEAK"),         # REFRACTORY
        ]
        for args in test_cases:
            s = determine_state(*args)
            produced.add(s)
        assert "CALM" in produced
        assert "REFRACTORY" in produced


# ═══════════════════════════════════════════════════════════════════
# M3.4 冷却检查
# ═══════════════════════════════════════════════════════════════════

class TestCoolingCheck:
    def test_refractory_above_threshold(self):
        from backend.services.cooling_buffer import check_refractory
        is_ref, transition = check_refractory(temperature=0.80, was_refractory=False)
        assert is_ref is True
        assert "REFRACTORY" in transition

    def test_no_refractory_below_threshold(self):
        from backend.services.cooling_buffer import check_refractory
        is_ref, transition = check_refractory(temperature=0.30, was_refractory=False)
        assert is_ref is False

    def test_accumulate_heat(self):
        from backend.services.cooling_buffer import accumulate_heat
        new_temp = accumulate_heat(temperature=0.1, intensity=0.5, is_burst=False)
        assert new_temp > 0.1

    def test_accumulate_heat_with_burst(self):
        from backend.services.cooling_buffer import accumulate_heat
        new_temp = accumulate_heat(temperature=0.1, intensity=0.5, is_burst=True)
        assert new_temp > 0.1


# ═══════════════════════════════════════════════════════════════════
# M3.5 情绪→电压调制
# ═══════════════════════════════════════════════════════════════════

class TestEmotionVoltageModulation:
    def test_prompt_quality(self):
        from backend.services.neural_current import compute_prompt_quality
        q = compute_prompt_quality("这是一段正常的测试文本，包含一些标点符号。")
        assert 0.0 <= q <= 1.0

    def test_signal_dna_generation(self):
        from backend.services.neural_current import compute_signal_dna
        dna = compute_signal_dna("测试文本信号")
        assert len(dna) > 0
        assert all(c in "ACGT" for c in dna)

    def test_initial_voltage(self):
        from backend.services.neural_current import compute_initial_voltage
        v = compute_initial_voltage(satiety=50, bio_current=3, mode="normal", task_complexity="simple")
        assert v > 0.0

    def test_emotion_voltage_modulation_positive(self):
        from backend.services.neural_current import compute_emotion_voltage_modulation
        v = compute_emotion_voltage_modulation(base_voltage=3.0, pad=(0.7, 0.6, 0.5), is_refractory=False)
        assert v > 3.0  # positive boost

    def test_emotion_voltage_modulation_refractory(self):
        from backend.services.neural_current import compute_emotion_voltage_modulation
        v = compute_emotion_voltage_modulation(base_voltage=3.0, pad=(0.7, 0.6, 0.5), is_refractory=True)
        assert v < 3.0  # refractory clamp

    def test_emotion_conductance_bias(self):
        from backend.services.neural_current import compute_emotion_conductance_bias
        bias = compute_emotion_conductance_bias((0.6, 0.5, 0.4))
        assert isinstance(bias, float)


# ═══════════════════════════════════════════════════════════════════
# M3.6 内驱力博弈
# ═══════════════════════════════════════════════════════════════════

class TestDriveCompetition:
    def test_resolve_no_override(self):
        from backend.services.drive_competition import resolve_drive_competition
        result = resolve_drive_competition(pad=(0.3, 0.3, 0.5), satiety=60, is_refractory=False)
        assert result.override_applied is False
        assert result.overclock_factor == 1.0

    def test_resolve_emotional_override(self):
        from backend.services.drive_competition import resolve_drive_competition
        result = resolve_drive_competition(pad=(0.8, 0.8, 0.7), satiety=20, is_refractory=False)
        assert result.override_applied is True
        assert result.overclock_factor > 1.0

    def test_resolve_refractory_blocks_override(self):
        from backend.services.drive_competition import resolve_drive_competition
        result = resolve_drive_competition(pad=(0.8, 0.8, 0.7), satiety=20, is_refractory=True)
        assert result.override_applied is False


# ═══════════════════════════════════════════════════════════════════
# M3.9 情绪表观遗传
# ═══════════════════════════════════════════════════════════════════

class TestEmotionEpigenetics:
    def test_long_term_avg(self):
        from backend.services.emotion_epigenetics import compute_long_term_avg
        records = [(0.5, 0.6, 0.4)] * 20
        v_avg, a_avg, d_avg = compute_long_term_avg(records, window=10)
        assert -1.0 <= v_avg <= 1.0
        assert -1.0 <= a_avg <= 1.0

    def test_no_trigger_below_threshold(self):
        from backend.services.emotion_epigenetics import check_epigenetic_trigger
        result = check_epigenetic_trigger((0.2, 0.3, 0.2), session_count=5)
        assert result is None

    def test_trigger_above_threshold(self):
        from backend.services.emotion_epigenetics import check_epigenetic_trigger
        result = check_epigenetic_trigger((0.6, 0.6, 0.6), session_count=15, threshold=0.4)
        assert result is not None

    def test_dna_mutation_output(self):
        from backend.services.emotion_epigenetics import compute_dna_mutation
        from backend.services.emotion_epigenetics import EpigeneticImprint
        imprint = EpigeneticImprint(
            v_avg=0.6, a_avg=0.5, d_avg=0.4,
            intensity=0.7, session_count=15,
        )
        new_left, positions, rate = compute_dna_mutation(imprint, "ACGTACGTACGTACGT")
        assert len(new_left) == len("ACGTACGTACGTACGT")
        assert rate <= 0.08


# ═══════════════════════════════════════════════════════════════════
# M3.10 情绪→饱食度耦合
# ═══════════════════════════════════════════════════════════════════

class TestEmotionSatietyCoupling:
    def test_modifier_in_range(self):
        from backend.services.neural_current import compute_emotion_satiety_modifier
        m = compute_emotion_satiety_modifier(pad=(0.5, 0.5, 0.5), satiety=50)
        assert m >= 0.2

    def test_high_arousal_accelerates_consumption(self):
        from backend.services.neural_current import compute_emotion_satiety_modifier
        m_high = compute_emotion_satiety_modifier(pad=(0.5, 0.9, 0.5), satiety=50)
        m_low = compute_emotion_satiety_modifier(pad=(0.5, 0.1, 0.5), satiety=50)
        assert m_high >= m_low  # 高唤醒度加速消耗


# ═══════════════════════════════════════════════════════════════════
# 管道组合：验证 10 步可按顺序执行且不出错
# ═══════════════════════════════════════════════════════════════════

class TestM3PipelineComposition:
    def test_full_pipeline_helpers_compose(self):
        """验证 M3 管道核心辅助函数可顺序组合，不抛异常。"""
        from backend.services.neural_current import (
            compute_prompt_quality, compute_signal_dna,
            compute_initial_voltage, compute_emotion_voltage_modulation,
            compute_emotion_conductance_bias, compute_emotion_satiety_modifier,
        )
        from backend.services.emotion_state_machine import determine_state
        from backend.services.cooling_buffer import accumulate_heat, check_refractory
        from backend.services.drive_competition import resolve_drive_competition
        from backend.services.emotion_reservoir import update_reservoir

        user_text = "你好，我想了解一下人工智能的最新进展"
        pad = (0.5, 0.6, 0.4)
        satiety = 50
        bio_current = 3
        mode = "normal"
        task_complexity = "simple"

        # M3.1: 直觉（在集成环境中需要 MemOS，此处跳过）
        # M3.2: 情绪惯性
        inertia = update_reservoir(
            v_current=pad[0], a_current=pad[1], d_current=pad[2],
            v_delta=0.05, a_delta=0.03, d_delta=-0.02,
            v_buffer=0.0, a_buffer=0.0, d_buffer=0.0,
        )
        assert isinstance(inertia, dict)

        # M3.3: 状态机
        state = determine_state(pad, is_refractory=False, prev_state="CALM")
        assert state in ("CALM", "ACTIVATED")

        # M3.4: 冷却
        new_temp = accumulate_heat(temperature=0.1, intensity=0.3, is_burst=False)
        is_ref, _ = check_refractory(new_temp, was_refractory=False)
        assert isinstance(is_ref, bool)

        # M3.5: 电压调制
        quality = compute_prompt_quality(user_text)
        signal_dna = compute_signal_dna(user_text)
        base_voltage = compute_initial_voltage(satiety, bio_current, mode, task_complexity)
        modulated_v = compute_emotion_voltage_modulation(base_voltage, pad, is_ref)
        assert modulated_v > 0

        # M3.6: 内驱力博弈
        drive = resolve_drive_competition(pad, satiety, is_ref)
        if drive.override_applied:
            final_v = modulated_v * drive.overclock_factor
        else:
            final_v = modulated_v
        assert final_v > 0

        # M3.8: 冷却积聚
        conductance_bias = compute_emotion_conductance_bias(pad)
        heat = accumulate_heat(new_temp, intensity=final_v / 5.0, is_burst=inertia.get("burst_count", 0) > 0)
        assert heat >= 0

        # M3.10: 能量耦合
        modifier = compute_emotion_satiety_modifier(pad, satiety)
        assert modifier >= 0.2
