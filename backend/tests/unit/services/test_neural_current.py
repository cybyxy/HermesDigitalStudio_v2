"""神经电流计算引擎单元测试"""
from __future__ import annotations


class _approx:
    """pytest.approx 的轻量替代"""
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


from backend.services.neural_current import (
    compute_initial_voltage,
    compute_conduction_depth,
    compute_activation_voltage,
    check_hedonic_override,
    accumulate_joule_heat,
    compute_metabolic_waste,
    compute_prompt_quality,
    # 情绪桥接
    compute_emotion_voltage_modulation,
    compute_emotion_conductance_bias,
    compute_emotion_satiety_modifier,
    compute_emotion_hedonic_threshold,
    # 完整管线
    compute_full_voltage_pipeline,
    # 衰减
    compute_joule_heat_decay,
    compute_metabolic_waste_decay,
    # 常量
    ConductionResult,
    VoltageResult,
    MIN_VOLTAGE,
    HEDONIC_THRESHOLD_QUALITY,
    HEDONIC_THRESHOLD_SATIETY,
)


# ═══════════════ 核心电流测试 ═══════════════


class TestInitialVoltage:
    def test_normal_mode(self):
        v = compute_initial_voltage(70, 5, "normal", "medium")
        assert v > 0.0
        # 70 → satiety_mul=1.0, 5 → bio_mul=1.5, medium → 1.0 → 1.5
        assert v == _approx(1.5)

    def test_power_save_mode(self):
        v = compute_initial_voltage(20, 2, "power_save", "simple")
        # 20 → 1.5 + (30-20)/40 = 1.75, *0.3 = 0.525
        # 2 → 1.0, simple → 0.8 → 0.42
        assert v < 1.0

    def test_surge_mode(self):
        v = compute_initial_voltage(50, 8, "surge", "large")
        # 50 → 1.0 + (60-50)/60 = 1.167, *1.5 = 1.75
        # 8 → 2.0, large → 1.5 → 5.25
        assert v > 2.0

    def test_starving_mode(self):
        v = compute_initial_voltage(5, 10, "normal", "idle")
        # 5 → 2.5, 10 → 3.0, idle → 0.5 → 3.75
        assert v > 2.0

    def test_full_mode(self):
        v = compute_initial_voltage(95, 3, "normal", "medium")
        # 95 → 0.7 - (95-85)/50 = 0.5
        # 3 → 1.0, medium → 1.0 → 0.5
        assert v < 1.0


class TestConductionDepth:
    def test_full_conduction(self):
        """电压足够高时应该传导所有边，但受 HOP_RESISTANCE 衰减制约。"""
        result = compute_conduction_depth(10.0, [0.9, 0.8, 0.7, 0.6, 0.5])
        # HOP_RESISTANCE=1.0, MIN_VOLTAGE=0.1 → 10V 约传导 3 跳
        assert result.max_depth >= 2
        assert len(result.decay_curve) == result.max_depth + 1

    def test_early_termination(self):
        """电压不足时应该提前终止。"""
        result = compute_conduction_depth(0.5, [0.9, 0.8])
        # hop0: 0.5*0.9/(1+1*1) = 0.225
        # hop1: 0.225*0.8/(1+1*2) = 0.06 < 0.1 → STOP
        assert result.can_continue is False
        assert result.max_depth == 1

    def test_decay_curve_monotonic(self):
        """电压应单调递减。"""
        result = compute_conduction_depth(5.0, [0.9, 0.8, 0.7, 0.6, 0.5])
        for i in range(len(result.decay_curve) - 1):
            assert result.decay_curve[i] >= result.decay_curve[i + 1]

    def test_low_resistance_penalty(self):
        """低权重边额外衰减。"""
        result_low = compute_conduction_depth(10.0, [0.15, 0.8])
        result_high = compute_conduction_depth(10.0, [0.25, 0.8])
        # 第一跳低权重应该有额外衰减
        assert result_low.decay_curve[0] < result_high.decay_curve[0]

    def test_empty_weights(self):
        result = compute_conduction_depth(10.0, [])
        assert result.max_depth == 0
        assert result.can_continue is True


class TestActivationVoltage:
    def test_full_activation(self):
        v = compute_activation_voltage(1.0, 1.0, 5.0)
        assert v == 5.0 * 1.0 * 1.5  # 0.5 + 1.0 = 1.5

    def test_no_expression(self):
        v = compute_activation_voltage(1.0, 0.0, 5.0)
        assert v == 5.0 * 1.0 * 0.5  # 0.5 + 0.0 = 0.5


class TestHedonicOverride:
    def test_triggered(self):
        is_override, multiplier = check_hedonic_override(90, 0.9)
        assert is_override is True
        assert multiplier == 2.0

    def test_not_triggered_quality(self):
        is_override, multiplier = check_hedonic_override(90, 0.5)
        assert is_override is False

    def test_not_triggered_satiety(self):
        is_override, multiplier = check_hedonic_override(50, 0.9)
        assert is_override is False


class TestJouleHeat:
    def test_no_heat(self):
        h = accumulate_joule_heat([], 0)
        assert h == 0.0

    def test_high_weight_low_heat(self):
        h = accumulate_joule_heat([0.9, 0.9, 0.9], 3)
        assert h > 0.0
        assert h < 0.5  # 高权重低产热

    def test_low_weight_high_heat(self):
        h_low = accumulate_joule_heat([0.1, 0.1, 0.1], 3)
        h_high = accumulate_joule_heat([0.9, 0.9, 0.9], 3)
        assert h_low > h_high  # 低权重产热更多


class TestMetabolicWaste:
    def test_no_waste(self):
        w = compute_metabolic_waste(0, 70)
        assert w == 0.0

    def test_high_waste(self):
        w = compute_metabolic_waste(3, 90)
        assert w > 0.2


class TestPromptQuality:
    def test_empty(self):
        assert compute_prompt_quality("") == 0.0
        assert compute_prompt_quality("   ") == 0.0

    def test_short(self):
        q = compute_prompt_quality("hi")
        # "hi": length_score=0.3 + vocab_score=0.3 = 0.6
        assert 0.3 <= q <= 0.7

    def test_detailed(self):
        long_text = "请帮我分析一下这个复杂的前端架构问题 " * 10
        q = compute_prompt_quality(long_text)
        assert q > 0.6

    def test_with_questions(self):
        q = compute_prompt_quality("你能帮我解决这个问题吗？这个bug怎么修？请告诉我具体步骤")
        assert q > 0.4


class TestDecay:
    def test_joule_heat_decay(self):
        assert compute_joule_heat_decay(1.0, 0) == 1.0
        assert compute_joule_heat_decay(1.0, 1) < 1.0
        assert compute_joule_heat_decay(1.0, 10) < 0.4

    def test_metabolic_waste_decay(self):
        assert compute_metabolic_waste_decay(1.0, 0) == 1.0
        assert compute_metabolic_waste_decay(1.0, 1) < 1.0


# ═══════════════ 情绪→神经电流桥接测试 ═══════════════


class TestEmotionVoltageModulation:
    def test_neutral_emotion(self):
        """中性情绪不改变电压。"""
        v = compute_emotion_voltage_modulation(5.0, (0.0, 0.0, 0.0), False)
        assert v == _approx(5.0)

    def test_positive_emotion_boost(self):
        """正面情绪提升电压。"""
        v_neutral = compute_emotion_voltage_modulation(5.0, (0.0, 0.0, 0.0), False)
        v_positive = compute_emotion_voltage_modulation(5.0, (0.8, 0.6, 0.5), False)
        assert v_positive > v_neutral

    def test_negative_emotion_dampen(self):
        """负面情绪降低电压。"""
        v_neutral = compute_emotion_voltage_modulation(5.0, (0.0, 0.0, 0.0), False)
        v_negative = compute_emotion_voltage_modulation(5.0, (-0.8, 0.3, -0.5), False)
        assert v_negative < v_neutral

    def test_refractory_override(self):
        """不应期强制低压。"""
        v = compute_emotion_voltage_modulation(5.0, (0.8, 0.8, 0.8), True)
        assert v == _approx(5.0 * 0.30)

    def test_clamp_bounds(self):
        """电压调制在 [0.5*base, 1.5*base] 范围内。"""
        # 极端正面
        v = compute_emotion_voltage_modulation(5.0, (1.0, 1.0, 1.0), False)
        assert v <= 5.0 * 1.5
        # 极端负面
        v = compute_emotion_voltage_modulation(5.0, (-1.0, 0.0, -1.0), False)
        assert v >= 5.0 * 0.5


class TestEmotionConductanceBias:
    def test_positive_reduces_resistance(self):
        bias = compute_emotion_conductance_bias((0.8, 0.0, 0.0))
        assert bias < 0  # 负偏置 = 降低电阻

    def test_negative_increases_resistance(self):
        bias = compute_emotion_conductance_bias((-0.8, 0.0, 0.0))
        assert bias > 0  # 正偏置 = 增加电阻

    def test_neutral_no_bias(self):
        bias = compute_emotion_conductance_bias((0.0, 0.0, 0.0))
        assert bias == 0.0


class TestEmotionSatietyModifier:
    def test_normal(self):
        """中性情绪 + 高饱食度稳定缓冲 → 修正略低于 1.0"""
        m = compute_emotion_satiety_modifier((0.0, 0.0, 0.0), 70)
        # neutral → 0 penalty, stability_bonus = 0.075 → 0.925
        assert m < 1.0
        assert m > 0.9

    def test_negative_accelerates(self):
        m = compute_emotion_satiety_modifier((-0.8, 0.0, 0.0), 70)
        assert m > 1.0

    def test_high_satiety_stability(self):
        m_unstable = compute_emotion_satiety_modifier((-0.8, 0.0, 0.0), 50)
        m_stable = compute_emotion_satiety_modifier((-0.8, 0.0, 0.0), 90)
        assert m_stable < m_unstable  # 高饱食度缓冲

    def test_minimum(self):
        m = compute_emotion_satiety_modifier((-1.0, 1.0, -1.0), 30)
        assert m >= 0.2


class TestEmotionHedonicThreshold:
    def test_below_threshold(self):
        assert compute_emotion_hedonic_threshold((0.4, 0.4, 0.0), 70) is False

    def test_above_threshold(self):
        assert compute_emotion_hedonic_threshold((0.6, 0.6, 0.0), 70) is True

    def test_only_valence_high(self):
        assert compute_emotion_hedonic_threshold((0.8, 0.3, 0.0), 70) is False

    def test_only_arousal_high(self):
        assert compute_emotion_hedonic_threshold((0.3, 0.8, 0.0), 70) is False


class TestFullPipeline:
    def test_normal_pipeline(self):
        result = compute_full_voltage_pipeline(
            satiety=70, bio_current=5, mode="normal",
            task_complexity="medium",
            pad=(0.2, 0.3, 0.1),
            is_refractory=False,
            prompt_quality=0.5,
        )
        assert result.base_voltage > 0
        assert result.modulated_voltage > 0
        assert result.overclock_applied is False
        assert result.hedonic_override is False

    def test_refractory_pipeline(self):
        result = compute_full_voltage_pipeline(
            satiety=70, bio_current=5, mode="normal",
            task_complexity="medium",
            pad=(0.8, 0.8, 0.8),
            is_refractory=True,
            prompt_quality=0.5,
        )
        # 不应期时调制电压应为 base * 0.3
        assert result.modulated_voltage == _approx(result.base_voltage * 0.30)

    def test_overclock_pipeline(self):
        result = compute_full_voltage_pipeline(
            satiety=70, bio_current=5, mode="normal",
            task_complexity="medium",
            pad=(0.8, 0.8, 0.8),
            is_refractory=False,
            prompt_quality=0.5,
            overclock_factor=1.3,
        )
        assert result.overclock_applied is True
        assert result.overclock_factor == 1.3
        assert result.modulated_voltage > result.base_voltage
