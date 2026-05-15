"""知识图谱服务 — 构建、查询、Mermaid 格式化导出。

从向量库的记忆条目中自动抽取实体和关系，构建结构化知识图谱，
在会话中按需提供关联知识（需求 D, Gap 5）。

特性：
- 增量构建：仅在新增记忆时触发，debounce 30 秒
- Mermaid 导出：生成 ``graph TD`` 格式用于前端可视化
- 邻居查询：支持 1 度邻居搜索，用于 ``<memory-context>`` 注入
- Per-agent 隔离：每个 Agent 拥有独立的知识图谱分表
"""

from __future__ import annotations

import logging
import re
import threading
import time
from typing import Any

from backend.db.knowledge import KnowledgeNodeDAO, KnowledgeEdgeDAO

_log = logging.getLogger(__name__)

# ── 常量 ──────────────────────────────────────────────────────────────────────

BUILD_DEBOUNCE_SECONDS = 30  # 增量构建防抖间隔
NEIGHBOR_DEGREE_DEFAULT = 1  # 默认邻居查询度数
MAX_GRAPH_NODES_IN_CONTEXT = 5  # <memory-context> 中最多注入的图谱节点数

# ── 防抖状态 ──────────────────────────────────────────────────────────────────

_last_build_time: dict[str, float] = {}
_build_lock = threading.Lock()


# ── 核心构建 ──────────────────────────────────────────────────────────────────


def build_graph_incremental(
    agent_id: str,
    memory_entries: list[dict] | None = None,
    force: bool = False,
) -> dict:
    """增量构建/更新 Agent 的知识图谱。

    使用 LLM 从 memory_entries 中提取实体和关系，写入知识图谱分表。

    Args:
        agent_id: Agent ID
        memory_entries: 要处理的新记忆条目 [{category, content}, ...]
        force: 是否强制执行（跳过 debounce）

    Returns:
        {"nodes_added": int, "edges_added": int, "nodes_total": int}
    """
    # debounce 检查
    now = time.time()
    with _build_lock:
        last = _last_build_time.get(agent_id, 0)
        if not force and (now - last) < BUILD_DEBOUNCE_SECONDS:
            return {"nodes_added": 0, "edges_added": 0, "nodes_total": 0, "skipped": True}
        _last_build_time[agent_id] = now

    if not memory_entries:
        return {"nodes_added": 0, "edges_added": 0, "nodes_total": 0}

    # 构建提取 prompt
    entries_text = "\n".join(
        f"- [{e.get('category', 'general')}] {e.get('content', '')}"
        for e in memory_entries[:20]
    )

    prompt = (
        "从以下记忆条目中提取实体和关系。\n\n"
        "实体类型（type）：concept（概念）、tool（工具/技术）、project（项目）、"
        "person（人物）、decision（决策）\n"
        "关系类型（relation）：uses（使用）、includes（包含）、depends_on（依赖）、"
        "alternative_to（替代）、related_to（关联）\n\n"
        "记忆条目：\n"
        f"{entries_text}\n\n"
        "返回 JSON 数组，格式：\n"
        '{"nodes": [{"label": "实体名", "type": "类型", "summary": "一句话描述"}], '
        '"edges": [{"source": "源实体名", "target": "目标实体名", '
        '"relation": "关系类型", "evidence": "支撑证据"}]}\n'
        "只返回 JSON，不要附加其他文字。"
    )

    try:
        result = _call_llm_for_extraction(agent_id, prompt)
        if not result:
            return {"nodes_added": 0, "edges_added": 0, "nodes_total": 0, "error": "LLM 提取失败"}

        nodes = result.get("nodes", [])
        edges = result.get("edges", [])

        # 写入数据库
        nodes_added = 0
        edges_added = 0

        for node in nodes:
            node_id = KnowledgeNodeDAO.upsert_node(
                agent_id,
                label=str(node.get("label", "")).strip(),
                node_type=str(node.get("type", "concept")).strip(),
                summary=str(node.get("summary", "")).strip(),
            )
            if node_id:
                nodes_added += 1

        # 先获取所有节点以建立 label→id 映射
        all_nodes = KnowledgeNodeDAO.get_all_nodes(agent_id)
        label_to_id = {n["label"]: n["id"] for n in all_nodes}

        for edge in edges:
            src_label = str(edge.get("source", "")).strip()
            tgt_label = str(edge.get("target", "")).strip()
            src_id = label_to_id.get(src_label)
            tgt_id = label_to_id.get(tgt_label)
            if src_id and tgt_id:
                edge_id = KnowledgeEdgeDAO.upsert_edge(
                    agent_id,
                    source_id=src_id,
                    target_id=tgt_id,
                    relation=str(edge.get("relation", "related_to")).strip(),
                    evidence=str(edge.get("evidence", "")).strip(),
                )
                if edge_id:
                    edges_added += 1

        total_nodes = len(KnowledgeNodeDAO.get_all_nodes(agent_id))
        return {
            "nodes_added": nodes_added,
            "edges_added": edges_added,
            "nodes_total": total_nodes,
        }
    except Exception as e:
        _log.warning("build_graph_incremental(%s) failed: %s", agent_id, e)
        return {"nodes_added": 0, "edges_added": 0, "nodes_total": 0, "error": str(e)}


def query_knowledge_graph(
    agent_id: str,
    entities: list[str],
    max_neighbors: int = MAX_GRAPH_NODES_IN_CONTEXT,
) -> str:
    """查询知识图谱中与给定实体相关的关联知识。

    用于 ``<memory-context>`` 注入，返回格式化的知识图谱上下文文本。

    Args:
        agent_id: Agent ID
        entities: 从用户消息中提取的实体列表
        max_neighbors: 最多返回的关联节点数

    Returns:
        格式化的知识图谱上下文，如：
        ``- React（概念）：前端框架 → 使用 Zustand（状态管理）``
    """
    if not entities:
        return ""

    # 查找命中的节点
    nodes = KnowledgeNodeDAO.find_by_labels(agent_id, entities)
    if not nodes:
        return ""

    # 获取邻居
    node_ids = [n["id"] for n in nodes]
    neighbors_map = KnowledgeEdgeDAO.get_neighbors_for_nodes(agent_id, node_ids)

    # 格式化输出
    lines: list[str] = []
    for node in nodes:
        node_type_cn = {
            "concept": "概念", "tool": "工具/技术", "project": "项目",
            "person": "人物", "decision": "决策",
        }.get(node["type"], node["type"])

        base = f"- {node['label']}（{node_type_cn}）"
        if node.get("summary"):
            base += f"：{node['summary']}"

        neighbors = neighbors_map.get(node["id"], [])
        if neighbors:
            relation_cn = {
                "uses": "使用", "includes": "包含",
                "depends_on": "依赖", "alternative_to": "替代",
                "related_to": "关联",
            }
            neighbor_strs = []
            for nb in neighbors[:3]:
                rel = relation_cn.get(nb.get("relation", ""), nb.get("relation", ""))
                nb_label = nb.get("label", "")
                nb_summary = nb.get("summary", "")
                n_text = f"{rel} {nb_label}"
                if nb_summary:
                    n_text += f"（{nb_summary}）"
                neighbor_strs.append(n_text)
            if neighbor_strs:
                base += " → " + " | ".join(neighbor_strs)

        lines.append(base)

    return "\n".join(lines[:max_neighbors])


# ── Mermaid 格式导出 ──────────────────────────────────────────────────────────


def build_mermaid_graph(agent_id: str) -> str:
    """从知识图谱表生成 Mermaid ``graph TD`` 格式。

    用于前端可视化展示实体和关系图。

    Returns:
        Mermaid 格式的图谱源码，可直接被 mermaid.js 渲染。
    """
    nodes = KnowledgeNodeDAO.get_all_nodes(agent_id)
    edges = KnowledgeEdgeDAO.get_all_edges(agent_id)

    if not nodes:
        return "graph TD\n    empty[\"暂无知识图谱数据\"]"

    lines = ["graph TD"]

    # 生成节点
    for n in nodes:
        safe_id = re.sub(r"\W", "_", n["label"])
        label_text = n["label"].replace('"', "'")
        summary = (n.get("summary") or "").replace('"', "'")
        if summary:
            display = f"{label_text}<br/>{summary[:60]}"
        else:
            display = label_text
        lines.append(f'    {safe_id}["{display}"]')

    # 生成边
    for e in edges:
        src = re.sub(r"\W", "_", e["source_label"])
        tgt = re.sub(r"\W", "_", e["target_label"])
        rel = e["relation"].replace('"', "'")
        lines.append(f"    {src} -->|{rel}| {tgt}")

    return "\n".join(lines)


# ── 内部辅助 ──────────────────────────────────────────────────────────────────


def _call_llm_for_extraction(agent_id: str, prompt: str) -> dict | None:
    """调用 Agent 的 LLM 进行实体关系提取。

    通过创建临时 session 提交 prompt 并获取 JSON 响应。
    如果 Agent 未运行，尝试使用 GatewayManager 的通用 LLM 调用接口。
    """
    try:
        from backend.services.agent import _get_manager
        mgr = _get_manager()
        info = mgr.get_agent(agent_id)
        if info is None:
            _log.warning("knowledge_graph: agent %s not found", agent_id)
            return None

        gw = info.gateway
        if not gw.is_alive():
            _log.warning("knowledge_graph: agent %s not alive", agent_id)
            return None

        # 创建临时 session 进行提取
        temp_sid = gw.create_session()
        if not temp_sid:
            return None

        done = threading.Event()
        state: dict = {"reply": "", "err": ""}

        def handler(ev: dict) -> None:
            if str(ev.get("session_id") or "") != temp_sid:
                return
            et = str(ev.get("type") or "")
            pl = ev.get("payload") or {}
            if et == "message.complete":
                state["reply"] = str(pl.get("text") or "")
                done.set()
            elif et == "error":
                state["err"] = str(pl.get("message", pl))
                done.set()

        gw.on_event(handler)
        try:
            ok = gw.submit_prompt(temp_sid, prompt)
            if not ok:
                return None
            if not done.wait(timeout=120.0):
                return None
            if state["err"]:
                return None

            # 解析 LLM 返回的 JSON
            reply = state["reply"]
            return _parse_llm_json(reply)
        finally:
            gw.remove_event(handler)
            try:
                gw.close_session(temp_sid)
            except Exception:
                pass
    except Exception as e:
        _log.warning("knowledge_graph: LLM extraction failed: %s", e)
    return None


def _parse_llm_json(text: str) -> dict:
    """从 LLM 回复中提取 JSON，支持 Markdown 围栏代码块。"""
    import json

    # 尝试提取 ```json ... ``` 围栏内容
    fence_match = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if fence_match:
        text = fence_match.group(1).strip()

    # 尝试找到第一个 { 和最后一个 }
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        text = text[start:end + 1]

    return json.loads(text)


# ── 模块导出 ──────────────────────────────────────────────────────────────────

__all__ = [
    "build_graph_incremental",
    "query_knowledge_graph",
    "build_mermaid_graph",
]
