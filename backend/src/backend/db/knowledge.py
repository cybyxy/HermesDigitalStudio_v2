"""知识图谱数据访问对象 — 操作 ``kgnode_{agent_id}`` / ``kgedge_{agent_id}`` 表。

每个 Agent 拥有独立的知识图谱分表：
- ``kgnode_{agent_id}`` — 实体节点（concept / tool / project / person / decision）
- ``kgedge_{agent_id}`` — 实体关系边（uses / includes / depends_on / alternative_to / related_to）
"""

from __future__ import annotations

import logging
import re

from backend.db.connection import get_connection, ensure_agent_memory_tables

_log = logging.getLogger(__name__)

_SAFE_ID_RE = re.compile(r"\W")

_VALID_NODE_TYPES = frozenset({"concept", "tool", "project", "person", "decision"})
_VALID_RELATIONS = frozenset({
    "uses", "includes", "depends_on", "alternative_to", "related_to",
})


def _safe_agent_id(agent_id: str) -> str:
    return _SAFE_ID_RE.sub("_", agent_id).strip("_") or "unknown"


# ── KnowledgeNodeDAO ──────────────────────────────────────────────────────────


class KnowledgeNodeDAO:
    """知识图谱节点 DAO — 操作 ``kgnode_{agent_id}`` 表。"""

    @classmethod
    def ensure_table(cls, agent_id: str) -> None:
        safid = _safe_agent_id(agent_id)
        conn = get_connection()
        try:
            ensure_agent_memory_tables(agent_id, conn)
        finally:
            conn.close()

    @classmethod
    def upsert_node(
        cls,
        agent_id: str,
        label: str,
        node_type: str,
        summary: str = "",
    ) -> int:
        """插入或更新节点，返回节点 id。"""
        import time

        node_type = node_type if node_type in _VALID_NODE_TYPES else "concept"
        safid = _safe_agent_id(agent_id)
        conn = get_connection()
        try:
            ensure_agent_memory_tables(agent_id, conn)
            now = time.time()
            # 先尝试 update
            cur = conn.execute(
                f"SELECT id, summary FROM kgnode_{safid} WHERE label = ?",
                (label,),
            )
            existing = cur.fetchone()
            if existing:
                node_id = existing[0]
                # 合并 summary（新 summary 不为空时覆盖）
                new_summary = summary if summary else existing[1]
                conn.execute(
                    f"UPDATE kgnode_{safid} SET type = ?, summary = ?, updated_at = ? "
                    f"WHERE id = ?",
                    (node_type, new_summary or "", now, node_id),
                )
            else:
                cur = conn.execute(
                    f"INSERT INTO kgnode_{safid} (label, type, summary, created_at, updated_at) "
                    f"VALUES (?, ?, ?, ?, ?)",
                    (label, node_type, summary, now, now),
                )
                node_id = cur.lastrowid
            conn.commit()
            return node_id
        except Exception as e:
            _log.warning("KnowledgeNodeDAO.upsert_node(%s) failed: %s", agent_id, e)
            return 0
        finally:
            conn.close()

    @classmethod
    def get_all_nodes(cls, agent_id: str) -> list[dict]:
        """获取 Agent 的所有知识图谱节点。"""
        safid = _safe_agent_id(agent_id)
        conn = get_connection()
        try:
            ensure_agent_memory_tables(agent_id, conn)
            cur = conn.execute(
                f"SELECT id, label, type, summary, created_at, updated_at "
                f"FROM kgnode_{safid} ORDER BY type, label",
            )
            return [
                {
                    "id": r[0],
                    "label": r[1],
                    "type": r[2],
                    "summary": r[3] or "",
                    "created_at": r[4],
                    "updated_at": r[5],
                }
                for r in cur.fetchall()
            ]
        except Exception as e:
            _log.debug("KnowledgeNodeDAO.get_all_nodes(%s) failed: %s", agent_id, e)
            return []
        finally:
            conn.close()

    @classmethod
    def find_by_label(cls, agent_id: str, label: str) -> dict | None:
        """按 label 查找节点。"""
        safid = _safe_agent_id(agent_id)
        conn = get_connection()
        try:
            ensure_agent_memory_tables(agent_id, conn)
            cur = conn.execute(
                f"SELECT id, label, type, summary FROM kgnode_{safid} WHERE label = ?",
                (label,),
            )
            row = cur.fetchone()
            if row:
                return {
                    "id": row[0],
                    "label": row[1],
                    "type": row[2],
                    "summary": row[3] or "",
                }
        except Exception:
            pass
        finally:
            conn.close()
        return None

    @classmethod
    def find_by_labels(cls, agent_id: str, labels: list[str]) -> list[dict]:
        """批量查找多个 label 对应的节点。"""
        if not labels:
            return []
        safid = _safe_agent_id(agent_id)
        conn = get_connection()
        try:
            ensure_agent_memory_tables(agent_id, conn)
            placeholders = ",".join("?" * len(labels))
            cur = conn.execute(
                f"SELECT id, label, type, summary FROM kgnode_{safid} "
                f"WHERE label IN ({placeholders})",
                labels,
            )
            return [
                {
                    "id": r[0],
                    "label": r[1],
                    "type": r[2],
                    "summary": r[3] or "",
                }
                for r in cur.fetchall()
            ]
        except Exception:
            return []
        finally:
            conn.close()


# ── KnowledgeEdgeDAO ──────────────────────────────────────────────────────────


class KnowledgeEdgeDAO:
    """知识图谱边 DAO — 操作 ``kgedge_{agent_id}`` 表。"""

    @classmethod
    def ensure_table(cls, agent_id: str) -> None:
        safid = _safe_agent_id(agent_id)
        conn = get_connection()
        try:
            ensure_agent_memory_tables(agent_id, conn)
        finally:
            conn.close()

    @classmethod
    def upsert_edge(
        cls,
        agent_id: str,
        source_id: int,
        target_id: int,
        relation: str,
        evidence: str = "",
    ) -> int:
        """插入或更新关系边，返回边 id。"""
        import time

        relation = relation if relation in _VALID_RELATIONS else "related_to"
        safid = _safe_agent_id(agent_id)
        conn = get_connection()
        try:
            ensure_agent_memory_tables(agent_id, conn)
            now = time.time()
            conn.execute(
                f"INSERT OR REPLACE INTO kgedge_{safid} "
                f"(source_id, target_id, relation, evidence, created_at) "
                f"VALUES (?, ?, ?, ?, ?)",
                (source_id, target_id, relation, evidence, now),
            )
            conn.commit()
            return conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        except Exception as e:
            _log.warning("KnowledgeEdgeDAO.upsert_edge(%s) failed: %s", agent_id, e)
            return 0
        finally:
            conn.close()

    @classmethod
    def get_all_edges(cls, agent_id: str) -> list[dict]:
        """获取 Agent 的所有知识图谱边（含 source/target label）。"""
        safid = _safe_agent_id(agent_id)
        conn = get_connection()
        try:
            ensure_agent_memory_tables(agent_id, conn)
            cur = conn.execute(
                f"SELECT e.id, e.source_id, e.target_id, e.relation, e.evidence, "
                f"  s.label AS source_label, t.label AS target_label "
                f"FROM kgedge_{safid} e "
                f"JOIN kgnode_{safid} s ON e.source_id = s.id "
                f"JOIN kgnode_{safid} t ON e.target_id = t.id "
                f"ORDER BY e.relation",
            )
            return [
                {
                    "id": r[0],
                    "source_id": r[1],
                    "target_id": r[2],
                    "relation": r[3],
                    "evidence": r[4] or "",
                    "source_label": r[5],
                    "target_label": r[6],
                }
                for r in cur.fetchall()
            ]
        except Exception as e:
            _log.debug("KnowledgeEdgeDAO.get_all_edges(%s) failed: %s", agent_id, e)
            return []
        finally:
            conn.close()

    @classmethod
    def get_neighbors(cls, agent_id: str, node_id: int, degree: int = 1) -> list[dict]:
        """获取某节点的指定度数邻居节点（含关系）。

        返回邻居节点信息 + 到达关系，用于在 ``<memory-context>`` 中注入关联知识。
        """
        safid = _safe_agent_id(agent_id)
        conn = get_connection()
        try:
            ensure_agent_memory_tables(agent_id, conn)
            cur = conn.execute(
                f"SELECT DISTINCT n.id, n.label, n.type, n.summary, e.relation "
                f"FROM kgedge_{safid} e "
                f"JOIN kgnode_{safid} n ON "
                f"  (e.target_id = n.id AND e.source_id = ?) "
                f"  OR (e.source_id = n.id AND e.target_id = ?) "
                f"WHERE n.id != ?",
                (node_id, node_id, node_id),
            )
            return [
                {
                    "id": r[0],
                    "label": r[1],
                    "type": r[2],
                    "summary": r[3] or "",
                    "relation": r[4],
                }
                for r in cur.fetchall()
            ]
        except Exception:
            return []
        finally:
            conn.close()

    @classmethod
    def get_neighbors_for_nodes(
        cls,
        agent_id: str,
        node_ids: list[int],
        degree: int = 1,
    ) -> dict[int, list[dict]]:
        """批量获取多个节点的邻居，返回 {node_id: [neighbors]} 映射。"""
        result: dict[int, list[dict]] = {}
        for nid in node_ids:
            neighbors = cls.get_neighbors(agent_id, nid, degree)
            if neighbors:
                result[nid] = neighbors
        return result
