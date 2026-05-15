"""测试 HeartbeatService 预判过滤器 — Jaccard 相似度计算与滑动窗口逻辑。"""
from __future__ import annotations

from backend.services.heartbeat import HeartbeatService


class TestJaccardSimilarity:
    """_compute_node_similarity 纯逻辑测试。"""

    def test_empty_current(self):
        result = HeartbeatService._compute_node_similarity(
            frozenset(),
            [frozenset(["A", "B"])],
        )
        assert result == 0.0

    def test_empty_history(self):
        result = HeartbeatService._compute_node_similarity(
            frozenset(["A", "B"]),
            [],
        )
        assert result == 0.0

    def test_perfect_match(self):
        result = HeartbeatService._compute_node_similarity(
            frozenset(["A", "B", "C"]),
            [frozenset(["A", "B", "C"])],
        )
        assert result == 1.0

    def test_partial_overlap(self):
        result = HeartbeatService._compute_node_similarity(
            frozenset(["A", "B", "C"]),
            [frozenset(["A", "B", "D"])],
        )
        # intersection = {A, B} = 2, union = {A, B, C, D} = 4 → 0.5
        assert result == 0.5

    def test_no_overlap(self):
        result = HeartbeatService._compute_node_similarity(
            frozenset(["A", "B"]),
            [frozenset(["C", "D"])],
        )
        assert result == 0.0

    def test_max_across_multiple_histories(self):
        """应返回多个历史记录中的最大值。"""
        result = HeartbeatService._compute_node_similarity(
            frozenset(["A", "B"]),
            [
                frozenset(["C", "D"]),       # Jaccard = 0.0
                frozenset(["A", "C"]),       # Jaccard = 1/3 ≈ 0.333
                frozenset(["A", "B", "E"]),  # Jaccard = 2/3 ≈ 0.667 (max)
            ],
        )
        assert abs(result - 2.0 / 3.0) < 0.01

    def test_single_element_match(self):
        result = HeartbeatService._compute_node_similarity(
            frozenset(["Person"]),
            [frozenset(["Person", "WorksAt", "Company"])],
        )
        assert result == 1.0 / 3.0  # 1 / 3

    def test_above_threshold_0_8(self):
        """相似度 > 0.8 应触发过滤跳过。"""
        # 模拟心跳过滤器的阈值判定
        similarity = HeartbeatService._compute_node_similarity(
            frozenset(["Person", "WorksAt", "CompanyA"]),
            [frozenset(["Person", "WorksAt", "CompanyA", "Role"])],
        )
        # intersection=3, union=4 → 0.75, 低于阈值
        assert similarity < 0.8

        similarity2 = HeartbeatService._compute_node_similarity(
            frozenset(["Person", "WorksAt", "CompanyA", "Role"]),
            [frozenset(["Person", "WorksAt", "CompanyA", "Role", "Project"])],
        )
        # intersection=4, union=5 → 0.8, 等于阈值
        assert similarity2 == 0.8

    def test_below_threshold_0_8_should_proceed(self):
        """相似度 <= 0.8 应允许 LLM 推理继续。"""
        similarity = HeartbeatService._compute_node_similarity(
            frozenset(["Person", "LivesIn"]),
            [frozenset(["Person", "WorksAt", "Project", "Task"])],
        )
        # intersection=1 {Person}, union=5 → 0.2
        assert similarity < 0.8


class TestRecentNodeSets:
    """_recent_node_sets 滑动窗口测试。"""

    def test_initial_empty_on_new_agent(self):
        svc = HeartbeatService()
        agent_id = "test-agent-prefilter"
        # 新 agent 没有历史记录
        assert svc._recent_node_sets.get(agent_id, []) == []

    def test_sliding_window_max_10_entries(self):
        """验证滑动窗口最多保留 10 个条目。"""
        svc = HeartbeatService()
        agent_id = "test-sliding-window"

        # 模拟 15 次游走
        for i in range(15):
            labels = frozenset([f"Node{i}", f"Label{i % 3}"])
            history = svc._recent_node_sets.get(agent_id, [])
            history.append(labels)
            if len(history) > 10:
                history.pop(0)
            svc._recent_node_sets[agent_id] = history

        # 验证最多保留 10 条
        assert len(svc._recent_node_sets[agent_id]) == 10

        # 最早的第 0-4 条应被移出，保留 5-14
        first_kept = svc._recent_node_sets[agent_id][0]
        assert "Node5" in first_kept
        last_kept = svc._recent_node_sets[agent_id][-1]
        assert "Node14" in last_kept

    def test_disjoint_labels_no_similarity(self):
        """完全不相关的节点标签集合不产生相似度。"""
        svc = HeartbeatService()
        agent_id = "test-disjoint"
        svc._recent_node_sets[agent_id] = [
            frozenset(["Cat", "Animal"]),
            frozenset(["Dog", "Animal"]),
        ]

        sim = HeartbeatService._compute_node_similarity(
            frozenset(["Car", "Vehicle", "Engine"]),
            svc._recent_node_sets[agent_id],
        )
        assert sim == 0.0

    def test_identical_to_recent_would_be_skipped(self):
        """与最近一次完全相同：Jaccard=1.0 > 0.8，应触发跳过。"""
        svc = HeartbeatService()
        agent_id = "test-identical"
        svc._recent_node_sets[agent_id] = [
            frozenset(["A", "B", "C"]),
        ]

        sim = HeartbeatService._compute_node_similarity(
            frozenset(["A", "B", "C"]),
            svc._recent_node_sets[agent_id],
        )
        assert sim == 1.0
        assert sim > 0.8  # 超过阈值，应被跳过
