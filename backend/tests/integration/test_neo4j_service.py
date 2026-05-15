"""Neo4j 集成测试 — 覆盖 Neo4jService 全部 26 个公开方法。

需要在运行后端的环境中执行，Neo4j 不可用时自动跳过。
"""
from __future__ import annotations

import os
import pytest
import random

_TEST_AGENT = "test_agent_neo4j_int"


def _neo4j_reachable() -> bool:
    """检测 Neo4j 是否可达。"""
    uri = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
    try:
        from neo4j import GraphDatabase
        with GraphDatabase.driver(uri, auth=("neo4j", os.environ.get("NEO4J_PASSWORD", "password"))) as driver:
            driver.verify_connectivity()
        return True
    except Exception:
        return False


@pytest.fixture(scope="module")
def svc():
    """Neo4j 服务单例 fixture。"""
    if not _neo4j_reachable():
        pytest.skip("Neo4j 不可达，跳过集成测试")

    from backend.services.neo4j_service import get_neo4j_service
    service = get_neo4j_service()
    import asyncio
    loop = asyncio.new_event_loop()
    loop.run_until_complete(service.start())
    yield service
    loop.run_until_complete(service.stop())
    loop.close()


def _rand_agent():
    return f"{_TEST_AGENT}_{random.randint(0, 99999)}"


# ═══════════════════════════════════════════════════════════════════
# 生命周期
# ═══════════════════════════════════════════════════════════════════

class TestLifecycle:
    def test_is_connected(self, svc):
        assert svc.is_connected() is True


# ═══════════════════════════════════════════════════════════════════
# DNA 操作
# ═══════════════════════════════════════════════════════════════════

class TestDNAOperations:
    def test_create_neuron(self, svc):
        agent = _rand_agent()
        ok = svc.create_neuron(agent, "概念_A", "ACG", "TGC", "PPPEEEIII", 0.8)
        assert ok is True

    def test_get_neuron_dna(self, svc):
        agent = _rand_agent()
        svc.create_neuron(agent, "概念_B", "AAA", "TTT")
        dna = svc.get_neuron_dna(agent, "概念_B")
        assert dna is not None
        assert dna["label"] == "概念_B"
        assert dna["left"] == "AAA"

    def test_get_nonexistent_neuron(self, svc):
        agent = _rand_agent()
        dna = svc.get_neuron_dna(agent, "不存在")
        assert dna is None

    def test_update_neuron_dna(self, svc):
        agent = _rand_agent()
        svc.create_neuron(agent, "概念_C", "111", "222")
        ok = svc.update_neuron_dna(agent, "概念_C", dna_left="GGG", expression_level=0.9)
        assert ok is True
        dna = svc.get_neuron_dna(agent, "概念_C")
        assert dna["left"] == "GGG"

    def test_migrate_nodes_to_dna(self, svc):
        agent = _rand_agent()
        # 创建几个节点
        svc.create_neuron(agent, "旧概念_1", "", "", "", 0.5)
        svc.create_neuron(agent, "旧概念_2", "", "", "", 0.5)
        result = svc.migrate_nodes_to_dna(agent, length=64)
        assert result["migrated"] >= 0


# ═══════════════════════════════════════════════════════════════════
# 知识图谱
# ═══════════════════════════════════════════════════════════════════

class TestKnowledgeGraph:
    def test_import_kg(self, svc):
        agent = _rand_agent()
        nodes = [
            {"label": "AI", "summary": "人工智能", "frequency": 10},
            {"label": "Python", "summary": "编程语言", "frequency": 8},
        ]
        edges = [
            {"source": "AI", "target": "Python", "relation": "uses"},
        ]
        count = svc.import_kg(agent, nodes, edges)
        assert count >= 0

    def test_get_central_nodes(self, svc):
        agent = _rand_agent()
        nodes = [
            {"label": "中心_A", "summary": "desc1", "frequency": 50},
            {"label": "中心_B", "summary": "desc2", "frequency": 40},
            {"label": "孤点_X", "summary": "desc3", "frequency": 1},
        ]
        edges = [
            {"source": "中心_A", "target": "中心_B", "relation": "related"},
        ]
        svc.import_kg(agent, nodes, edges)
        central = svc.get_central_nodes(agent, top_k=5)
        assert isinstance(central, list)

    def test_prune_irrelevant(self, svc):
        agent = _rand_agent()
        nodes = [
            {"label": "重要节点", "summary": "desc", "frequency": 100},
            {"label": "相关节点", "summary": "desc", "frequency": 50},
        ]
        edges = [
            {"source": "重要节点", "target": "相关节点", "relation": "connected"},
        ]
        svc.import_kg(agent, nodes, edges)
        result = svc.prune_irrelevant(agent, ["重要节点", "相关节点", "孤立节点"])
        assert isinstance(result, list)

    def test_random_walk(self, svc):
        agent = _rand_agent()
        nodes = [
            {"label": "起点", "summary": "出发点", "frequency": 30},
            {"label": "路径_A", "summary": "节点A", "frequency": 20},
            {"label": "路径_B", "summary": "节点B", "frequency": 15},
        ]
        edges = [
            {"source": "起点", "target": "路径_A", "relation": "leads_to"},
            {"source": "起点", "target": "路径_B", "relation": "leads_to"},
        ]
        svc.import_kg(agent, nodes, edges)
        walk = svc.random_walk(agent, max_depth=3, max_nodes=10)
        assert isinstance(walk, list)


# ═══════════════════════════════════════════════════════════════════
# 神经电流
# ═══════════════════════════════════════════════════════════════════

class TestNeuralActivation:
    def test_activate_neurons_with_current(self, svc):
        agent = _rand_agent()
        svc.create_neuron(agent, "神经元_1", "ACG", "TGC")
        svc.create_neuron(agent, "神经元_2", "GTA", "CAT")
        result = svc.activate_neurons_with_current(
            agent, "ACG", satiety=50, bio_current=3,
            mode="normal", task_complexity="simple", prompt_quality=0.8,
        )
        assert isinstance(result, dict)
        assert "activated_neurons" in result

    def test_activate_no_neurons_created(self, svc):
        agent = _rand_agent()
        result = svc.activate_neurons_with_current(
            agent, "XYZ", satiety=50, bio_current=3,
            mode="normal", task_complexity="simple", prompt_quality=0.8,
        )
        assert isinstance(result, dict)


# ═══════════════════════════════════════════════════════════════════
# Hebbian 学习
# ═══════════════════════════════════════════════════════════════════

class TestHebbianLearning:
    def test_strengthen_edge(self, svc):
        agent = _rand_agent()
        svc.create_neuron(agent, "源节点", "AAA", "TTT")
        svc.create_neuron(agent, "目标节点", "CCC", "GGG")
        # 先创建边
        svc.import_kg(agent,
            [{"label": "源节点", "summary": "src", "frequency": 10},
             {"label": "目标节点", "summary": "tgt", "frequency": 10}],
            [{"source": "源节点", "target": "目标节点", "relation": "connected"}],
        )
        ok = svc.strengthen_edge(agent, "源节点", "目标节点", delta=0.05, voltage=2.5)
        assert ok is True


# ═══════════════════════════════════════════════════════════════════
# 变异管理
# ═══════════════════════════════════════════════════════════════════

class TestMutation:
    def test_accumulate_potential(self, svc):
        agent = _rand_agent()
        svc.create_neuron(agent, "变异候选", "ACG", "TGC")
        potential = svc.accumulate_potential(agent, "变异候选", 0.3)
        assert potential > 0.0

    def test_accumulate_and_check_no_mutation(self, svc):
        agent = _rand_agent()
        svc.create_neuron(agent, "阈值下节点", "ACG", "TGC")
        svc.accumulate_potential(agent, "阈值下节点", 0.1)
        result = svc.check_mutation(agent, "阈值下节点")
        assert result is None

    def test_accumulate_and_check_mutation(self, svc):
        agent = _rand_agent()
        svc.create_neuron(agent, "触发节点", "ACGTACGT", "TGCATGCA")
        svc.accumulate_potential(agent, "触发节点", 1.5)
        result = svc.check_mutation(agent, "触发节点")
        assert result is not None

    def test_apply_mutation(self, svc):
        agent = _rand_agent()
        svc.create_neuron(agent, "待变异节点", "AAAA", "TTTT")
        ok = svc.apply_mutation(agent, "待变异节点", "GGGG", "CCCC")
        assert ok is True
        dna = svc.get_neuron_dna(agent, "待变异节点")
        assert dna["left"] == "GGGG"

    def test_prune_neuron_connections(self, svc):
        agent = _rand_agent()
        svc.create_neuron(agent, "剪枝目标", "ACG", "TGC")
        count = svc.prune_neuron_connections(agent, "剪枝目标")
        assert count >= 0

    def test_form_new_synapses(self, svc):
        agent = _rand_agent()
        svc.create_neuron(agent, "突触节点", "ACG", "TGC")
        svc.create_neuron(agent, "邻居_1", "GTA", "CAT")
        # 先创建边连接
        svc.import_kg(agent,
            [{"label": "突触节点", "summary": "main", "frequency": 10},
             {"label": "邻居_1", "summary": "neighbor", "frequency": 8}],
            [{"source": "突触节点", "target": "邻居_1", "relation": "connected"}],
        )
        count = svc.form_new_synapses(agent, "突触节点")
        assert count >= 0

    def test_create_hybrid_neuron(self, svc):
        agent = _rand_agent()
        svc.create_neuron(agent, "父本_A", "ACGT", "TGCA")
        svc.create_neuron(agent, "父本_B", "CAGT", "GTCA")
        ok = svc.create_hybrid_neuron(agent, "父本_A", "父本_B", "杂交子代")
        assert ok is True


# ═══════════════════════════════════════════════════════════════════
# 衰减
# ═══════════════════════════════════════════════════════════════════

class TestDecay:
    def test_decay_node_properties(self, svc):
        agent = _rand_agent()
        svc.create_neuron(agent, "衰减测试", "ACG", "TGC")
        import time
        result = svc.decay_node_properties(agent, timestamp=time.time())
        assert isinstance(result, dict)
        assert "decayed" in result


# ═══════════════════════════════════════════════════════════════════
# 电压驱动随机游走
# ═══════════════════════════════════════════════════════════════════

class TestVoltageDrivenWalk:
    def test_current_driven_random_walk(self, svc):
        agent = _rand_agent()
        nodes = [
            {"label": "电压起点", "summary": "start", "frequency": 40},
            {"label": "经过点", "summary": "mid", "frequency": 25},
        ]
        edges = [
            {"source": "电压起点", "target": "经过点", "relation": "flows"},
        ]
        svc.import_kg(agent, nodes, edges)
        walk = svc.current_driven_random_walk(agent, voltage=5.0, max_depth=3)
        assert isinstance(walk, list)


# ═══════════════════════════════════════════════════════════════════
# 物品/空间 CRUD
# ═══════════════════════════════════════════════════════════════════

class TestItemCRUD:
    def test_create_item(self, svc):
        agent = _rand_agent()
        ok = svc.create_item(agent, "魔法书", "古老的魔法书", x=100, y=200, category="book",
                             mood_tags=["mystery", "calm"])
        assert ok is True

    def test_get_items_near_agent(self, svc):
        agent = _rand_agent()
        svc.create_item(agent, "附近物品", "测试用", x=10, y=10, category="test")
        items = svc.get_items_near_agent(agent, x=0, y=0, threshold=200)
        assert isinstance(items, list)

    def test_query_item_emotions(self, svc):
        agent = _rand_agent()
        svc.create_item(agent, "情绪物品", "测试情绪标签", mood_tags=["joy", "excitement"])
        result = svc.query_item_emotions(agent, "情绪物品")
        assert isinstance(result, dict)
        assert "tags" in result

    def test_update_agent_location(self, svc):
        agent = _rand_agent()
        svc.create_item(agent, "定位物品", "测试位置更新", x=50, y=50)
        # 不应抛异常
        svc.update_agent_location(agent, "Agent_1", 60.0, 60.0)
