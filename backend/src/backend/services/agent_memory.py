"""Agent 记忆聚合模块：SOUL.md、state.db、Session 历史、技能列表。

从 services/agent.py 提取的自包含子模块，负责完整 RAM/系统信息聚合。
"""

from __future__ import annotations

import logging
import sqlite3
import sys
import threading
from pathlib import Path

_log = logging.getLogger(__name__)

# ── vendor path helper ───────────────────────────────────────────────────────


def _ensure_vendor_on_path() -> None:
    """确保 vendor/hermes-agent 在 sys.path 中，以便导入 hermes_state 等模块。"""
    from pathlib import Path as _Path
    # agent_memory.py 位于 backend/src/backend/services/ — parents[3] = backend/ dir
    _BACKEND_DIR = _Path(__file__).resolve().parents[3]
    _HERMES_VENDOR_ROOT = _BACKEND_DIR.parent / "vendor" / "hermes-agent"
    v = str(_HERMES_VENDOR_ROOT)
    if v not in sys.path:
        sys.path.insert(0, v)


def _read_hermes_session_titles(agent_id: str, info) -> list[dict]:
    """从 Agent 的 Hermes state.db 读取所有 session 的 title 数据。

    通过 ``agent_sessions`` 表获取该 agent 的所有 session_key，
    再打开 Hermes state.db 按 ``sessions.id`` 查询 title 列。
    返回 [{sessionKey, title, startedAt}, ...]。
    """
    from backend.services import agent_db as _agent_db

    # 1. 获取所有 session_key
    sessions = _agent_db.list_agent_sessions(agent_id)
    session_keys = [s.get("session_key") for s in sessions if s.get("session_key")]
    if not session_keys:
        return []

    # 2. 推导 hermes_home
    gw_home = getattr(info.gateway, "hermes_home", None)
    if gw_home:
        hermes_home = str(Path(gw_home).expanduser())
    else:
        from backend.services.profile_scanner import _hermes_home_path_for_profile
        hermes_home = _hermes_home_path_for_profile(info.profile)

    db_path = Path(hermes_home) / "state.db"
    if not db_path.is_file():
        return [
            {"sessionKey": sk, "title": None, "startedAt": None}
            for s in sessions
            for sk in ([s.get("session_key")] if s.get("session_key") else [])
        ]

    # 3. 从 state.db 读取 title
    _ensure_vendor_on_path()
    try:
        from hermes_state import SessionDB
    except ImportError as e:
        _log.warning("[agent] hermes_state 不可用: %s (agent=%s)", e, agent_id)
        return []

    db = None
    try:
        db = SessionDB(db_path=db_path)
        placeholders = ",".join("?" * len(session_keys))
        with db._lock:
            cursor = db._conn.execute(
                f"SELECT id, title, started_at FROM sessions WHERE id IN ({placeholders}) ORDER BY started_at DESC",
                session_keys,
            )
            rows = cursor.fetchall()
        title_map: dict[str, str | None] = {}
        started_map: dict[str, float | None] = {}
        for row in rows:
            sid_key = row["id"]
            title_map[sid_key] = row["title"]
            started_map[sid_key] = row["started_at"]

        return [
            {
                "sessionKey": sk,
                "title": title_map.get(sk),
                "startedAt": started_map.get(sk),
            }
            for sk in session_keys
        ]
    except sqlite3.OperationalError as e:
        err = str(e).lower()
        if "locked" in err or "busy" in err:
            _log.debug("[agent] state.db locked for agent=%s: %s", agent_id, e)
        else:
            _log.warning("[agent] state.db query failed for agent=%s: %s", agent_id, e)
        return []
    except Exception:
        _log.exception("[agent] read session titles failed for agent=%s", agent_id)
        return []
    finally:
        if db is not None:
            try:
                db.close()
            except Exception:
                pass


# ── public API ────────────────────────────────────────────────────────────────


def get_agent_memory(agent_id: str) -> dict:
    """聚合返回 Agent 的完整记忆数据：SOUL.md、state.db、Session 历史、长期记忆配置、技能列表。"""
    from backend.services.agent import _get_manager

    mgr = _get_manager()
    info = mgr.get_agent(agent_id)
    if info is None:
        raise FileNotFoundError(f"Agent '{agent_id}' 不存在")

    # 推导 hermes_home
    gw_home = getattr(info.gateway, "hermes_home", None)
    if gw_home:
        hermes_home = str(Path(gw_home).expanduser())
    else:
        from backend.services.profile_scanner import _hermes_home_path_for_profile
        hermes_home = _hermes_home_path_for_profile(info.profile)

    # 1. SOUL.md
    soul_path = Path(hermes_home) / "SOUL.md"
    soul_md = {"identity": "", "style": "", "defaults": "", "avoid": "", "coreTruths": ""}
    display_name = str(info.display_name or "").strip()
    if soul_path.is_file():
        try:
            from backend.services.soul_md import parse_soul_md as _parse_soul_md
            text = soul_path.read_text(encoding="utf-8")
            parsed = _parse_soul_md(text)
            soul_md["identity"] = parsed.get("identity", "")
            soul_md["style"] = parsed.get("style", "")
            soul_md["defaults"] = parsed.get("defaults", "")
            soul_md["avoid"] = parsed.get("avoid", "")
            soul_md["coreTruths"] = parsed.get("coreTruths", "")
            dn = str(parsed.get("displayName") or "").strip()
            if dn:
                display_name = dn
        except Exception:
            pass

    # 2. state.db 数据
    from backend.services import agent_db as _agent_db
    avatar = _agent_db.get_avatar(agent_id) or "badboy"
    gender = _agent_db.get_gender(agent_id)
    personality_data = _agent_db.get_personality(agent_id)
    model_data = _agent_db.get_agent_model(agent_id)
    office_pose = _agent_db.get_office_pose(agent_id)

    state_db = {
        "avatar": avatar,
        "gender": gender,
        "personality": personality_data.get("personality", ""),
        "catchphrases": personality_data.get("catchphrases", ""),
        "memes": personality_data.get("memes", ""),
        "officePose": office_pose,
        "model": model_data.get("model", ""),
        "modelProvider": model_data.get("model_provider", ""),
        "modelBaseUrl": model_data.get("model_base_url", ""),
    }

    # 3. Session 历史
    session_history = _agent_db.list_agent_sessions(agent_id)
    session_history_camel = [
        {
            "sessionId": s.get("session_id", ""),
            "sessionKey": s.get("session_key") or "",
            "createdAt": s.get("created_at", 0),
            "lastUsedAt": s.get("last_used_at", 0),
            "isActive": s.get("is_active", False),
            "parentSessionId": s.get("parent_session_id"),
        }
        for s in session_history
    ]

    # 4. 长期记忆配置 (config.yaml)
    memory_provider = {}
    cfg_path = Path(hermes_home) / "config.yaml"
    if cfg_path.is_file():
        try:
            import yaml
            cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
            memory_provider = cfg.get("memory", {})
            if not isinstance(memory_provider, dict):
                memory_provider = {}
        except Exception:
            pass

    # 5. 技能记忆 — 扫描 Agent hermes_home/skills/ 目录
    from backend.services.skill import _scan_skills_in_dir
    skills = _scan_skills_in_dir(Path(hermes_home))

    # 6. 会话标题 — 从 Hermes state.db 读取
    session_titles = _read_hermes_session_titles(agent_id, info)

    return {
        "agentId": agent_id,
        "profile": info.profile,
        "displayName": display_name,
        "avatar": avatar,
        "gender": gender,
        "soulMd": soul_md,
        "stateDb": state_db,
        "sessionHistory": session_history_camel,
        "sessionTitles": session_titles,
        "memoryProvider": memory_provider,
        "skills": skills,
    }


def summarize_session_memory(agent_id: str) -> dict:
    """读取 Agent 的所有 session title，交由 Agent 智能汇总并返回摘要。

    若 Agent 未运行，返回 ``{summarized: false, sessionTitles: [...]}``。
    若 Agent 正在运行，创建临时 session 提交汇总 prompt，等待
    ``message.complete`` 事件后返回 ``{summarized: true, summary: "...", ...}``。
    """
    from backend.services.agent import _get_manager

    mgr = _get_manager()
    info = mgr.get_agent(agent_id)
    if info is None:
        raise FileNotFoundError(f"Agent '{agent_id}' 不存在")

    # 1. 读取 session titles
    titles = _read_hermes_session_titles(agent_id, info)

    # 2. 检查 Agent 是否运行
    gw = info.gateway
    if not gw.is_alive():
        return {"summarized": False, "sessionTitles": titles}

    # 3. 构建汇总 prompt
    valid_titles = [(t.get("title") or "(无标题)") for t in titles]
    titles_text = "\n".join(f"{i + 1}. {t}" for i, t in enumerate(valid_titles))
    prompt = (
        "你是一个会话记忆汇总助手。以下是本 Agent 所有历史会话的标题列表，"
        "请用 2-4 句简洁的中文概述这些会话涵盖了哪些主题或讨论内容，"
        "注意观察是否有重复主题或值得关注的变化趋势。\n\n"
        "会话标题列表：\n"
        f"{titles_text}"
    )

    # 4. 创建临时 session
    temp_sid = gw.create_session()
    if not temp_sid:
        return {"summarized": False, "sessionTitles": titles, "error": "创建临时会话失败"}

    # 5. 提交 prompt 并等待 Agent 响应
    done = threading.Event()
    state: dict = {"summary": "", "err": ""}

    def handler(ev: dict) -> None:
        if str(ev.get("session_id") or "") != temp_sid:
            return
        et = str(ev.get("type") or "")
        pl = ev.get("payload") or {}
        if et == "message.complete":
            state["summary"] = str(pl.get("text") or "")
            done.set()
        elif et == "error":
            state["err"] = str(pl.get("message", pl))
            done.set()

    gw.on_event(handler)
    try:
        ok = gw.submit_prompt(temp_sid, prompt)
        if not ok:
            return {"summarized": False, "sessionTitles": titles, "error": "提交提示词失败"}

        if not done.wait(timeout=60.0):
            return {"summarized": False, "sessionTitles": titles, "error": "等待Agent响应超时"}

        if state["err"]:
            return {"summarized": False, "sessionTitles": titles, "error": state["err"]}

        return {"summarized": True, "summary": state["summary"], "sessionTitles": titles}
    finally:
        gw.remove_event(handler)
        try:
            gw.close_session(temp_sid)
        except Exception:
            pass


def get_recent_session_summaries(agent_id: str, n: int = 3) -> list[dict]:
    """获取 Agent 最近 N 个会话的摘要，用于跨会话上下文注入。

    优先从 ``smry_{agent_id}`` 缓存表读取；若无缓存则返回原始 session 标题。
    返回列表按时间倒序排列（最新的在前）。

    用法::

        summaries = get_recent_session_summaries("coder", n=3)
        for s in summaries:
            print(f"[{s['session_id'][:8]}] {s['summary'][:100]}")
    """
    import re as _re
    safe_id = _re.sub(r"\W", "_", agent_id).strip("_") or "unknown"

    # 尝试从 smry 缓存表读取
    try:
        import sqlite3 as _sqlite3
        from backend.db.connection import get_connection as _get_conn

        conn = _get_conn()
        try:
            table = f"smry_{safe_id}"
            cur = conn.execute(
                f"SELECT session_id, summary, generated_at FROM \"{table}\" "
                f"ORDER BY generated_at DESC LIMIT ?",
                (n,),
            )
            rows = cur.fetchall()
            if rows:
                result = []
                for r in rows:
                    result.append({
                        "session_id": str(r[0]),
                        "summary": str(r[1] or ""),
                        "generated_at": float(r[2]) if len(r) > 2 and r[2] else 0,
                    })
                conn.close()
                return result
        except Exception:
            # 表可能尚不存在
            pass
        finally:
            try:
                conn.close()
            except Exception:
                pass
    except Exception:
        pass

    # 退而求其次：从 state.db 获取 session 标题
    titles = _read_hermes_session_titles(agent_id, _get_agent_info(agent_id))
    result = []
    for t in titles[:n]:
        title = (t.get("title") or "").strip()
        key = (t.get("sessionKey") or "")[:8]
        result.append({
            "session_id": t.get("sessionKey", "?"),
            "summary": title or "(无标题)",
            "generated_at": t.get("startedAt") or 0,
        })
    return result


def _get_agent_info(agent_id: str):
    """内部辅助：获取 AgentInfo 对象。"""
    from backend.services.agent import _get_manager
    mgr = _get_manager()
    info = mgr.get_agent(agent_id)
    if info is None:
        raise FileNotFoundError(f"Agent '{agent_id}' 不存在")
    return info


# ── 双重记忆统计 ──────────────────────────────────────────────────────────────


def get_dual_memory_stats(agent_id: str) -> dict:
    """获取 Agent 双重记忆的汇总统计数据：向量记忆、知识图谱。

    Returns:
        {
            "vectorMemory": {"count": int, "status": "active"|"empty"|"unavailable"},
            "knowledgeGraph": {"nodeCount": int, "edgeCount": int},
            "sessions": {"sessionFileCount": int, "activeSessionCount": int},
        }
    """
    from backend.services.agent import _get_manager

    mgr = _get_manager()
    info = mgr.get_agent(agent_id)
    if info is None:
        raise FileNotFoundError(f"Agent '{agent_id}' 不存在")

    # 推导 hermes_home
    gw_home = getattr(info.gateway, "hermes_home", None)
    if gw_home:
        hermes_home = str(Path(gw_home).expanduser())
    else:
        from backend.services.profile_scanner import _hermes_home_path_for_profile
        hermes_home = _hermes_home_path_for_profile(info.profile)

    # ── 1. 向量记忆统计 ──────────────────────────────────────────────────
    vector_memory = {"count": 0, "status": "unavailable"}
    try:
        # 尝试从 memos 目录下的 textual_memory.json 读取记忆数量
        from backend.services.mem_os_service import _get_memos_dir

        memos_dir = Path(_get_memos_dir())
        safe_id = agent_id.replace("/", "_").replace(":", "_")

        # 常见路径: {memos_dir}/qdrant/{safe_id}/ 或 {memos_dir}/qdrant/{safe_id}/{safe_id}_memory/
        qdrant_path = memos_dir / "qdrant" / safe_id
        if qdrant_path.is_dir():
            # 检查 Qdrant 数据文件
            col_files = list(qdrant_path.rglob("*.col")) + list(qdrant_path.rglob("*.segment"))
            if col_files:
                vector_memory["count"] = len(col_files)
                vector_memory["status"] = "active"

        # 也尝试检查 textual_memory.json
        text_mem_patterns = [
            memos_dir / f"{safe_id}_cube" / "textual_memory.json",
            memos_dir / "textual_memory.json",
            qdrant_path / "textual_memory.json",
        ]
        for tm_path in text_mem_patterns:
            if tm_path.is_file():
                try:
                    import json
                    data = json.loads(tm_path.read_text(encoding="utf-8"))
                    if isinstance(data, list):
                        vector_memory["count"] = max(vector_memory["count"], len(data))
                    elif isinstance(data, dict):
                        vector_memory["count"] = max(vector_memory["count"], len(data.get("memories", data.get("entries", []))))
                    vector_memory["status"] = "active"
                except Exception:
                    pass
                break

        if vector_memory["status"] == "unavailable" and qdrant_path.is_dir():
            # 目录存在但无可计数文件
            vector_memory["status"] = "empty"
    except Exception as exc:
        _log.debug("[agent] dual_stats vector_memory failed for agent=%s: %s", agent_id, exc)
        vector_memory = {"count": 0, "status": "unavailable"}

    # ── 2. 知识图谱统计 ──────────────────────────────────────────────────
    knowledge_graph = {"nodeCount": 0, "edgeCount": 0}
    try:
        from backend.db.knowledge import KnowledgeEdgeDAO, KnowledgeNodeDAO

        nodes = KnowledgeNodeDAO.get_all_nodes(agent_id)
        edges = KnowledgeEdgeDAO.get_all_edges(agent_id)
        knowledge_graph = {
            "nodeCount": len(nodes),
            "edgeCount": len(edges),
        }
    except Exception as exc:
        _log.debug("[agent] dual_stats knowledge_graph failed for agent=%s: %s", agent_id, exc)

    # ── 3. Session 统计 ─────────────────────────────────────────────────
    sessions_info = {"sessionFileCount": 0, "activeSessionCount": 0}
    try:
        sessions_dir = Path(hermes_home) / "sessions"
        if sessions_dir.is_dir():
            files = list(sessions_dir.iterdir())
            sessions_info["sessionFileCount"] = len(files)

        from backend.services import agent_db as _agent_db
        all_sessions = _agent_db.list_agent_sessions(agent_id)
        sessions_info["activeSessionCount"] = sum(
            1 for s in all_sessions if s.get("is_active")
        )
    except Exception as exc:
        _log.debug("[agent] dual_stats sessions failed for agent=%s: %s", agent_id, exc)

    return {
        "vectorMemory": vector_memory,
        "knowledgeGraph": knowledge_graph,
        "sessions": sessions_info,
    }
