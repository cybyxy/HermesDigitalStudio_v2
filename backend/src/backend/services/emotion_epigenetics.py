"""情绪表观遗传 (Emotional Epigenetics) — 长期情绪 → DNA 左链变异

纯计算模块，不依赖 I/O。接受情绪历史序列，输出 DNA 左链突变方案。

DNA 编码: A=0, C=1, G=2, T=3
"""
from __future__ import annotations

import random
from dataclasses import dataclass

# 追踪最近会话数
SESSION_WINDOW = 50

# 长期情绪均值绝对值触发阈值
EPIGENETIC_THRESHOLD = 0.60

# 情绪强度→DNA突变率映射系数
MUTATION_RATE_PER_INTENSITY = 0.05

# 单次最多修改左链比例
MAX_LEFT_CHAIN_MUTATION = 0.08

# 最少会话数才能形成印记
MIN_SESSIONS = 10


@dataclass
class EpigeneticImprint:
    """表观遗传印记"""

    v_long_term: float
    a_long_term: float
    d_long_term: float
    intensity: float  # 印记强度 0.0~1.0
    session_count: int
    mutation_rate: float  # 当前变异率
    is_triggered: bool  # 是否触发表观遗传


def compute_long_term_avg(
    history: list[tuple[float, float, float]],
    window: int = SESSION_WINDOW,
) -> tuple[float, float, float]:
    """长程加权平均（近期更高权重）。

    Args:
        history: [(v, a, d), ...] 按时间升序排列（最新的在最后）
        window: 滑动窗口大小

    Returns:
        (v_avg, a_avg, d_avg) 加权平均值
    """
    if not history:
        return (0.0, 0.0, 0.0)

    recent = history[-window:]
    n = len(recent)

    total_v = total_a = total_d = 0.0
    total_weight = 0.0

    for i, (v, a, d) in enumerate(recent):
        # 越近期权重越高: (i+1)/n
        weight = (i + 1) / n
        total_v += v * weight
        total_a += a * weight
        total_d += d * weight
        total_weight += weight

    if total_weight == 0:
        return (0.0, 0.0, 0.0)

    return (total_v / total_weight, total_a / total_weight, total_d / total_weight)


def check_epigenetic_trigger(
    long_term_avg: tuple[float, float, float],
    session_count: int,
    threshold: float = EPIGENETIC_THRESHOLD,
    min_sessions: int = MIN_SESSIONS,
) -> EpigeneticImprint | None:
    """检查是否触发表观遗传印记。

    Args:
        long_term_avg: (v_avg, a_avg, d_avg)
        session_count: 总记录数
        threshold: 情绪强度阈值
        min_sessions: 最少记录数

    Returns:
        EpigeneticImprint 或 None（未触发）
    """
    if session_count < min_sessions:
        return None

    v_avg, a_avg, d_avg = long_term_avg

    # 计算综合强度
    intensity = (abs(v_avg) + abs(a_avg) + abs(d_avg)) / 3.0

    if intensity < threshold:
        return None

    # 突变率 = intensity * MUTATION_RATE_PER_INTENSITY，上限 MAX_LEFT_CHAIN_MUTATION
    mutation_rate = min(MAX_LEFT_CHAIN_MUTATION, intensity * MUTATION_RATE_PER_INTENSITY)

    return EpigeneticImprint(
        v_long_term=v_avg,
        a_long_term=a_avg,
        d_long_term=d_avg,
        intensity=intensity,
        session_count=session_count,
        mutation_rate=mutation_rate,
        is_triggered=True,
    )


def compute_dna_mutation(
    imprint: EpigeneticImprint,
    left_chain: str,
) -> tuple[str, list[int], float]:
    """计算 DNA 左链变异。

    变异逻辑:
    - 70% 概率在 promoter 区（前 25%）变异
    - 碱基偏移方向：正向情绪 → +1, 负向情绪 → -1
    - 单次最多修改 MAX_LEFT_CHAIN_MUTATION 比例

    Args:
        imprint: 表观遗传印记
        left_chain: DNA 左链序列 (A/C/G/T 或 0/1/2/3)

    Returns:
        (new_left_chain, positions, actual_ratio)
    """
    try:
        bases = [int(c) for c in left_chain]
    except ValueError:
        # 如果已经是字符编码，转换为数字
        symbol_map = {"A": 0, "C": 1, "G": 2, "T": 3}
        bases = [symbol_map.get(c, 0) for c in left_chain]

    chain_len = len(bases)

    # 突变方向：由长期情绪主导维度决定
    # 正向 → +1, 负向 → -1
    dominant = max(
        (abs(imprint.v_long_term), "v"),
        (abs(imprint.a_long_term), "a"),
        (abs(imprint.d_long_term), "d"),
    )
    dim_name = dominant[1]
    dim_value = getattr(imprint, f"{dim_name}_long_term")
    direction = 1 if dim_value > 0 else -1

    # 突变数量
    num_mutations = max(1, int(chain_len * imprint.mutation_rate))
    num_mutations = min(num_mutations, int(chain_len * MAX_LEFT_CHAIN_MUTATION))

    promoter_boundary = max(1, int(chain_len * 0.25))
    positions: list[int] = []

    for _ in range(num_mutations):
        if random.random() < 0.70:
            pos = random.randint(0, promoter_boundary - 1)
        else:
            pos = random.randint(promoter_boundary, chain_len - 1)

        if pos not in positions:
            positions.append(pos)
            bases[pos] = (bases[pos] + direction) % 4

    new_chain = "".join(str(b) for b in bases)
    actual_ratio = len(positions) / chain_len if chain_len > 0 else 0.0

    return new_chain, sorted(positions), actual_ratio
