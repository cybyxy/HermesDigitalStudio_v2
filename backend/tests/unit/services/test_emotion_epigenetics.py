"""情绪表观遗传单元测试"""
from __future__ import annotations

from backend.services.emotion_epigenetics import (
    EpigeneticImprint,
    compute_long_term_avg,
    check_epigenetic_trigger,
    compute_dna_mutation,
    EPIGENETIC_THRESHOLD,
    MAX_LEFT_CHAIN_MUTATION,
    MIN_SESSIONS,
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


class TestLongTermAvg:
    def test_empty(self):
        v, a, d = compute_long_term_avg([])
        assert v == 0.0 and a == 0.0 and d == 0.0

    def test_single_entry(self):
        v, a, d = compute_long_term_avg([(0.5, 0.3, 0.1)])
        assert v == 0.5 and a == 0.3 and d == 0.1

    def test_weighted_recent(self):
        """近期应权重大于远期。"""
        history = [(0.0, 0.0, 0.0)] * 9 + [(1.0, 1.0, 1.0)]
        v, a, d = compute_long_term_avg(history)
        # 10个记录: 9×0 + 1×1, 近期(最后一个)权重最高
        # 加权平均 ≈ (1.0*1.0)/(0.1+0.2+...+1.0) = 1.0/5.5 ≈ 0.18
        # 单一近期高值不能完全压倒远期的零值
        assert v > 0.1

    def test_window_truncation(self):
        """超过 window 的历史被截断。"""
        history = [(0.0, 0.0, 0.0)] * 90 + [(1.0, 1.0, 1.0)] * 10
        v, a, d = compute_long_term_avg(history, window=10)
        assert v == _approx(1.0)


class TestEpigeneticTrigger:
    def test_insufficient_sessions(self):
        """不足 MIN_SESSIONS 条记录不应触发。"""
        avg = (0.8, 0.8, 0.8)
        imprint = check_epigenetic_trigger(avg, session_count=5)
        assert imprint is None

    def test_below_threshold(self):
        """强度不足不应触发。"""
        avg = (0.4, 0.4, 0.4)
        imprint = check_epigenetic_trigger(avg, session_count=MIN_SESSIONS)
        assert imprint is None

    def test_triggered(self):
        """高强度 + 足够次数 = 触发。"""
        avg = (0.7, 0.7, 0.7)
        imprint = check_epigenetic_trigger(avg, session_count=MIN_SESSIONS)
        assert imprint is not None
        assert imprint.is_triggered is True
        assert imprint.mutation_rate > 0

    def test_mutation_rate_capped(self):
        """突变率不超过 MAX_LEFT_CHAIN_MUTATION。"""
        avg = (1.0, 1.0, 1.0)  # 极端强度
        imprint = check_epigenetic_trigger(avg, session_count=MIN_SESSIONS)
        assert imprint.mutation_rate <= MAX_LEFT_CHAIN_MUTATION


class TestDNAMutation:
    def test_basic_mutation(self):
        imprint = EpigeneticImprint(
            v_long_term=0.8, a_long_term=0.3, d_long_term=0.1,
            intensity=0.7, session_count=20,
            mutation_rate=MAX_LEFT_CHAIN_MUTATION, is_triggered=True,
        )
        left = "0123012301230123"  # 16 bases
        new_left, positions, ratio = compute_dna_mutation(imprint, left)
        assert len(positions) > 0
        assert ratio <= MAX_LEFT_CHAIN_MUTATION
        assert len(new_left) == len(left)
        # 变异位应不同
        for pos in positions:
            assert new_left[pos] != left[pos]

    def test_mutation_with_string_bases(self):
        """支持 A/C/G/T 字符编码。"""
        imprint = EpigeneticImprint(
            v_long_term=0.8, a_long_term=0.3, d_long_term=0.1,
            intensity=0.7, session_count=20,
            mutation_rate=MAX_LEFT_CHAIN_MUTATION, is_triggered=True,
        )
        left = "ACGTACGTACGTACGT"
        new_left, positions, ratio = compute_dna_mutation(imprint, left)
        assert len(new_left) == len(left)
        assert set(new_left).issubset({"0", "1", "2", "3"})

    def test_negative_emotion_direction(self):
        """负向情绪应产生 -1 方向偏移。"""
        imprint = EpigeneticImprint(
            v_long_term=-0.8, a_long_term=-0.3, d_long_term=-0.1,
            intensity=0.7, session_count=20,
            mutation_rate=MAX_LEFT_CHAIN_MUTATION, is_triggered=True,
        )
        left = "1111111111111111"  # All C (1)
        new_left, positions, ratio = compute_dna_mutation(imprint, left)
        for pos in positions:
            # 负向: pos 处碱基应变为 0 (A)
            assert new_left[pos] == "0"

    def test_no_mutation_with_minimal_rate(self):
        """minimal rate 下至少突变 1 位（需要足够长的链）。"""
        imprint = EpigeneticImprint(
            v_long_term=0.6, a_long_term=0.6, d_long_term=0.6,
            intensity=0.6, session_count=20,
            mutation_rate=0.001, is_triggered=True,
        )
        # 使用足够长的链确保至少有 1 个变异位
        left = "0123012301230123"  # 16 bases
        new_left, positions, ratio = compute_dna_mutation(imprint, left)
        assert len(positions) >= 1
        assert ratio <= MAX_LEFT_CHAIN_MUTATION
