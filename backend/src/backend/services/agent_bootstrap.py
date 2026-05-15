"""Agent 启动引导 — 重启后自动恢复记忆上下文。

在每个 Agent 子进程启动后，后台线程执行：
1. 从 MemOS 向量库读取最后会话内容
2. 从 state.db 读取知识图谱（kgnode_/kgedge_ 表）
3. 导入 Neo4j 做度中心性验证，过滤无关关键词
4. 构建启动恢复上下文
5. 写入 bootstrap 缓存文件（由 memory_context.py 在子进程首次推理时注入）
"""

from __future__ import annotations

import json
import logging
import threading
import time
from pathlib import Path
from typing import Any

_log = logging.getLogger(__name__)

# ── 常量 ──────────────────────────────────────────────────────────────────

_MAX_BOOTSTRAP_TIME_SEC = 60  # 每个 agent 最大引导时间


# ── 公开入口 ──────────────────────────────────────────────────────────────


def bootstrap_all_agents(mgr) -> None:
    """为所有已启动的 Agent 执行启动引导（后台线程）。"""
    agents = mgr.list_agents()
    if not agents:
        _log.info("agent_bootstrap: 无 Agent，跳过引导")
        return

    _log.info("agent_bootstrap: 开始引导 %d 个 Agent", len(agents))
    threads: list[threading.Thread] = []

    for agent_id in agents:
        # 获取默认 session（idempotent，已有则返回现有 session_id）
        try:
            sid = mgr.ensure_default_session(agent_id, cols=120)
        except Exception as e:
            _log.warning("agent_bootstrap: %s 获取 session 失败: %s", agent_id, e)
            continue

        if not sid:
            _log.warning("agent_bootstrap: %s 无可用 session，跳过", agent_id)
            continue

        t = threading.Thread(
            target=_bootstrap_single_agent,
            args=(agent_id, sid),
            daemon=True,
            name=f"agent-bootstrap-{agent_id}",
        )
        t.start()
        threads.append(t)

    # 等待所有 bootstrap 完成（不超过每个 agent 的最大时间）
    deadline = time.time() + _MAX_BOOTSTRAP_TIME_SEC
    for t in threads:
        remaining = deadline - time.time()
        if remaining > 0:
            t.join(timeout=remaining)
        else:
            break

    _log.info("agent_bootstrap: 引导完成（%d/%d 个 Agent）", len(threads), len(agents))


def bootstrap_single_agent(agent_id: str, session_id: str) -> dict:
    """为单个 Agent 执行启动引导（同步，可在外部调用）。"""
    return _bootstrap_single_agent(agent_id, session_id)


# ── 核心流程 ──────────────────────────────────────────────────────────────


def _bootstrap_single_agent(agent_id: str, session_id: str) -> dict:
    """单 Agent 引导流程。"""
    start_time = time.time()
    result = {
        "agent_id": agent_id,
        "session_id": session_id,
        "memos_ok": False,
        "db_kg_ok": False,
        "neo4j_pruned": 0,
        "neo4j_kept": 0,
        "context_built": False,
        "error": None,
    }

    try:
        # Step 1: 从 MemOS 读取最后会话内容
        memos_context = ""
        try:
            memos_context = _recall_last_session(agent_id)
            result["memos_ok"] = True
        except Exception as e:
            _log.warning("agent_bootstrap: %s MemOS 会话回忆失败: %s", agent_id, e)

        # Step 2: 从 state.db 读取知识图谱
        nodes: list[dict] = []
        edges: list[dict] = []
        try:
            nodes, edges = _read_state_db_knowledge_graph(agent_id)
            result["db_kg_ok"] = len(nodes) > 0
        except Exception as e:
            _log.warning("agent_bootstrap: %s state.db 图谱读取失败: %s", agent_id, e)

        # Step 3: Neo4j 验证 + 过滤无关关键词
        all_labels = [n.get("label", "") for n in nodes if n.get("label")]
        central_labels = all_labels
        try:
            import backend.services.neo4j_service as _neo4j

            imported_count = _neo4j.import_kg_to_neo4j(agent_id, nodes, edges)
            central_labels = _neo4j.prune_irrelevant_nodes(agent_id, all_labels)
            result["neo4j_pruned"] = len(all_labels) - len(central_labels)
            result["neo4j_kept"] = len(central_labels)
        except Exception as e:
            _log.warning("agent_bootstrap: %s Neo4j 验证失败: %s", agent_id, e)

        # Step 4: 构建启动上下文
        context_text = _build_startup_context(
            agent_id=agent_id,
            memos_context=memos_context,
            central_entities=central_labels,
            node_count=len(nodes),
            edge_count=len(edges),
        )
        result["context_built"] = bool(context_text)

        # Step 5: 写入缓存文件
        _write_bootstrap_cache(agent_id, context_text, central_labels)
        elapsed = time.time() - start_time
        _log.info(
            "agent_bootstrap: %s 引导成功 (%.1fs), memos=%s db_kg=%s entities=%d/%d",
            agent_id,
            elapsed,
            result["memos_ok"],
            result["db_kg_ok"],
            result["neo4j_kept"],
            len(all_labels),
        )

    except Exception as e:
        result["error"] = str(e)
        _log.warning("agent_bootstrap: %s 引导整体失败: %s", agent_id, e)

    return result


# ── Step 1: MemOS 会话回忆 ───────────────────────────────────────────────


def _recall_last_session(agent_id: str) -> str:
    """从 MemOS 向量库搜索最近会话记忆。"""
    try:
        from backend.services.mem_os_service import mos_search

        memories = mos_search(agent_id, "最近对话 讨论 历史 重点", top_k=5)
        if memories:
            return "\n".join(f"- {m}" for m in memories)
    except Exception:
        pass

    # 回退：读取 schema.db 中的 session titles
    try:
        from backend.core.config import get_config

        hermes_home = get_config().hermes_home
        state_db = hermes_home / "state.db"
        if state_db.is_file():
            import sqlite3

            conn = sqlite3.connect(str(state_db))
            rows = conn.execute(
                "SELECT id, title FROM sessions ORDER BY started_at DESC LIMIT 3"
            ).fetchall()
            conn.close()
            if rows:
                return "\n".join(f"- [{row[0][:8]}...] {row[1] or '(无标题)'}" for row in rows)
    except Exception:
        pass

    return ""


# ── Step 2: state.db 知识图谱读取 ─────────────────────────────────────────


def _read_state_db_knowledge_graph(agent_id: str) -> tuple[list[dict], list[dict]]:
    """从 state.db kgnode_/kgedge_ 表读取知识图谱的节点和边。

    返回: (nodes, edges)
      - nodes: [{"label": "React", "frequency": 1, "summary": "..."}, ...]
      - edges: [{"source": "React", "target": "TypeScript", "weight": 1}, ...]
    """
    try:
        from backend.db.knowledge import KnowledgeNodeDAO, KnowledgeEdgeDAO

        nodes_raw = KnowledgeNodeDAO.get_all_nodes(agent_id)
        edges_raw = KnowledgeEdgeDAO.get_all_edges(agent_id)

        nodes = [
            {"label": n["label"], "frequency": 1, "summary": n.get("summary", "")}
            for n in nodes_raw
        ]
        edges = [
            {"source": e["source_label"], "target": e["target_label"], "weight": 1}
            for e in edges_raw
        ]

        _log.debug(
            "agent_bootstrap: %s 从 state.db 读取到 %d 节点, %d 边",
            agent_id, len(nodes), len(edges),
        )
        return nodes, edges

    except Exception as e:
        _log.debug("agent_bootstrap: %s state.db KG 读取失败: %s", agent_id, e)
        return [], []


# ── Step 4: 构建启动上下文 ───────────────────────────────────────────────


def _build_startup_context(
    agent_id: str,
    memos_context: str,
    central_entities: list[str],
    node_count: int,
    edge_count: int,
) -> str:
    """组装启动恢复上下文的纯文本块。"""
    parts: list[str] = []

    # 身份声明
    display_name = agent_id.capitalize()
    try:
        from backend.services.soul_md import read_soul_md

        soul = read_soul_md(agent_id)
        if soul and soul.get("identity"):
            display_name = soul["identity"].get("name", display_name)
    except Exception:
        pass

    parts.append(f"你是 {display_name}，刚刚从重启中恢复。以下是你的记忆摘要：")

    # 最近会话记忆
    if memos_context:
        parts.append(f"\n## 最近对话记忆\n{memos_context}")

    # 核心知识图谱实体
    if central_entities:
        entities_str = "、".join(central_entities[:20])
        parts.append(
            f"\n## 知识图谱核心实体\n"
            f"你的知识图谱中有 {node_count} 个实体、{edge_count} 条关系，"
            f"其中核心实体包括: {entities_str}"
        )

    if not memos_context and not central_entities:
        parts.append("\n（暂无可恢复的记忆，这是一个全新的开始。）")

    return "\n".join(parts)


# ── Step 5: 写入缓存文件 ─────────────────────────────────────────────────


def _write_bootstrap_cache(agent_id: str, context: str, entities: list[str]) -> None:
    """将启动引导结果写入缓存文件，供子进程 memory_context.py 读取。"""
    try:
        from backend.services.mem_os_service import _get_memos_dir

        cache_dir = Path(_get_memos_dir()) / "agent_bootstrap"
        cache_dir.mkdir(parents=True, exist_ok=True)

        cache_file = cache_dir / f"{agent_id}.json"
        data = {
            "agent_id": agent_id,
            "context": context,
            "entities": entities,
            "timestamp": time.time(),
        }
        cache_file.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        _log.debug("agent_bootstrap: 缓存已写入 %s", cache_file)

    except Exception as e:
        _log.warning("agent_bootstrap: 缓存写入失败: %s", e)
