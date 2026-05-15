"""双链数字DNA计算引擎 — 纯计算，无I/O依赖。

左链 = 基因型（稳定基准，base-4编码: 0=A, 1=C, 2=G, 3=T）
右链 = 表现型（互补序列: right[i] = 3 - left[i]）
"""
from __future__ import annotations

import hashlib
import json
import math
import random
import time
from dataclasses import dataclass, field
from typing import Optional

# ── 常量 ──────────────────────────────────────────────────────────────
PROMOTER_WEIGHT = 0.40
EXON_WEIGHT = 0.45
INTRON_WEIGHT = 0.05
EXPRESSION_BONUS = 0.10
MAX_MUTATION_RATIO = 0.15
POTENTIAL_PER_INTERACTION = 0.0001
PHOSPHORYLATION_HALF_LIFE = 300.0
DEFAULT_DNA_LENGTH = 128

# 四大碱基: 0=A 腺嘌呤, 1=C 胞嘧啶, 2=G 鸟嘌呤, 3=T 胸腺嘧啶
BASE_SYMBOLS = ["A", "C", "G", "T"]


@dataclass
class DNARegions:
    """DNA功能分区元数据"""
    promoter_start: int = 0
    promoter_end: int = 0
    exon1_start: int = 0
    exon1_end: int = 0
    exon2_start: int = 0
    exon2_end: int = 0
    intron_start: int = 0
    intron_end: int = 0

    def to_dict(self) -> dict:
        return {
            "promoter": [self.promoter_start, self.promoter_end],
            "exon1": [self.exon1_start, self.exon1_end],
            "exon2": [self.exon2_start, self.exon2_end],
            "intron": [self.intron_start, self.intron_end],
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict())

    @classmethod
    def from_dict(cls, d: dict) -> "DNARegions":
        r = cls()
        if "promoter" in d:
            r.promoter_start, r.promoter_end = d["promoter"]
        if "exon1" in d:
            r.exon1_start, r.exon1_end = d["exon1"]
        if "exon2" in d:
            r.exon2_start, r.exon2_end = d["exon2"]
        if "intron" in d:
            r.intron_start, r.intron_end = d["intron"]
        return r


@dataclass
class MutationRecord:
    """突变审计记录"""
    timestamp: float = field(default_factory=time.time)
    old_left: str = ""
    new_left: str = ""
    changed_positions: list[int] = field(default_factory=list)
    trigger: str = ""
    mutation_ratio: float = 0.0


# ── 核心函数 ──────────────────────────────────────────────────────────


def generate_dna(length: int = DEFAULT_DNA_LENGTH) -> str:
    """生成随机base-4左链序列。"""
    return "".join(str(random.randint(0, 3)) for _ in range(length))


def generate_default_regions(length: int = DEFAULT_DNA_LENGTH) -> DNARegions:
    """生成默认功能分区: promoter 25%, exon 2×25%, intron 12.5%,
    剩余 12.5% 为表达区缓冲。
    """
    n = length
    promoter_end = max(1, int(n * 0.25))
    exon1_start = promoter_end
    exon1_end = exon1_start + max(1, int(n * 0.25))
    exon2_start = exon1_end
    exon2_end = exon2_start + max(1, int(n * 0.25))
    intron_start = exon2_end
    intron_end = min(n, intron_start + max(1, int(n * 0.125)))
    return DNARegions(
        promoter_start=0, promoter_end=promoter_end,
        exon1_start=exon1_start, exon1_end=exon1_end,
        exon2_start=exon2_start, exon2_end=exon2_end,
        intron_start=intron_start, intron_end=intron_end,
    )


def compute_complement(dna: str) -> str:
    """计算互补右链: right[i] = 3 - left[i]"""
    return "".join(str(3 - int(c)) for c in dna)


def compute_signal_dna(query_text: str, length: int = DEFAULT_DNA_LENGTH) -> str:
    """文本 → SHA-256 → base-4 信号DNA（确定性映射）。

    用于将用户查询转换为可比的DNA信号序列。
    """
    h = hashlib.sha256(query_text.encode("utf-8")).hexdigest()
    signal = []
    for i in range(length):
        # 每次取2个hex char → 0-255, mod 4 → 0-3
        idx = i * 2 % len(h)
        val = int(h[idx:idx + 2], 16) if idx + 2 <= len(h) else int(h[idx], 16)
        signal.append(str(val % 4))
    return "".join(signal)


def align_score(signal: str, left: str, regions: DNARegions) -> float:
    """分区加权比对得分。

    promoter × 0.40 + exon × 0.45 + intron × 0.05

    signal 和 left 逐位比较（同一位置相同=1, 不同=0），
    在各功能分区内计算匹配率后加权求和。
    """
    min_len = min(len(signal), len(left))

    def _zone_match_rate(start: int, end: int) -> float:
        if start >= end or start >= min_len:
            return 0.0
        actual_end = min(end, min_len)
        matching = sum(1 for i in range(start, actual_end) if signal[i] == left[i])
        return matching / (actual_end - start) if actual_end > start else 0.0

    promoter_score = _zone_match_rate(regions.promoter_start, regions.promoter_end)
    exon1_score = _zone_match_rate(regions.exon1_start, regions.exon1_end)
    exon2_score = _zone_match_rate(regions.exon2_start, regions.exon2_end)
    intron_score = _zone_match_rate(regions.intron_start, regions.intron_end)

    exon_avg = (exon1_score + exon2_score) / 2.0 if (exon1_score + exon2_score) > 0 else 0.0

    return (
        promoter_score * PROMOTER_WEIGHT
        + exon_avg * EXON_WEIGHT
        + intron_score * INTRON_WEIGHT
    )


def compute_activation_score(
    signal: str,
    left: str,
    right: str,
    regions: DNARegions,
    expression_level: float = 0.5,
) -> float:
    """总激活得分 = align_score + expression_bonus。

    expression_bonus = expression_level * 0.10
    """
    base = align_score(signal, left, regions)
    bonus = expression_level * EXPRESSION_BONUS
    return min(1.0, base + bonus)


def apply_phosphorylation(label: str, context: str) -> dict:
    """临时右链磷酸化：基于上下文计算右链偏移位置和临时序列。

    返回 {active_right, delta_positions, applied_at}
    """
    # 基于上下文字的哈希确定偏移位置
    seed = hash(label + context) % (2 ** 31)
    rng = random.Random(seed)
    num_deltas = max(1, len(context) % 5 + 1)
    positions = sorted([rng.randint(0, DEFAULT_DNA_LENGTH - 1) for _ in range(num_deltas)])

    # 生成偏移模式
    dna_len = DEFAULT_DNA_LENGTH
    active = list("0" * dna_len)
    for pos in positions:
        active[pos] = str(rng.randint(0, 3))

    return {
        "active_right": "".join(active),
        "delta_positions": positions,
        "applied_at": time.time(),
    }


def decay_phosphorylation(
    active_right: str | None,
    applied_at: float | None,
    half_life: float = PHOSPHORYLATION_HALF_LIFE,
) -> str | None:
    """指数衰减：elapsed > 5 * half_life 时完全清除磷酸化。

    返回 None 表示磷酸化已完全衰减。
    """
    if active_right is None or applied_at is None:
        return None
    elapsed = time.time() - applied_at
    if elapsed > half_life * 5:
        return None

    # 衰减存活概率 = 2^(-elapsed/half_life)
    survival = math.pow(2, -elapsed / half_life)
    if random.random() > survival:
        return None
    return active_right


def accumulate_potential(current: float, delta: float = POTENTIAL_PER_INTERACTION) -> tuple[float, bool]:
    """蓄力累加，返回 (new_value, should_mutate)。

    should_mutate = True 当 new_value >= 1.0
    """
    new_val = current + delta
    if new_val >= 1.0:
        return new_val, True
    return new_val, False


def compute_mutation_probability(potential: float) -> float:
    """将蓄力值映射到实际突变概率。

    potential ∈ [0, 1] → probability ∈ [0, MAX_MUTATION_RATIO]
    使用线性映射: probability = potential * MAX_MUTATION_RATIO
    """
    return min(potential, 1.0) * MAX_MUTATION_RATIO


def trigger_mutation(
    left: str,
    right: str,
    regions: DNARegions,
    expression_levels: dict | None = None,
    history: list[MutationRecord] | None = None,
    mutation_probability: float | None = None,
) -> dict:
    """定向突变：≤15%碱基变更，偏向 promoter 区域。

    返回 {new_left, new_right, changed_positions, mutation_ratio, history_appended}
    """
    chain_len = len(left)
    if mutation_probability is None:
        mutation_probability = MAX_MUTATION_RATIO * 0.5  # 默认中等概率

    # 计算变异碱基数
    num_mutations = max(1, min(
        int(chain_len * MAX_MUTATION_RATIO),
        int(chain_len * mutation_probability),
    ))
    num_mutations = max(1, num_mutations)  # 至少变异1个

    promoter_len = regions.promoter_end - regions.promoter_start
    mutated = list(left)
    positions = []

    for _ in range(num_mutations):
        # 70% 概率在 promoter 区变异
        if promoter_len > 0 and random.random() < 0.70:
            pos = random.randint(regions.promoter_start, min(regions.promoter_end, chain_len) - 1)
        else:
            pos = random.randint(0, chain_len - 1)

        # 防止同一位置重复变异
        if pos in positions:
            continue

        old_base = int(mutated[pos])
        # 碱基偏移方向：随机 +1 或 -1（模4）
        direction = random.choice([1, -1])
        new_base = (old_base + direction) % 4
        mutated[pos] = str(new_base)
        positions.append(pos)

    new_left = "".join(mutated)
    new_right = compute_complement(new_left)
    actual_ratio = len(positions) / chain_len

    record = MutationRecord(
        timestamp=time.time(),
        old_left=left,
        new_left=new_left,
        changed_positions=sorted(positions),
        trigger="potential_threshold",
        mutation_ratio=actual_ratio,
    )

    full_history = (history or []) + [record]

    return {
        "new_left": new_left,
        "new_right": new_right,
        "changed_positions": sorted(positions),
        "mutation_ratio": actual_ratio,
        "history": full_history,
    }


def validate_complement(left: str, right: str) -> tuple[bool, list[int]]:
    """互补链校验。

    返回 (is_valid, [mismatch_positions])
    """
    min_len = min(len(left), len(right))
    mismatches = [
        i for i in range(min_len)
        if int(right[i]) != (3 - int(left[i]))
    ]
    return len(mismatches) == 0, mismatches


def hybridize(
    left_a: str,
    right_a: str,
    regions_a: DNARegions,
    left_b: str,
    right_b: str,
    regions_b: DNARegions,
    crossover_point: int | None = None,
) -> dict:
    """双亲A和B交叉重组生成子DNA。

    使用单点交叉: 在 crossover_point 处交换左链片段。
    右链由新左链通过 compute_complement 重新计算。

    返回 {left_child, right_child, regions_child, crossover_point}
    """
    min_len = min(len(left_a), len(left_b))
    if crossover_point is None:
        # 在 promoter 尾部和 exon 之间随机选交叉点
        point_range = (min_len // 4, min_len * 3 // 4)
        crossover_point = random.randint(point_range[0], point_range[1])

    left_child = left_a[:crossover_point] + left_b[crossover_point:]
    left_child = left_child[:min_len]  # 保持长度

    right_child = compute_complement(left_child)

    # 合并功能分区（取A的前半+B的后半）
    regions_child = DNARegions(
        promoter_start=0,
        promoter_end=regions_a.promoter_end,
        exon1_start=regions_b.exon1_start if regions_b.exon1_start > 0 else regions_a.exon1_start,
        exon1_end=regions_b.exon1_end if regions_b.exon1_end > 0 else regions_a.exon1_end,
        exon2_start=regions_b.exon2_start if regions_b.exon2_start > 0 else regions_a.exon2_start,
        exon2_end=regions_b.exon2_end if regions_b.exon2_end > 0 else regions_a.exon2_end,
        intron_start=regions_b.intron_start if regions_b.intron_start > 0 else regions_a.intron_start,
        intron_end=regions_b.intron_end if regions_b.intron_end > 0 else regions_a.intron_end,
    )

    return {
        "left_child": left_child,
        "right_child": right_child,
        "regions_child": regions_child,
        "crossover_point": crossover_point,
    }


def compute_signal_dna_from_keywords(keywords: list[str], length: int = DEFAULT_DNA_LENGTH) -> str:
    """从关键词列表生成信号DNA（用于无长文本时的DNA匹配）。

    与 compute_signal_dna 类似但接受字符串列表。
    """
    combined = " ".join(sorted(keywords))
    return compute_signal_dna(combined, length)


def dna_to_symbols(dna: str) -> str:
    """将 base-4 序列转为人类可读的碱基符号串 (A/C/G/T)。"""
    return "".join(BASE_SYMBOLS[int(c)] for c in dna)


def symbols_to_dna(symbols: str) -> str:
    """将碱基符号串转回 base-4 序列。"""
    symbol_map = {s: str(i) for i, s in enumerate(BASE_SYMBOLS)}
    return "".join(symbol_map.get(c, "0") for c in symbols.upper())
