"""DNA计算引擎单元测试"""
from __future__ import annotations

import json

from backend.services.dna_service import (
    DNARegions,
    MutationRecord,
    generate_dna,
    generate_default_regions,
    compute_complement,
    compute_signal_dna,
    align_score,
    compute_activation_score,
    apply_phosphorylation,
    decay_phosphorylation,
    accumulate_potential,
    compute_mutation_probability,
    trigger_mutation,
    validate_complement,
    hybridize,
    dna_to_symbols,
    symbols_to_dna,
    DEFAULT_DNA_LENGTH,
)


class TestDNAGeneration:
    def test_generate_dna_default_length(self):
        dna = generate_dna()
        assert len(dna) == DEFAULT_DNA_LENGTH
        assert all(c in "0123" for c in dna)

    def test_generate_dna_custom_length(self):
        dna = generate_dna(64)
        assert len(dna) == 64
        assert all(c in "0123" for c in dna)

    def test_generate_dna_randomness(self):
        a = generate_dna(128)
        b = generate_dna(128)
        assert a != b  # 极低概率相同

    def test_generate_default_regions(self):
        regions = generate_default_regions(128)
        assert regions.promoter_end > 0
        assert regions.exon1_end > regions.exon1_start
        assert regions.exon2_end > regions.exon2_start
        assert regions.intron_end > regions.intron_start

    def test_regions_serialization(self):
        regions = generate_default_regions(128)
        d = regions.to_dict()
        assert "promoter" in d
        assert len(d["promoter"]) == 2
        json_str = regions.to_json()
        restored = DNARegions.from_dict(json.loads(json_str))
        assert restored.promoter_end == regions.promoter_end


class TestDNAComplement:
    def test_compute_complement(self):
        left = "0123"
        right = compute_complement(left)
        assert right == "3210"

    def test_compute_complement_idempotent(self):
        left = generate_dna(64)
        right = compute_complement(left)
        # complement of complement = original
        left_again = compute_complement(right)
        assert left_again == left

    def test_validate_complement_valid(self):
        left = "01230123"
        right = "32103210"
        valid, mismatches = validate_complement(left, right)
        assert valid is True
        assert mismatches == []

    def test_validate_complement_invalid(self):
        left = "01230123"
        right = "02100321"
        valid, mismatches = validate_complement(left, right)
        assert valid is False
        assert len(mismatches) > 0


class TestSignalDNA:
    def test_compute_signal_dna_length(self):
        signal = compute_signal_dna("hello world", 64)
        assert len(signal) == 64
        assert all(c in "0123" for c in signal)

    def test_compute_signal_dna_deterministic(self):
        a = compute_signal_dna("hello world")
        b = compute_signal_dna("hello world")
        assert a == b

    def test_compute_signal_dna_different_inputs(self):
        a = compute_signal_dna("hello")
        b = compute_signal_dna("world")
        assert a != b


class TestAlignment:
    def test_align_score_perfect_match(self):
        left = "0101" * 32  # 128 length
        signal = left  # 完全匹配
        regions = generate_default_regions(128)
        score = align_score(signal, left, regions)
        # 各区域匹配率 = 1.0, 加权 = 0.40*1 + 0.45*1 + 0.05*1 = 0.90
        assert score > 0.85

    def test_align_score_complete_mismatch(self):
        left = "0000" * 32
        signal = "3333" * 32
        regions = generate_default_regions(128)
        score = align_score(signal, left, regions)
        assert score == 0.0

    def test_activation_score(self):
        left = "0101" * 32
        right = compute_complement(left)
        signal = left
        regions = generate_default_regions(128)
        score = compute_activation_score(signal, left, right, regions, expression_level=0.5)
        # align + 0.5 * 0.10 = align + 0.05
        assert 0.0 < score <= 1.0


class TestPhosphorylation:
    def test_apply_phosphorylation(self):
        result = apply_phosphorylation("test_neuron", "some context")
        assert "active_right" in result
        assert "delta_positions" in result
        assert "applied_at" in result
        assert len(result["active_right"]) == DEFAULT_DNA_LENGTH

    def test_decay_no_phosphorylation(self):
        result = decay_phosphorylation(None, None)
        assert result is None

    def test_decay_very_old(self):
        import time
        result = decay_phosphorylation("0123", time.time() - 10000)
        assert result is None


class TestMutation:
    def test_accumulate_potential_below_threshold(self):
        val, should = accumulate_potential(0.5)
        assert val == 0.5 + 0.0001
        assert should is False

    def test_accumulate_potential_at_threshold(self):
        val, should = accumulate_potential(0.9999)
        assert val >= 1.0
        assert should is True

    def test_mutation_probability(self):
        prob = compute_mutation_probability(0.5)
        assert prob == 0.075  # 0.5 * 0.15

    def test_trigger_mutation(self):
        left = generate_dna(128)
        right = compute_complement(left)
        regions = generate_default_regions(128)
        result = trigger_mutation(left, right, regions, mutation_probability=0.05)
        assert len(result["new_left"]) == 128
        assert len(result["changed_positions"]) > 0
        # 变异比例 ≤15%
        assert result["mutation_ratio"] <= 0.15
        # 新右链 = complement(新左链)
        expected_right = compute_complement(result["new_left"])
        assert result["new_right"] == expected_right

    def test_trigger_mutation_safety_boundary(self):
        """确保变异不超过安全边界."""
        left = generate_dna(128)
        right = compute_complement(left)
        regions = generate_default_regions(128)
        for _ in range(20):
            result = trigger_mutation(left, right, regions, mutation_probability=0.5)
            assert result["mutation_ratio"] <= 0.15


class TestHybridization:
    def test_hybridize(self):
        left_a = "0" * 128
        right_a = compute_complement(left_a)
        left_b = "3" * 128
        right_b = compute_complement(left_b)
        regions_a = generate_default_regions(128)
        regions_b = generate_default_regions(128)

        result = hybridize(left_a, right_a, regions_a, left_b, right_b, regions_b, crossover_point=64)
        child = result["left_child"]
        assert len(child) == 128
        # 前64位来自A (全是0), 后64位来自B (全是3)
        assert child[:64] == "0" * 64
        assert child[64:] == "3" * 64
        assert result["right_child"] == compute_complement(child)


class TestSymbolConversion:
    def test_dna_to_symbols(self):
        symbols = dna_to_symbols("0123")
        assert symbols == "ACGT"

    def test_symbols_to_dna(self):
        dna = symbols_to_dna("ACGT")
        assert dna == "0123"

    def test_roundtrip(self):
        original = generate_dna(64)
        symbols = dna_to_symbols(original)
        restored = symbols_to_dna(symbols)
        assert restored == original
