"""Neo4j 知识图谱服务 — 公共类。

封装所有 Neo4j 操作，包括连接管理、图谱导入、
度中心性分析、随机游走等。

用法::

    from backend.services.neo4j_service import get_neo4j_service
    neo4j = get_neo4j_service()
    await neo4j.start()
    nodes = neo4j.random_walk("default")
"""

from __future__ import annotations

import logging
import random
import threading
from typing import Any

from backend.core.config import get_config

_log = logging.getLogger(__name__)

# ── 常量 ─────────────────────────────────────────────────────────────────

_ENTITY_LABEL = "崽崽"
_DB_NAME = "neo4j"

# Neo4j driver 类型延迟导入，避免未安装时模块加载失败
_DriverType: Any = None


def _get_driver_type():
    global _DriverType
    if _DriverType is None:
        from neo4j import GraphDatabase as _DriverType
    return _DriverType


# ── 公共类 ───────────────────────────────────────────────────────────────


class Neo4jService:
    """Neo4j 知识图谱操作类（单例）。"""

    def __init__(self):
        self._driver: Any = None
        self._lock = threading.Lock()

    # ── 生命周期 ────────────────────────────────────────────────────────

    async def start(self) -> bool:
        """初始化 Neo4j 连接并创建索引。

        幂等：多次调用不会重复初始化。

        Returns:
            True 如果连接成功。
        """
        with self._lock:
            if self._driver is not None:
                return True

            config = get_config()
            try:
                GraphDatabase = _get_driver_type()
                self._driver = GraphDatabase.driver(
                    config.neo4j_uri,
                    auth=(config.neo4j_user, config.neo4j_password),
                )
                # 验证连接
                with self._driver.session(database=_DB_NAME) as session:
                    result = session.run("RETURN 1 AS ok")
                    record = result.single()
                    if record and record["ok"] == 1:
                        _log.info(
                            "neo4j_service: 连接验证成功 (%s)", config.neo4j_uri
                        )
                    else:
                        _log.warning("neo4j_service: 连接验证返回异常值")
                        self._driver = None
                        return False

                # 创建索引
                self._ensure_indexes()
                return True

            except Exception as e:
                _log.warning("neo4j_service: 初始化失败 (非致命): %s", e)
                self._driver = None
                return False

    async def stop(self) -> None:
        """关闭 Neo4j driver 连接。"""
        with self._lock:
            if self._driver is not None:
                try:
                    self._driver.close()
                except Exception:
                    pass
                self._driver = None

    def is_connected(self) -> bool:
        """Neo4j 当前是否已连接。"""
        return self._driver is not None

    # ── 内部 ────────────────────────────────────────────────────────────

    @staticmethod
    def _safe_agent_id(agent_id: str) -> str:
        """将 agent_id 转为 Neo4j 标签安全的字符串。"""
        return agent_id.replace("/", "_").replace(":", "_").replace("-", "_")

    def _ensure_indexes(self) -> None:
        """创建必要的索引。"""
        if self._driver is None:
            return
        try:
            with self._driver.session(database=_DB_NAME) as session:
                session.run(
                    "CREATE INDEX entity_label IF NOT EXISTS "
                    f"FOR (n:{_ENTITY_LABEL}) ON (n.label)"
                )
                session.run(
                    "CREATE INDEX entity_agent IF NOT EXISTS "
                    f"FOR (n:{_ENTITY_LABEL}) ON (n.agent_id)"
                )
                # DNA + 神经电流索引
                session.run(
                    "CREATE INDEX idx_neuron_potential IF NOT EXISTS "
                    f"FOR (n:{_ENTITY_LABEL}) ON (n.agent_id, n.mutation_potential)"
                )
                session.run(
                    "CREATE INDEX idx_item_agent IF NOT EXISTS "
                    "FOR (n:物品) ON (n.agent_id)"
                )
                session.run(
                    "CREATE INDEX idx_item_name IF NOT EXISTS "
                    "FOR (n:物品) ON (n.agent_id, n.name)"
                )
        except Exception as e:
            _log.debug("neo4j_service: 索引创建失败 (可能已存在): %s", e)

    # ── 图谱导入 ────────────────────────────────────────────────────────

    def import_kg(
        self,
        agent_id: str,
        nodes: list[dict],
        edges: list[dict],
    ) -> int:
        """将知识图谱的节点和边导入 Neo4j。

        Args:
            agent_id: Agent ID
            nodes: [{"label": "React", "frequency": 5, "summary": "..."}, ...]
            edges: [{"source": "React", "target": "TypeScript", "weight": 3}, ...]

        Returns:
            核心实体数量（度 > 1 的节点数）。
        """
        if self._driver is None:
            _log.warning("neo4j_service: Neo4j 不可用，跳过图谱导入")
            return len(nodes)

        safe_aid = self._safe_agent_id(agent_id)

        try:
            with self._driver.session(database=_DB_NAME) as session:
                # 1. 清理该 agent 的旧图谱数据
                session.run(
                    f"MATCH (n:{_ENTITY_LABEL} {{agent_id: $agent_id}}) "
                    "DETACH DELETE n",
                    agent_id=safe_aid,
                )

                # 2. 导入节点
                for node in nodes:
                    label = node.get("label", "").strip()
                    if not label:
                        continue
                    session.run(
                        f"CREATE (n:{_ENTITY_LABEL} {{"
                        "  label: $label,"
                        "  agent_id: $agent_id,"
                        "  frequency: $freq,"
                        "  summary: $summary"
                        "})",
                        label=label,
                        agent_id=safe_aid,
                        freq=node.get("frequency", 1),
                        summary=node.get("summary", ""),
                    )

                # 3. 导入边
                for edge in edges:
                    src = edge.get("source", "").strip()
                    tgt = edge.get("target", "").strip()
                    if not src or not tgt:
                        continue
                    session.run(
                        f"MATCH (a:{_ENTITY_LABEL} "
                        f"{{label: $src, agent_id: $agent_id}}), "
                        f"      (b:{_ENTITY_LABEL} "
                        f"{{label: $tgt, agent_id: $agent_id}}) "
                        "CREATE (a)-[:RELATES_TO {weight: $weight}]->(b)",
                        src=src,
                        tgt=tgt,
                        agent_id=safe_aid,
                        weight=edge.get("weight", 1),
                    )

                # 4. 计算核心实体
                central = self.get_central_nodes(safe_aid, session=session)
                _log.info(
                    "neo4j_service: agent=%s 导入 %d 节点, %d 边, 核心=%d",
                    agent_id, len(nodes), len(edges), len(central),
                )
                return len(central)

        except Exception as e:
            _log.warning("neo4j_service: 图谱导入失败 (非致命): %s", e)
            return len(nodes)

    # ── 查询 ────────────────────────────────────────────────────────────

    def get_central_nodes(
        self,
        agent_id: str,
        top_k: int = 30,
        session: Any = None,
        entity_label: str | None = None,
        id_prop: str = "label",
    ) -> list[str]:
        """通过度中心性分析返回核心实体标签列表。

        度 = 出度 + 入度，过滤度 <= 1 的孤立节点。
        当 entity_label="Concept" 时不按 agent_id 过滤。

        Args:
            agent_id: Agent ID
            top_k: 返回前 K 个核心实体
            session: 复用已有 session（可选）
            entity_label: 节点标签，None 用默认 _ENTITY_LABEL
            id_prop: 标识符属性名

        Returns:
            标签字符串列表，按度降序排列。
        """
        if self._driver is None:
            return []

        el = entity_label or _ENTITY_LABEL
        use_agent = el != "Concept"
        safe_aid = self._safe_agent_id(agent_id)
        close_session = session is None

        try:
            if session is None:
                session = self._driver.session(database=_DB_NAME)

            if use_agent:
                match = f"MATCH (n:{el} {{agent_id: $agent_id}})"
            else:
                match = f"MATCH (n:{el})"

            params: dict = {"top_k": top_k}
            if use_agent:
                params["agent_id"] = safe_aid

            result = session.run(
                f"{match} "
                "OPTIONAL MATCH (n)-[r_out]->() "
                "OPTIONAL MATCH ()-[r_in]->(n) "
                "WITH n, COUNT(DISTINCT r_out) + COUNT(DISTINCT r_in) AS degree "
                "WHERE degree >= 1 "
                f"RETURN n.{id_prop} AS label, degree "
                "ORDER BY degree DESC "
                "LIMIT $top_k",
                **params,
            )
            return [record["label"] for record in result]

        except Exception as e:
            _log.warning("neo4j_service: 度中心性查询失败: %s", e)
            return []
        finally:
            if close_session and session is not None:
                session.close()

    def prune_irrelevant(
        self,
        agent_id: str,
        all_labels: list[str],
    ) -> list[str]:
        """过滤无关关键词：仅保留度中心性 > 1 的核心实体。

        如果 Neo4j 不可用，返回全部标签（不过滤）。
        """
        central = self.get_central_nodes(agent_id)
        if not central:
            return all_labels

        central_set = set(central)
        pruned = [l for l in all_labels if l in central_set]
        removed = len(all_labels) - len(pruned)
        if removed > 0:
            _log.info(
                "neo4j_service: agent=%s 过滤 %d 个无关关键词, 保留 %d 个",
                agent_id, removed, len(pruned),
            )
        return pruned

    def random_walk(
        self,
        agent_id: str,
        max_depth: int = 5,
        max_nodes: int = 20,
    ) -> list[dict]:
        """从 Agent 知识图谱的中心节点开始随机游走。

        优先尝试 KGEntity schema，无数据时回退到 Concept schema。

        Returns:
            [{"label": str, "summary": str, "frequency": int|float, "depth": int}, ...]
        """
        if self._driver is None:
            return []

        safe_aid = self._safe_agent_id(agent_id)

        def _try_schema(
            session,
            entity_label: str,
            id_prop: str,
            detail_props: tuple[str, ...],
            use_agent: bool,
        ) -> list[dict] | None:
            aid = safe_aid if use_agent else ""
            central_labels = self.get_central_nodes(
                agent_id, top_k=5, session=session,
                entity_label=entity_label, id_prop=id_prop,
            )

            # 回退：度中心性无结果时，直接取任意节点（不过滤 degree）
            if not central_labels:
                try:
                    if use_agent:
                        fallback = session.run(
                            f"MATCH (n:{entity_label} {{agent_id: $agent_id}}) "
                            f"RETURN n.{id_prop} AS label "
                            "LIMIT 10",
                            agent_id=safe_aid,
                        )
                    else:
                        fallback = session.run(
                            f"MATCH (n:{entity_label}) "
                            f"RETURN n.{id_prop} AS label "
                            "LIMIT 10",
                        )
                    central_labels = [r["label"] for r in fallback]
                except Exception:
                    pass

            if not central_labels:
                return None

            start_label = random.choice(central_labels)
            visited: set[str] = {start_label}

            start_node = self._get_node_detail(
                session, start_label, safe_aid=aid,
                entity_label=entity_label, id_prop=id_prop,
                props=detail_props,
            )
            if not start_node:
                return None

            nodes: list[dict] = [{
                "label": start_node.get("name", start_node.get("label", start_label)),
                "summary": start_node.get("summary", str(start_node.get("weight", ""))),
                "frequency": start_node.get("frequency", start_node.get("weight", 1)),
                "depth": 0,
            }]

            frontier: list[str] = [start_label]
            for depth in range(1, max_depth + 1):
                if len(nodes) >= max_nodes:
                    break
                next_frontier: list[str] = []
                for current_label in frontier:
                    neighbors = self._get_neighbors(
                        session, current_label, safe_aid=aid,
                        entity_label=entity_label, id_prop=id_prop,
                    )
                    candidates = [n for n in neighbors if n not in visited]
                    if not candidates:
                        continue
                    k = min(random.randint(1, 3), len(candidates))
                    chosen = random.sample(candidates, k)
                    for lbl in chosen:
                        if len(nodes) >= max_nodes:
                            break
                        visited.add(lbl)
                        detail = self._get_node_detail(
                            session, lbl, safe_aid=aid,
                            entity_label=entity_label, id_prop=id_prop,
                            props=detail_props,
                        )
                        if detail:
                            nodes.append({
                                "label": detail.get("name", detail.get("label", lbl)),
                                "summary": detail.get("summary", str(detail.get("weight", ""))),
                                "frequency": detail.get("frequency", detail.get("weight", 1)),
                                "depth": depth,
                            })
                        next_frontier.append(lbl)
                    if len(nodes) >= max_nodes:
                        break
                frontier = next_frontier
                if not frontier:
                    break
            return nodes if nodes else None

        try:
            with self._driver.session(database=_DB_NAME) as session:
                # 1) KGEntity schema
                result = _try_schema(
                    session,
                    entity_label=_ENTITY_LABEL,
                    id_prop="label",
                    detail_props=("label", "summary", "frequency"),
                    use_agent=True,
                )
                if result:
                    _log.debug(
                        "random_walk: agent=%s (KGEntity) collected=%d nodes",
                        agent_id, len(result),
                    )
                    return result

                # 2) Concept schema (fallback)
                _log.debug(
                    "random_walk: agent=%s 无 KGEntity 数据，回退到 Concept",
                    agent_id,
                )
                result = _try_schema(
                    session,
                    entity_label="Concept",
                    id_prop="name",
                    detail_props=("name", "weight"),
                    use_agent=False,
                )
                if result:
                    _log.info(
                        "random_walk: agent=%s (Concept) collected=%d nodes",
                        agent_id, len(result),
                    )
                    return result

                _log.info("random_walk: agent=%s 图谱无可用节点", agent_id)
                return []

        except Exception as e:
            _log.warning("random_walk: agent=%s 游走失败: %s", agent_id, e)
            return []

    # ── 内部辅助 ────────────────────────────────────────────────────────

    @staticmethod
    def _get_node_detail(
        session,
        label: str,
        safe_aid: str = "",
        entity_label: str = _ENTITY_LABEL,
        id_prop: str = "label",
        props: tuple[str, ...] = ("label", "summary", "frequency"),
    ) -> dict | None:
        """获取单个节点的详情。"""
        try:
            has_agent = safe_aid and entity_label != "Concept"
            if has_agent:
                query = (
                    f"MATCH (n:{entity_label} "
                    f"{{ {id_prop}: $label, agent_id: $agent_id }}) "
                )
            else:
                query = (
                    f"MATCH (n:{entity_label} "
                    f"{{ {id_prop}: $label }}) "
                )

            return_clause = ", ".join(f"n.{p} AS {p}" for p in props)
            query += f"RETURN {return_clause}"

            params = {"label": label}
            if has_agent:
                params["agent_id"] = safe_aid

            result = session.run(query, **params)
            record = result.single()
            if record:
                return {
                    p: (record.get(p) or "" if p in ("label", "summary", "name")
                        else record.get(p) or 1)
                    for p in props
                }
            return None
        except Exception:
            return None

    @staticmethod
    def _get_neighbors(
        session,
        label: str,
        safe_aid: str = "",
        entity_label: str = _ENTITY_LABEL,
        id_prop: str = "label",
    ) -> list[str]:
        """获取节点的所有邻接节点（出边 + 入边）。"""
        try:
            has_agent = safe_aid and entity_label != "Concept"
            if has_agent:
                match_clause = f"{{ {id_prop}: $label, agent_id: $agent_id }}"
                match_neighbor = "{ agent_id: $agent_id }"
                params = {"label": label, "agent_id": safe_aid}
            else:
                match_clause = f"{{ {id_prop}: $label }}"
                match_neighbor = ""
                params = {"label": label}

            labels: list[str] = []

            # 出边
            result = session.run(
                f"MATCH (n:{entity_label} {match_clause}) "
                f"OPTIONAL MATCH (n)-[]->(out:{entity_label} {match_neighbor}) "
                f"RETURN DISTINCT out.{id_prop} AS label",
                **params,
            )
            for record in result:
                lbl = record.get("label")
                if lbl and lbl != label:
                    labels.append(lbl)

            # 入边
            result2 = session.run(
                f"MATCH (n:{entity_label} {match_clause}) "
                f"OPTIONAL MATCH (in_node:{entity_label} {match_neighbor})-[]->(n) "
                f"RETURN DISTINCT in_node.{id_prop} AS label",
                **params,
            )
            for record in result2:
                lbl = record.get("label")
                if lbl and lbl != label and lbl not in labels:
                    labels.append(lbl)

            return labels
        except Exception:
            return []

    # ── DNA 操作 ──────────────────────────────────────────────────────────

    def create_neuron(
        self, agent_id: str, label: str, dna_left: str = "", dna_right: str = "",
        dna_regions: str = "", expression_level: float = 0.5,
    ) -> bool:
        """创建带完整 DNA 属性的神经元。"""
        if self._driver is None:
            return False
        safe_aid = self._safe_agent_id(agent_id)
        try:
            with self._driver.session(database=_DB_NAME) as session:
                session.run(
                    f"""
                    MERGE (n:{_ENTITY_LABEL} {{label: $label, agent_id: $aid}})
                    SET n.dna_left = $dna_left,
                        n.dna_right = $dna_right,
                        n.dna_regions = $dna_regions,
                        n.expression_level = $expr,
                        n.mutation_potential = 0.0,
                        n.neural_voltage = 0.0,
                        n.conduction_resistance = 0.5,
                        n.joule_heat = 0.0,
                        n.metabolic_waste = 0.0
                    """,
                    label=label, aid=safe_aid, dna_left=dna_left,
                    dna_right=dna_right, dna_regions=dna_regions, expr=expression_level,
                )
            return True
        except Exception as e:
            _log.warning("neo4j_service: create_neuron failed: %s", e)
            return False

    def get_neuron_dna(self, agent_id: str, label: str) -> dict | None:
        """获取神经元完整 DNA 数据。"""
        if self._driver is None:
            return None
        safe_aid = self._safe_agent_id(agent_id)
        try:
            with self._driver.session(database=_DB_NAME) as session:
                record = session.run(
                    f"""
                    MATCH (n:{_ENTITY_LABEL} {{label: $label, agent_id: $aid}})
                    RETURN n.label AS label, n.dna_left AS left, n.dna_right AS right,
                           n.dna_regions AS regions, n.expression_level AS expr,
                           n.mutation_potential AS potential
                    """,
                    label=label, aid=safe_aid,
                ).single()
                if record:
                    return dict(record)
            return None
        except Exception as e:
            _log.warning("neo4j_service: get_neuron_dna failed: %s", e)
            return None

    def update_neuron_dna(self, agent_id: str, label: str, **kwargs) -> bool:
        """动态更新神经元 DNA 相关属性。"""
        if self._driver is None:
            return False
        safe_aid = self._safe_agent_id(agent_id)
        try:
            allowed = {"dna_left", "dna_right", "dna_regions", "expression_level",
                       "neural_voltage", "conduction_resistance", "joule_heat",
                       "metabolic_waste", "dna_right_active", "phosphorylated_at",
                       "mutation_potential"}
            set_clauses = []
            params = {"label": label, "aid": safe_aid}
            for k, v in kwargs.items():
                if k in allowed:
                    set_clauses.append(f"n.{k} = ${k}")
                    params[k] = v
            if not set_clauses:
                return False

            with self._driver.session(database=_DB_NAME) as session:
                session.run(
                    f"MATCH (n:{_ENTITY_LABEL} {{label: $label, agent_id: $aid}}) "
                    f"SET {', '.join(set_clauses)}",
                    **params,
                )
            return True
        except Exception as e:
            _log.warning("neo4j_service: update_neuron_dna failed: %s", e)
            return False

    def migrate_nodes_to_dna(self, agent_id: str, length: int = 128) -> dict:
        """批量迁移遗留节点到完整 DNA 属性。"""
        if self._driver is None:
            return {"migrated": 0, "errors": 0}
        safe_aid = self._safe_agent_id(agent_id)
        migrated = 0
        errors = 0
        try:
            from backend.services.dna_service import generate_dna, compute_complement

            with self._driver.session(database=_DB_NAME) as session:
                nodes = session.run(
                    f"MATCH (n:{_ENTITY_LABEL} {{agent_id: $aid}}) "
                    "WHERE n.dna_left IS NULL RETURN n.label AS label",
                    aid=safe_aid,
                )
                for record in nodes:
                    label = record["label"]
                    try:
                        dna = generate_dna(length)
                        right = compute_complement(dna)
                        session.run(
                            f"MATCH (n:{_ENTITY_LABEL} {{label: $label, agent_id: $aid}}) "
                            "SET n.dna_left = $left, n.dna_right = $right, "
                            "n.expression_level = 0.5, n.mutation_potential = 0.0",
                            label=label, aid=safe_aid, left=dna, right=right,
                        )
                        migrated += 1
                    except Exception:
                        errors += 1
        except Exception as e:
            _log.warning("neo4j_service: migrate_nodes_to_dna failed: %s", e)
            errors += 1

        return {"migrated": migrated, "errors": errors}

    # ── 神经电流驱动激活 ──────────────────────────────────────────────────

    def activate_neurons_with_current(
        self, agent_id: str, signal_dna: str, satiety: int, bio_current: int,
        mode: str, task_complexity: str, prompt_quality: float,
        modulated_voltage: float | None = None,
        conductance_bias: float = 0.0,
    ) -> dict:
        """电流驱动神经元激活 (Winner-Take-All + BFS 遍历)。

        Returns 字典包含 activated_neurons, traversed_edges 等。
        """
        if self._driver is None:
            return {"activated_neurons": [], "traversed_edges": [], "total_current_used": 0.0}

        safe_aid = self._safe_agent_id(agent_id)
        try:
            from backend.services.neural_current import (
                compute_initial_voltage,
                compute_activation_voltage,
                compute_conduction_depth,
                accumulate_joule_heat,
                check_hedonic_override,
            )
            from backend.services.dna_service import (
                compute_activation_score,
                apply_phosphorylation,
                accumulate_potential,
            )

            # Step 1+2: 初始电压 + 享乐检测
            voltage = compute_initial_voltage(satiety, bio_current, mode, task_complexity)
            hedonic = False
            if prompt_quality >= 0.8 and satiety >= 85:
                hedonic, _multiplier = check_hedonic_override(satiety, prompt_quality)
                if hedonic:
                    voltage *= 2.0

            # 应用外部电压调制
            if modulated_voltage is not None:
                voltage = modulated_voltage

            # Step 3: DNA 信号匹配
            with self._driver.session(database=_DB_NAME) as session:
                candidates = session.run(
                    f"MATCH (n:{_ENTITY_LABEL} {{agent_id: $aid}}) "
                    "WHERE n.dna_left IS NOT NULL "
                    "RETURN n.label AS label, n.dna_left AS left, n.dna_right AS right, "
                    "n.dna_regions AS regions, n.expression_level AS expr",
                    aid=safe_aid,
                )

                scored = []
                for record in candidates:
                    try:
                        regions_data = record.get("regions", "[]")
                        if isinstance(regions_data, str):
                            import json
                            regions_data = json.loads(regions_data)
                    except Exception:
                        regions_data = None

                    score = compute_activation_score(
                        signal_dna, record["left"], record["right"],
                        regions_data, record.get("expr", 0.5),
                    )
                    scored.append((score, dict(record)))

                # 取 top 5
                scored.sort(key=lambda x: x[0], reverse=True)
                top5 = scored[:5]

                # Step 4: 计算各神经元激活电压
                activated_neurons = []
                for score, neuron in top5:
                    nv = compute_activation_voltage(score, neuron.get("expr", 0.5), voltage)
                    activated_neurons.append({
                        "label": neuron["label"],
                        "activation_voltage": nv,
                        "alignment_score": score,
                        "depth": 0,
                    })

                # Step 5: BFS 遍历
                traversed_edges = []
                all_weights = []
                max_depth = 0

                for i, neuron in enumerate(activated_neurons[:3]):  # 最多 3 个 winner
                    nv = neuron["activation_voltage"]
                    # 获取邻居边
                    edges = session.run(
                        f"""
                        MATCH (start:{_ENTITY_LABEL} {{label: $label, agent_id: $aid}})
                             -[r:RELATES_TO]-(neighbor:{_ENTITY_LABEL} {{agent_id: $aid}})
                        RETURN neighbor.label AS target, r.weight AS weight,
                               type(r) AS rel_type, startNode(r).label AS from_label,
                               endNode(r).label AS to_label
                        LIMIT 8
                        """,
                        label=neuron["label"], aid=safe_aid,
                    )

                    edge_list = []
                    for edge in edges:
                        w = edge.get("weight", 0.5)
                        if isinstance(w, (int, float)) and w > 0:
                            edge_list.append(w)
                            all_weights.append(w)

                    # 应用传导深度计算
                    if edge_list:
                        cd = compute_conduction_depth(nv, edge_list)
                        max_depth = max(max_depth, cd.max_depth)
                        # 记录 traversed edges（简化版）
                        for hop in range(min(cd.max_depth, len(edge_list))):
                            traversed_edges.append({
                                "source": neuron["label"],
                                "target": f"hop_{hop}",
                                "conductance": edge_list[hop],
                                "voltage": cd.decay_curve[hop] if hop < len(cd.decay_curve) else 0.0,
                                "hop": hop,
                            })

                # Step 6: 焦耳热
                joule_heat = accumulate_joule_heat(all_weights, max_depth)

                return {
                    "activated_neurons": activated_neurons,
                    "traversed_edges": traversed_edges,
                    "total_current_used": voltage,
                    "joule_heat": joule_heat,
                    "max_depth_reached": max_depth,
                    "hedonic_override": hedonic,
                    "early_terminated": joule_heat > 0.7,
                }

        except Exception as e:
            _log.warning("neo4j_service: activate_neurons_with_current failed: %s", e)
            return {"activated_neurons": [], "traversed_edges": [], "total_current_used": 0.0}

    # ── 赫布学习 ──────────────────────────────────────────────────────────

    def strengthen_edge(self, agent_id: str, src: str, tgt: str,
                        delta: float = 0.01, voltage: float = 0.0) -> bool:
        """赫布学习：强化共激活边。"""
        if self._driver is None:
            return False
        safe_aid = self._safe_agent_id(agent_id)
        try:
            with self._driver.session(database=_DB_NAME) as session:
                session.run(
                    f"""
                    MATCH (a:{_ENTITY_LABEL} {{label: $src, agent_id: $aid}})
                         -[r:RELATES_TO]-(b:{_ENTITY_LABEL} {{label: $tgt, agent_id: $aid}})
                    SET r.conductance = COALESCE(r.conductance, 0.5) + $delta,
                        r.current_flow = $voltage,
                        r.flow_count = COALESCE(r.flow_count, 0) + 1,
                        r.co_activation_count = COALESCE(r.co_activation_count, 0) + 1
                    """,
                    src=src, tgt=tgt, aid=safe_aid, delta=delta, voltage=voltage,
                )
            return True
        except Exception as e:
            _log.warning("neo4j_service: strengthen_edge failed: %s", e)
            return False

    # ── 突变管理 ──────────────────────────────────────────────────────────

    def accumulate_potential(self, agent_id: str, label: str, delta: float) -> float:
        """累积突变潜力（带代谢废物惩罚）。"""
        if self._driver is None:
            return 0.0
        safe_aid = self._safe_agent_id(agent_id)
        try:
            with self._driver.session(database=_DB_NAME) as session:
                record = session.run(
                    f"MATCH (n:{_ENTITY_LABEL} {{label: $label, agent_id: $aid}}) "
                    "RETURN n.mutation_potential AS p, n.metabolic_waste AS w",
                    label=label, aid=safe_aid,
                ).single()
                if not record:
                    return 0.0

                current = float(record.get("p", 0.0) or 0.0)
                waste = float(record.get("w", 0.0) or 0.0)
                effective_delta = delta * max(0.3, 1.0 - waste)
                new_val = current + effective_delta

                session.run(
                    f"MATCH (n:{_ENTITY_LABEL} {{label: $label, agent_id: $aid}}) "
                    "SET n.mutation_potential = $p",
                    label=label, aid=safe_aid, p=new_val,
                )
                return new_val
        except Exception as e:
            _log.warning("neo4j_service: accumulate_potential failed: %s", e)
            return 0.0

    def check_mutation(self, agent_id: str, label: str) -> dict | None:
        """检查是否需要执行突变。"""
        if self._driver is None:
            return None
        safe_aid = self._safe_agent_id(agent_id)
        try:
            with self._driver.session(database=_DB_NAME) as session:
                record = session.run(
                    f"MATCH (n:{_ENTITY_LABEL} {{label: $label, agent_id: $aid}}) "
                    "WHERE n.dna_left IS NOT NULL "
                    "RETURN n.dna_left AS left, n.dna_right AS right, "
                    "n.mutation_potential AS potential",
                    label=label, aid=safe_aid,
                ).single()
                if record and float(record.get("potential", 0.0) or 0.0) >= 1.0:
                    return {
                        "left": record["left"],
                        "right": record["right"],
                        "potential": float(record["potential"]),
                    }
            return None
        except Exception as e:
            _log.warning("neo4j_service: check_mutation failed: %s", e)
            return None

    def apply_mutation(self, agent_id: str, label: str,
                       new_left: str, new_right: str) -> bool:
        """原子性执行 DNA 突变。"""
        if self._driver is None:
            return False
        safe_aid = self._safe_agent_id(agent_id)
        try:
            with self._driver.session(database=_DB_NAME) as session:
                session.run(
                    f"MATCH (n:{_ENTITY_LABEL} {{label: $label, agent_id: $aid}}) "
                    "SET n.dna_left = $left, n.dna_right = $right, "
                    "n.mutation_potential = 0.0",
                    label=label, aid=safe_aid, left=new_left, right=new_right,
                )
            return True
        except Exception as e:
            _log.warning("neo4j_service: apply_mutation failed: %s", e)
            return False

    def prune_neuron_connections(self, agent_id: str, label: str) -> int:
        """突变后剪除旧域连接。"""
        if self._driver is None:
            return 0
        safe_aid = self._safe_agent_id(agent_id)
        try:
            with self._driver.session(database=_DB_NAME) as session:
                result = session.run(
                    f"""
                    MATCH (n:{_ENTITY_LABEL} {{label: $label, agent_id: $aid}})
                         -[r:RELATES_TO]-()
                    WHERE COALESCE(r.flow_count, 0) < 3
                    DELETE r
                    RETURN count(r) AS removed
                    """,
                    label=label, aid=safe_aid,
                )
                record = result.single()
                return record["removed"] if record else 0
        except Exception as e:
            _log.warning("neo4j_service: prune_neuron_connections failed: %s", e)
            return 0

    def form_new_synapses(self, agent_id: str, label: str) -> int:
        """突变后建立新域连接。"""
        if self._driver is None:
            return 0
        safe_aid = self._safe_agent_id(agent_id)
        try:
            with self._driver.session(database=_DB_NAME) as session:
                result = session.run(
                    f"""
                    MATCH (n:{_ENTITY_LABEL} {{label: $label, agent_id: $aid}})
                    MATCH (m:{_ENTITY_LABEL} {{agent_id: $aid}})
                    WHERE m.label <> n.label
                      AND NOT (n)-[:RELATES_TO]-(m)
                      AND COALESCE(m.frequency, 0) > 1
                    WITH n, m LIMIT 3
                    MERGE (n)-[r:RELATES_TO]->(m)
                    SET r.weight = 0.3, r.conductance = 0.3, r.is_hybrid_parent = false
                    RETURN count(r) AS created
                    """,
                    label=label, aid=safe_aid,
                )
                record = result.single()
                return record["created"] if record else 0
        except Exception as e:
            _log.warning("neo4j_service: form_new_synapses failed: %s", e)
            return 0

    def create_hybrid_neuron(self, agent_id: str, parent_a: str, parent_b: str,
                             child_label: str) -> bool:
        """跨节点杂交。"""
        if self._driver is None:
            return False
        safe_aid = self._safe_agent_id(agent_id)
        try:
            from backend.services.dna_service import hybridize
            dna_a = self.get_neuron_dna(agent_id, parent_a)
            dna_b = self.get_neuron_dna(agent_id, parent_b)
            if not dna_a or not dna_b:
                return False

            hybrid = hybridize(
                dna_a.get("left", ""), dna_a.get("right", ""),
                dna_b.get("left", ""), dna_b.get("right", ""),
            )
            if not hybrid:
                return False

            self.create_neuron(
                agent_id, child_label,
                dna_left=hybrid.get("child_left", ""),
                dna_right=hybrid.get("child_right", ""),
                expression_level=hybrid.get("expression_level", 0.5),
            )
            return True
        except Exception as e:
            _log.warning("neo4j_service: create_hybrid_neuron failed: %s", e)
            return False

    # ── 衰减 ──────────────────────────────────────────────────────────────

    def decay_node_properties(self, agent_id: str, timestamp: float | None = None) -> dict:
        """焦耳热 + 代谢废物衰减。"""
        import time as _time
        if self._driver is None:
            return {"decayed": 0}
        safe_aid = self._safe_agent_id(agent_id)
        try:
            from backend.services.neural_current import (
                compute_joule_heat_decay, compute_metabolic_waste_decay,
            )
            import time as t

            now = timestamp or t.time()
            decayed = 0

            with self._driver.session(database=_DB_NAME) as session:
                nodes = session.run(
                    f"MATCH (n:{_ENTITY_LABEL} {{agent_id: $aid}}) "
                    "WHERE n.joule_heat > 0 OR n.metabolic_waste > 0 "
                    "RETURN n.label AS label, n.joule_heat AS heat, "
                    "n.metabolic_waste AS waste, n.last_activated_at AS last",
                    aid=safe_aid,
                )
                for record in nodes:
                    elapsed = now - float(record.get("last", now) or now)
                    new_heat = compute_joule_heat_decay(
                        float(record.get("heat", 0) or 0), elapsed / 60
                    )
                    new_waste = compute_metabolic_waste_decay(
                        float(record.get("waste", 0) or 0), elapsed / 3600
                    )
                    session.run(
                        f"MATCH (n:{_ENTITY_LABEL} {{label: $label, agent_id: $aid}}) "
                        "SET n.joule_heat = $heat, n.metabolic_waste = $waste",
                        label=record["label"], aid=safe_aid,
                        heat=new_heat, waste=new_waste,
                    )
                    decayed += 1

            return {"decayed": decayed}
        except Exception as e:
            _log.warning("neo4j_service: decay_node_properties failed: %s", e)
            return {"decayed": 0}

    def current_driven_random_walk(self, agent_id: str, voltage: float,
                                   central_nodes: list[str] | None = None,
                                   max_depth: int = 5) -> list[dict]:
        """电压驱动随机游走（替换静态深度游走）。"""
        if self._driver is None:
            return []
        safe_aid = self._safe_agent_id(agent_id)
        try:
            from backend.services.neural_current import compute_conduction_depth

            with self._driver.session(database=_DB_NAME) as session:
                if not central_nodes:
                    central = self.get_central_nodes(agent_id, top_k=5, session=session)
                else:
                    central = central_nodes

                visited = set()
                results = []

                for start_label in central[:3]:
                    if start_label in visited:
                        continue

                    node = self._get_node_detail(session, start_label, safe_aid)
                    if not node:
                        continue

                    results.append({"node": node, "depth": 0, "voltage": voltage})
                    visited.add(start_label)

                    current_voltage = voltage
                    for depth in range(1, max_depth + 1):
                        neighbors = self._get_neighbors(session, start_label, safe_aid)
                        remaining = [n for n in neighbors if n not in visited]
                        if not remaining:
                            break

                        # 传导深度检查
                        weights = [0.5] * len(remaining[:5])  # 默认权重
                        cd = compute_conduction_depth(current_voltage, weights)
                        if not cd.can_continue and cd.max_depth == 0:
                            break

                        for nbr in remaining[:3]:
                            if nbr in visited:
                                continue
                            selected = self._get_node_detail(session, nbr, safe_aid)
                            if selected:
                                results.append({
                                    "node": selected, "depth": depth,
                                    "voltage": cd.remaining_voltage,
                                })
                                visited.add(nbr)
                        current_voltage = cd.remaining_voltage
                        if current_voltage < 0.01:
                            break

                return results
        except Exception as e:
            _log.warning("neo4j_service: current_driven_random_walk failed: %s", e)
            return []

    # ── 物品节点 CRUD ─────────────────────────────────────────────────────

    def create_item(self, agent_id: str, name: str, description: str = "",
                    x: int = 0, y: int = 0, category: str = "unknown",
                    mood_tags: list[str] | None = None,
                    interact_actions: list[str] | None = None) -> bool:
        """创建物品节点。"""
        if self._driver is None:
            return False
        safe_aid = self._safe_agent_id(agent_id)
        import json as _json
        try:
            tags_json = _json.dumps(mood_tags or [])
            actions_json = _json.dumps(interact_actions or [])
            with self._driver.session(database=_DB_NAME) as session:
                session.run(
                    """
                    MERGE (item:物品 {agent_id: $aid, name: $name})
                    SET item.description = $desc,
                        item.pos_x = $x,
                        item.pos_y = $y,
                        item.category = $cat,
                        item.mood_tags = $tags,
                        item.interact_actions = $actions
                    """,
                    aid=safe_aid, name=name, desc=description,
                    x=x, y=y, cat=category, tags=tags_json, actions=actions_json,
                )
            return True
        except Exception as e:
            _log.warning("neo4j_service: create_item failed: %s", e)
            return False

    def sync_items_from_map(self, agent_id: str, map_json: dict) -> dict:
        """从 Tiled 地图批量同步物品节点。"""
        try:
            from backend.services.spatial_perception import parse_tiled_interactive_objects
        except ImportError:
            return {"created": 0, "skipped": 0}

        items = parse_tiled_interactive_objects(map_json)
        created = 0
        for item in items:
            if self.create_item(
                agent_id, item.name, item.description,
                item.x, item.y, item.category,
                item.mood_tags, item.interact_actions,
            ):
                created += 1
        return {"created": created, "skipped": len(items) - created}

    def get_items_near_agent(self, agent_id: str, x: float, y: float,
                             threshold: float = 150) -> list[dict]:
        """查询 agent 附近的物品。"""
        if self._driver is None:
            return []
        safe_aid = self._safe_agent_id(agent_id)
        import math
        try:
            with self._driver.session(database=_DB_NAME) as session:
                records = session.run(
                    "MATCH (item:物品 {agent_id: $aid}) "
                    "RETURN item.name AS name, item.description AS description, "
                    "item.pos_x AS x, item.pos_y AS y, item.mood_tags AS tags, "
                    "item.interact_actions AS actions, item.category AS category",
                    aid=safe_aid,
                )
                nearby = []
                for r in records:
                    ix = float(r.get("x", 0) or 0)
                    iy = float(r.get("y", 0) or 0)
                    d = math.sqrt((x - ix) ** 2 + (y - iy) ** 2)
                    if d <= threshold:
                        nearby.append({
                            "name": r["name"],
                            "description": r.get("description", ""),
                            "x": ix, "y": iy, "distance": d,
                            "mood_tags": r.get("tags", "[]"),
                            "interact_actions": r.get("actions", "[]"),
                            "category": r.get("category", ""),
                        })
                nearby.sort(key=lambda n: n["distance"])
                return nearby[:5]
        except Exception as e:
            _log.warning("neo4j_service: get_items_near_agent failed: %s", e)
            return []

    def update_agent_location(self, agent_id: str, agent_label: str,
                              x: float, y: float) -> None:
        """更新 agent 位置并重建 LOCATED_NEAR 关系。"""
        if self._driver is None:
            return
        safe_aid = self._safe_agent_id(agent_id)
        try:
            with self._driver.session(database=_DB_NAME) as session:
                # 删除旧关系
                session.run(
                    f"MATCH (a:{_ENTITY_LABEL} {{label: $label, agent_id: $aid}})"
                    "-[r:LOCATED_NEAR]->() DELETE r",
                    label=agent_label, aid=safe_aid,
                )
                # 找附近物品并创建关系
                items = session.run(
                    "MATCH (item:物品 {agent_id: $aid}) "
                    "RETURN item.name AS name, item.pos_x AS x, item.pos_y AS y",
                    aid=safe_aid,
                )
                import math
                for r in items:
                    ix = float(r.get("x", 0) or 0)
                    iy = float(r.get("y", 0) or 0)
                    d = math.sqrt((x - ix) ** 2 + (y - iy) ** 2)
                    if d <= 150:
                        session.run(
                            f"""
                            MATCH (a:{_ENTITY_LABEL} {{label: $label, agent_id: $aid}})
                            MATCH (item:物品 {{name: $item_name, agent_id: $aid}})
                            MERGE (a)-[r:LOCATED_NEAR]->(item)
                            SET r.distance = $dist
                            """,
                            label=agent_label, aid=safe_aid,
                            item_name=r["name"], dist=d,
                        )
        except Exception as e:
            _log.warning("neo4j_service: update_agent_location failed: %s", e)

    def query_item_emotions(self, agent_id: str, item_name: str) -> dict:
        """查询物品的情绪关联。"""
        if self._driver is None:
            return {"tags": [], "emotions": []}
        safe_aid = self._safe_agent_id(agent_id)
        try:
            with self._driver.session(database=_DB_NAME) as session:
                record = session.run(
                    """
                    MATCH (item:物品 {name: $name, agent_id: $aid})
                    RETURN item.mood_tags AS tags
                    """,
                    name=item_name, aid=safe_aid,
                ).single()

                import json
                tags = []
                if record:
                    raw = record.get("tags", "[]")
                    if isinstance(raw, str):
                        try:
                            tags = json.loads(raw)
                        except json.JSONDecodeError:
                            tags = []
                    elif isinstance(raw, list):
                        tags = raw

                return {"tags": tags, "emotions": []}
        except Exception as e:
            _log.warning("neo4j_service: query_item_emotions failed: %s", e)
            return {"tags": [], "emotions": []}


# ── 单例工厂 ─────────────────────────────────────────────────────────────

_service: Neo4jService | None = None


def get_neo4j_service() -> Neo4jService:
    """获取 Neo4jService 全局单例。"""
    global _service
    if _service is None:
        _service = Neo4jService()
    return _service


# ── 向后兼容的模块级函数 ─────────────────────────────────────────────

def import_kg_to_neo4j(agent_id, nodes, edges):
    """[已废弃] 导入知识图谱。请使用 ``get_neo4j_service().import_kg()``。"""
    return get_neo4j_service().import_kg(agent_id, nodes, edges)


def prune_irrelevant_nodes(agent_id, all_labels):
    """[已废弃] 过滤无关节点。请使用 ``get_neo4j_service().prune_irrelevant()``。"""
    return get_neo4j_service().prune_irrelevant(agent_id, all_labels)


def random_walk_from_center(agent_id, max_depth=5, max_nodes=20):
    """[已废弃] 随机游走。请使用 ``get_neo4j_service().random_walk()``。"""
    return get_neo4j_service().random_walk(
        agent_id, max_depth=max_depth, max_nodes=max_nodes,
    )
