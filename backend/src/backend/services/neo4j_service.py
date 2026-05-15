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
