"""记忆上下文构建模块 — 运行时内存注入管道的核心。

通过 ``<memory-context>...</memory-context>`` 标签机制（vendor 内置的
``MemoryManager.build_memory_context_block()`` + ``StreamingContextScrubber``）
将 Studio 层的记忆数据注入到 Agent 推理中，不修改 vendor 代码。

在 ``submit_with_hint()`` 中调用本模块函数，构建上下文块前置到用户消息前。

Phase 1 职责：
- ``build_session_startup_context()`` — 新 session 首次提交时注入跨会话摘要（Gap 2）
- ``build_routing_context()`` — 替代无效的 ``studio.set_routing_hint`` RPC（Gap 0）
"""

from __future__ import annotations

import logging
import os
import re
import time
import threading
from pathlib import Path
from typing import Any

_log = logging.getLogger(__name__)

# ── 表名安全化 ────────────────────────────────────────────────────────────────

_SAFE_ID_RE = re.compile(r"\W")


def _safe_agent_id(agent_id: str) -> str:
    """将 agent_id 转换为 DB 表名安全形式。

    非单词字符替换为 ``_``，如 ``agent-coder`` → ``agent_coder``。
    """
    return _SAFE_ID_RE.sub("_", agent_id).strip("_") or "unknown"


# ── Session 首次提交判断 ──────────────────────────────────────────────────────

_first_turn_tracker: dict[str, bool] = {}
_tracker_lock = threading.Lock()


def is_first_turn_for_session(session_id: str) -> bool:
    """判断给定的 session_id 是否为首次提交 prompt。

    首次调用返回 True，后续调用返回 False。
    """
    with _tracker_lock:
        if session_id not in _first_turn_tracker:
            _first_turn_tracker[session_id] = False
            return True
        return False


def reset_session_tracker(session_id: str) -> None:
    """重置 session 的首次提交标记，用于 session 恢复/重启场景。"""
    with _tracker_lock:
        _first_turn_tracker.pop(session_id, None)


def _cleanup_stale_trackers() -> None:
    """清理超过 24 小时的跟踪记录，防止内存泄漏。"""
    now = time.time()
    stale_keys = []
    # 简单策略：保留最近 1000 项
    with _tracker_lock:
        if len(_first_turn_tracker) > 1000:
            keys = list(_first_turn_tracker.keys())
            for k in keys[: len(keys) // 2]:
                _first_turn_tracker.pop(k, None)


# ── 核心构建函数 ──────────────────────────────────────────────────────────────


def build_session_startup_context(
    agent_id: str,
    session_id: str,
    is_first_turn: bool = False,
) -> str:
    """构建新 session 首次提交时的跨会话记忆上下文。

    仅在 ``is_first_turn`` 为 True 时生成有意义的内容。

    注入内容：
    1. 最近 N=3 个会话的摘要（从 DB + state.db 获取）
    2. Session chain 上下文（如果当前 session 有 parent）
    3. MEMORY.md 当前记录条数提示

    返回格式：
    ``## 最近会话摘要\\n...`` 的文本块（不包含 ``<memory-context>`` 标签，
    由调用方统一包裹）。
    """
    if not is_first_turn:
        return ""

    parts: list[str] = []

    # 1. 最近会话摘要
    try:
        summaries = _get_recent_summaries(agent_id, n=3)
        if summaries:
            parts.append("## 最近会话摘要\n" + "\n".join(summaries))
    except Exception as e:
        _log.debug("memory_context: get_recent_summaries failed for agent=%s: %s",
                   agent_id, e)

    # 2. Session chain 上下文（压缩续接）
    try:
        chain_ctx = _get_session_chain_context(agent_id, session_id)
        if chain_ctx:
            parts.append("## 会话追溯\n" + chain_ctx)
    except Exception as e:
        _log.debug("memory_context: get_session_chain_context failed: %s", e)

    # 3. MEMORY.md 条目数提示（不注入全部内容，交由 vendor frozen snapshot）
    try:
        mem_hint = _get_memory_file_hint(agent_id)
        if mem_hint:
            parts.append("## 当前已记录的记忆\n" + mem_hint)
    except Exception as e:
        _log.debug("memory_context: get_memory_file_hint failed: %s", e)

    # 新增：首次注入时附带自模型摘要（Step 2 / L3）
    if is_first_turn:
        try:
            self_summary = _build_self_model_summary(agent_id)
            if self_summary:
                parts.append("## 自我认知摘要\n" + self_summary)
        except Exception as e:
            _log.debug("memory_context: self_model_summary failed: %s", e)

    # 新增：Agent 启动引导上下文（由 backend agent_bootstrap 在启动时准备）
    if is_first_turn:
        try:
            bootstrap_ctx = _read_bootstrap_cache(agent_id)
            if bootstrap_ctx:
                parts.append("## 启动恢复上下文\n" + bootstrap_ctx)
                _log.info(
                    "memory_context: injected bootstrap context for agent=%s", agent_id
                )
        except Exception as e:
            _log.debug("memory_context: bootstrap context read failed: %s", e)

    return "\n\n".join(parts) if parts else ""


def _read_soul_personality_fallback(agent_id: str) -> str:
    """当 agent_personality 表无数据时，从 SOUL.md 回退读取人格设定。

    解析 ``## Identity`` 和 ``## Style`` 段落作为人格提示，
    返回格式与 DB 读取的 personality_hint 一致。
    """
    from backend.services.agent import _get_manager

    mgr = _get_manager()
    info = mgr.get_agent(agent_id)
    if info is None:
        return ""

    gw_home = getattr(info.gateway, "hermes_home", None)
    if gw_home:
        hermes_home = str(Path(gw_home).expanduser())
    else:
        from backend.services.profile_scanner import _hermes_home_path_for_profile
        hermes_home = _hermes_home_path_for_profile(info.profile)

    soul_path = Path(hermes_home) / "SOUL.md"
    if not soul_path.is_file():
        return ""

    try:
        content = soul_path.read_text(encoding="utf-8")
    except Exception:
        return ""

    identity = _extract_md_section(content, "Identity")
    style = _extract_md_section(content, "Style")

    parts: list[str] = []
    if identity:
        parts.append(f"【性格】{identity}")
    if style:
        parts.append(f"【风格】{style}")

    return ("\n".join(parts) + "\n") if parts else ""


def _extract_md_section(content: str, section_name: str) -> str:
    """从 Markdown 内容中提取指定 ## 段落的内容。

    从 ``## SectionName`` 行开始，到下一个 ``##`` 或 ``#`` 行结束。
    返回段落内容（不含标题行），未找到返回空字符串。
    """
    pattern = rf"^##\s+{re.escape(section_name)}\s*$(.+?)(?=^##\s|\Z)"
    match = re.search(pattern, content, re.MULTILINE | re.DOTALL)
    if not match:
        return ""
    return match.group(1).strip()


def build_routing_context(
    agent_id: str,
    personality_hint: str = "",
    plan_hint: str = "",
    peer_routing: str = "",
    emotion_hint: str = "",
) -> str:
    """构建路由/规划/人格提示的上下文块。

    替代当前无效的 ``studio.set_routing_hint`` JSON-RPC 调用。
    将这些提示作为 ``<memory-context>`` 注入到用户消息前，
    Agent 在 message history 中看到，参与推理。

    当 ``personality_hint`` 为空时，自动从 SOUL.md 回退读取
    ``## Identity`` 和 ``## Style`` 段落作为人格提示。

    ``emotion_hint`` 包含当前情绪状态，注入在上下文最前面。

    返回格式：用 ``##`` 标题分段的纯文本（不包含 outer 标签）。
    若所有参数为空，返回空字符串。
    """
    parts: list[str] = []

    # 情绪提示：放在最前面，Agent 最先感知
    if emotion_hint:
        parts.append(f"## 当前情绪状态\n{emotion_hint}")

    # 人格提示：若 DB 中无数据，回退到 SOUL.md 解析
    effective_personality = personality_hint
    if not effective_personality:
        effective_personality = _read_soul_personality_fallback(agent_id)

    if effective_personality:
        parts.append(f"## 角色与风格提示\n{effective_personality}")

    if plan_hint:
        parts.append(f"## 输出格式要求\n{plan_hint}")

    if peer_routing:
        parts.append(f"## 工作室协作指引\n{peer_routing}")

    return "\n\n".join(parts) if parts else ""


def build_memory_context_block(content: str) -> str:
    """将内容包裹为 ``<memory-context>`` 标签块。

    Vendor 的 ``StreamingContextScrubber`` 会在输出流中自动过滤此块，
    用户看不到注入的记忆上下文。
    """
    if not content.strip():
        return ""
    return (
        "<memory-context>\n"
        f"{content.strip()}\n"
        "</memory-context>"
    )


def build_self_model_context(agent_id: str) -> str:
    """构建自我模型上下文块，Agent 在每轮推理中看到自己的"自我模型"。

    从 self_model.json 读取偏好、行为模式和衍生特质注入到 `<memory-context>`。
    如果 self_model 不存在或为空，返回空字符串。

    返回格式：``## 自我认知：偏好\\n...`` 的文本块（不包含 outer 标签）。
    """
    try:
        from backend.services.self_model import get_self_model_for_agent
        model = get_self_model_for_agent(agent_id)
    except Exception as e:
        _log.debug("self_model: get_self_model_for_agent failed: %s", e)
        return ""

    parts: list[str] = []
    preferences = (model.get("preferences") or "").strip()
    capabilities = (model.get("capabilities") or "").strip()
    behavioral = (model.get("behavioral_patterns") or "").strip()
    traits = (model.get("derived_traits") or "").strip()

    if not any([preferences, capabilities, behavioral, traits]):
        return ""

    if preferences:
        parts.append(f"## 自我认知：偏好（从对话中学习）\n{preferences}")
    if capabilities:
        parts.append(f"## 自我认知：能力自知\n{capabilities}")
    if behavioral:
        parts.append(f"## 自我认知：行为模式（从对话中总结）\n{behavioral}")
    if traits:
        parts.append(f"## 自我认知：衍生特质\n{traits}")

    return "\n\n".join(parts) if parts else ""


def _build_self_model_summary(agent_id: str) -> str:
    """构建首次注入时的自模型摘要（简版，用于 session startup context）。"""
    try:
        from backend.services.self_model import get_self_model_for_agent
        model = get_self_model_for_agent(agent_id)
    except Exception:
        return ""

    num_reflections = len(model.get("reflection_history", []))
    parts: list[str] = []
    prefs = (model.get("preferences") or "").strip()
    if prefs:
        parts.append(f"偏好：{prefs[:200]}")

    history_count = ""
    if num_reflections > 0:
        latest = model["reflection_history"][-1]
        history_count = f"已有 {num_reflections} 次自我反思，最近一次：{latest.get('lesson', '')[:100]}"

    if not parts and not history_count:
        return ""

    result = "\n".join(parts)
    if history_count:
        result += f"\n{history_count}"
    return result


# ── 内部辅助函数 ──────────────────────────────────────────────────────────────


def _get_recent_summaries(agent_id: str, n: int = 3) -> list[str]:
    """获取 Agent 最近 N 个会话的摘要。

    优先从 ``smry_{agent_id}`` 表读取缓存的摘要；
    若无缓存，则从 ``agent_sessions`` + Hermes state.db 获取 session 标题。
    """
    safe_id = _safe_agent_id(agent_id)
    lines: list[str] = []

    # 优先从 smry 缓存表读取
    try:
        from backend.db.connection import get_connection
        conn = get_connection()
        try:
            table = f"smry_{safe_id}"
            cur = conn.execute(
                f"SELECT session_id, summary FROM \"{table}\" ORDER BY generated_at DESC LIMIT ?",
                (n,),
            )
            rows = cur.fetchall()
            if rows:
                for r in rows:
                    sid = r[0]
                    summary = r[1] or ""
                    short_sid = sid[:8] if sid else "?"
                    if summary:
                        lines.append(f"- [{short_sid}] {summary[:300]}")
                if lines:
                    return lines
        except Exception:
            # 表可能尚不存在，回退到标题方式
            pass
        finally:
            conn.close()
    except Exception:
        pass

    # 退而求其次：从 Hermes state.db 读取 session 标题
    try:
        titles = _read_hermes_session_titles_fast(agent_id, n)
        for t in titles:
            title = (t.get("title") or "").strip()
            key = (t.get("sessionKey") or "")[:8]
            if title:
                lines.append(f"- [{key}] {title[:300]}")
            elif key:
                lines.append(f"- [{key}] (无标题)")
    except Exception as e:
        _log.debug("memory_context: fast title read failed: %s", e)

    return lines[:n]


def _read_hermes_session_titles_fast(agent_id: str, n: int = 3) -> list[dict]:
    """快速从 Hermes state.db 读取最近 n 个 session 的标题。"""
    import sqlite3 as _sqlite3
    from backend.services.agent import _get_manager

    mgr = _get_manager()
    info = mgr.get_agent(agent_id)
    if info is None:
        return []

    gw_home = getattr(info.gateway, "hermes_home", None)
    if gw_home:
        hermes_home = str(Path(gw_home).expanduser())
    else:
        from backend.services.profile_scanner import _hermes_home_path_for_profile
        hermes_home = _hermes_home_path_for_profile(info.profile)

    db_path = Path(hermes_home) / "state.db"
    if not db_path.is_file():
        return []

    result: list[dict] = []
    try:
        db = _sqlite3.connect(str(db_path))
        db.row_factory = _sqlite3.Row
        cur = db.execute(
            "SELECT id, title FROM sessions ORDER BY started_at DESC LIMIT ?",
            (n,),
        )
        for row in cur.fetchall():
            result.append({
                "sessionKey": str(row["id"]),
                "title": row["title"],
            })
        db.close()
    except Exception:
        pass
    return result


def _get_session_chain_context(agent_id: str, session_id: str) -> str:
    """获取当前 session 的续接链上下文。

    如果当前 session 有 parent_session_id，说明是从压缩续接而来，
    生成包含 parent_session_id 的追溯指引，方便 Agent 按需查询原始记录。
    """
    from backend.services import agent_db as _agent_db
    from backend.db.agent import AgentSessionDAO

    parent_id = AgentSessionDAO.get_parent_session(session_id)
    if not parent_id:
        return ""

    # 获取 parent session 的压缩映射信息
    safe_id = _safe_agent_id(agent_id)
    cmap_info = _get_compression_map_entry(safe_id, session_id, parent_id)
    if cmap_info:
        return (
            f"本会话续接自会话 {parent_id}（压缩于 {cmap_info.get('compressed_at', '?')}）\n"
            f"关键话题：{cmap_info.get('key_topics', '（未记录）')}\n"
            f"压缩摘要：{cmap_info.get('summary', '（未记录）')[:200]}\n"
            f"\n"
            f"如需回顾原始讨论细节，可使用 session_search tool 查询原始会话。\n"
            f"原始会话 ID: {parent_id}"
        )

    # 仅有 parent_id 但无压缩映射记录时的简化版
    return (
        f"本会话续接自会话 {parent_id}\n"
        f"如需回顾上一段讨论细节，可使用 session_search tool 查询原始会话。\n"
        f"原始会话 ID: {parent_id}"
    )


def _get_compression_map_entry(safe_id: str, session_id: str, parent_id: str) -> dict | None:
    """从 cmap_{agent_id} 表获取压缩映射条目。"""
    try:
        from backend.db.connection import get_connection
        conn = get_connection()
        try:
            table = f"cmap_{safe_id}"
            cur = conn.execute(
                f"SELECT summary, key_topics, compressed_at FROM \"{table}\" "
                f"WHERE compressed_session_id = ? AND original_session_id = ?",
                (session_id, parent_id),
            )
            row = cur.fetchone()
            if row:
                return {
                    "summary": row[0] or "",
                    "key_topics": row[1] or "",
                    "compressed_at": row[2] if len(row) > 2 else None,
                }
        except Exception:
            pass
        finally:
            conn.close()
    except Exception:
        pass
    return None


def _get_memory_file_hint(agent_id: str) -> str:
    """获取 MEMORY.md 的简要提示（不注入全部内容）。"""
    from backend.services.agent import _get_manager

    mgr = _get_manager()
    info = mgr.get_agent(agent_id)
    if info is None:
        return ""

    gw_home = getattr(info.gateway, "hermes_home", None)
    if gw_home:
        hermes_home = str(Path(gw_home).expanduser())
    else:
        from backend.services.profile_scanner import _hermes_home_path_for_profile
        hermes_home = _hermes_home_path_for_profile(info.profile)

    mem_path = Path(hermes_home) / "MEMORY.md"
    if not mem_path.is_file():
        return "（暂无已记录的长期记忆）"

    try:
        content = mem_path.read_text(encoding="utf-8")
        lines = [l.strip() for l in content.splitlines() if l.strip().startswith("[")]
        count = len(lines)
        if count == 0:
            return "（暂无已记录的长期记忆）"
        size = len(content)
        return f"已记录 {count} 条记忆条目，总大小约 {size} 字符。"
    except Exception:
        return ""


# ── Phase 2 预置：mtime 检测 ──────────────────────────────────────────────────

# session 级别的 MEMORY.md / USER.md mtime 追踪
# key: session_id → {"memory_mtime": float, "user_mtime": float}
_session_mtimes: dict[str, dict[str, float]] = {}
_mtime_lock = threading.Lock()


def record_session_mtimes(session_id: str, mem_mtime: float, user_mtime: float = 0.0) -> None:
    """记录 session 启动时的文件修改时间。"""
    with _mtime_lock:
        _session_mtimes[session_id] = {
            "memory_mtime": mem_mtime,
            "user_mtime": user_mtime,
        }


def build_memory_delta_context(agent_id: str, session_id: str) -> str:
    """检测 MEMORY.md 是否有变化，如有则生成增量记忆上下文（Phase 2）。

    返回格式：``## 记忆更新\\n...`` 或空字符串。
    """
    from backend.services.agent import _get_manager

    mgr = _get_manager()
    info = mgr.get_agent(agent_id)
    if info is None:
        return ""

    gw_home = getattr(info.gateway, "hermes_home", None)
    if gw_home:
        hermes_home = str(Path(gw_home).expanduser())
    else:
        from backend.services.profile_scanner import _hermes_home_path_for_profile
        hermes_home = _hermes_home_path_for_profile(info.profile)

    mem_path = Path(hermes_home) / "MEMORY.md"
    if not mem_path.is_file():
        return ""

    current_mtime = mem_path.stat().st_mtime

    with _mtime_lock:
        tracked = _session_mtimes.get(session_id, {})
        old_mtime = tracked.get("memory_mtime", current_mtime)
        # 更新为最新 mtime
        _session_mtimes[session_id] = {
            "memory_mtime": current_mtime,
            "user_mtime": tracked.get("user_mtime", current_mtime),
        }

    if current_mtime <= old_mtime:
        return ""  # 无变化

    # 有变化，读取全部条目
    try:
        content = mem_path.read_text(encoding="utf-8")
        lines = [l.strip() for l in content.splitlines()
                 if l.strip().startswith("[")]
        if not lines:
            return ""

        return (
            "## 记忆更新\n"
            "以下是最新的长期记忆条目（MEMORY.md 在上轮对话后已更新）：\n\n"
            + "\n".join(f"- {l}" for l in lines[:20])
        )
    except Exception:
        return ""


def cleanup_session_mtime(session_id: str) -> None:
    """清理 session 的 mtime 追踪记录。"""
    with _mtime_lock:
        _session_mtimes.pop(session_id, None)


# ── Phase 3+4：实体提取 + 向量回溯 + 知识图谱查询 ────────────────────────────


# 实体提取正则（英文技术术语 + PascalCase 词）
# 采用英文优先策略；中文实体查询通过知识图谱 kgnode 表实现（Phase 4）
_ENTITY_RE_CAMEL = re.compile(r"\b[A-Z][a-zA-Z0-9]+\b")       # PascalCase/CamelCase
_ENTITY_RE_TECH = re.compile(r"\b[a-z]+[a-z0-9_\-\.]+[a-z0-9]+\b")  # 小写技术词
_ENTITY_SPLIT_RE = re.compile(r"[^\u4e00-\u9fa5]+")  # 中文分词分隔符

# 英文停用词（常见非技术词）
_ENTITY_EN_STOP = frozenset({
    "the", "this", "that", "what", "how", "and", "you", "are", "can",
    "for", "not", "but", "all", "will", "have", "with", "from", "your",
    "just", "like", "when", "make", "more", "some", "them",
    "has", "been", "its", "into", "than", "get", "use", "about",
    "which", "also", "new", "out", "one", "very", "well", "back",
    "then", "now", "here", "there", "only", "over", "each", "may",
    "should", "could", "would", "other", "after", "first",
    "class", "def", "import", "return", "print", "true", "false",
    "null", "function", "const", "let", "var", "if", "else",
    "hello", "thanks", "thank", "start", "stop", "none",
})

# 中文停用词（非实体的常见词）
_ENTITY_CN_STOP = frozenset({
    "可以", "什么", "一下", "如果", "我们", "这个", "那个", "就是", "一个",
    "然后", "已经", "还有", "这些", "那些", "看看", "能够", "或者",
    "帮我", "需要", "怎么", "现在", "知道", "应该", "所以", "只是",
    "使用", "进行", "没有", "不是", "他们", "因为", "但是", "不过",
    "可能", "的话", "时候", "之后", "这里", "那里", "比较",
    "之前", "还是", "并且", "以及", "其中", "最后", "首先",
    "关于", "很多", "非常", "不会", "自己", "不用", "一直",
    "真的", "觉得", "这种", "那种", "这么", "那么",
    "说了", "东西", "事情", "问题", "方法", "方式", "情况",
    "一点", "其实", "还是", "项目", "状态",
})


def extract_entities(text: str, max_entities: int = 10) -> list[str]:
    """从用户消息中提取关键技术实体（英文为主，中文辅助）。

    英文：匹配 PascalCase/CamelCase 词 + 小写技术术语（\b 边界禁止部分匹配）
    中文：按非中文字符分段后提取 2-3 字候选（聚合频率过滤）
    """
    if not text:
        return []

    matches: list[tuple[int, str]] = []

    # 1. PascalCase/CamelCase 技术词 (React, Vue, Zustand, PostgreSQL, MongoDB)
    for m in _ENTITY_RE_CAMEL.finditer(text):
        matches.append((m.start(), m.group()))

    # 2. 小写技术词 (fastapi, docker, eslint, zustand)
    for m in _ENTITY_RE_TECH.finditer(text):
        matches.append((m.start(), m.group()))

    # 3. 中文实体：按标点分段，统计 2-3 字片段出现频率
    cn_candidates: dict[str, int] = {}
    cn_segments = _ENTITY_SPLIT_RE.split(text)
    for seg in cn_segments:
        if len(seg) < 2:
            continue
        for i in range(len(seg)):
            for window in (2, 3):
                end = i + window
                if end <= len(seg):
                    chunk = seg[i:end]
                    cn_candidates[chunk] = cn_candidates.get(chunk, 0) + 1

    # 取频率最高的中文候选（至少出现 2 次或在停用词外）
    cn_sorted = sorted(cn_candidates.items(), key=lambda x: -x[1])
    for chunk, freq in cn_sorted:
        if chunk not in _ENTITY_CN_STOP:
            idx = text.find(chunk)
            if idx >= 0:
                matches.append((idx, chunk))
            if len([m for m in matches if any('\u4e00' <= c <= '\u9fa5' for c in m[1])]) >= max_entities // 2:
                break

    # 按首次出现位置排序，去重
    matches.sort(key=lambda x: x[0])
    seen: set[str] = set()
    result = []
    for _, m in matches:
        lower = m.lower()
        if lower in _ENTITY_EN_STOP:
            continue
        if m in _ENTITY_CN_STOP:
            continue
        if m not in seen:
            seen.add(m)
            result.append(m)
            if len(result) >= max_entities:
                break
    return result


def build_turn_memory_context(
    agent_id: str,
    session_id: str,
    user_text: str,
    *,
    enable_vector_lookup: bool = False,
    enable_knowledge_graph: bool = False,
) -> str:
    """构建 per-turn 记忆上下文（Phase 3+4 集成）。

    执行两步检索：
    1. 实体提取（正则 + 分词）
    2. 知识图谱邻居查询（对命中的实体查找关联知识）
    3. 可选：向量库回溯（使用用户消息全文进行语义搜索）

    Args:
        agent_id: Agent ID
        session_id: 当前会话 ID
        user_text: 用户输入文本
        enable_vector_lookup: 是否启用向量库查找（需要向量库适配器）
        enable_knowledge_graph: 是否启用知识图谱查询

    Returns:
        ``<memory-context>`` 内的格式化文本块，无结果时返回空字符串。
    """
    parts: list[str] = []

    # Step 1: 实体提取（用于知识图谱查询 + 向量搜索关键词）
    entities = extract_entities(user_text)

    # Step 2: 知识图谱查询（Phase 4 / 需求 D）
    if enable_knowledge_graph and entities:
        try:
            from backend.services.knowledge_graph import query_knowledge_graph
            kg_context = query_knowledge_graph(agent_id, entities)
            if kg_context:
                parts.append(f"## 关联知识\n{kg_context}")
        except Exception as e:
            _log.debug("memory_context: KG query failed: %s", e)

    # Step 3: 向量库回溯（Phase 3 / 需求 C）
    # 即使实体提取为空，也用用户消息全文做语义搜索
    if enable_vector_lookup:
        try:
            if entities:
                unseen = _filter_unseen_entities(agent_id, session_id, entities)
                vector_results = _lookup_vector_memories(agent_id, unseen, user_text)
            else:
                # 无实体时直接用用户全文语义搜索
                vector_results = _lookup_vector_memories(agent_id, [], user_text)
            if vector_results:
                parts.append(f"## 历史相关记忆\n{vector_results}")
        except Exception as e:
            _log.debug("memory_context: vector lookup failed: %s", e)

    return "\n\n".join(parts) if parts else ""


def _filter_unseen_entities(
    agent_id: str,
    session_id: str,
    entities: list[str],
) -> list[str]:
    """筛选在当前 session 消息历史中未出现的实体。

    当前为简化实现：仅通过正则匹配当前用户消息中是否已包含实体。
    完整实现需要查询 session 的 message history（vendor state.db messages 表），
    待 Phase 3 完整实现时通过查询 Hermes state.db 的 messages_fts 表判定。
    """
    # 简化版：所有支持向量库的实体都做查询（不做 session 内过滤）
    # 完整版需要 access to session message history
    return entities


def _lookup_vector_memories(agent_id: str, entities: list[str], user_text: str = "") -> str:
    """查询 MemOS 向量库获取与指定实体相关的历史记忆。

    使用 MemOS (MemoryOS 2.0.15) 的 Qdrant 本地向量库进行语义搜索。
    每个 Agent 拥有独立的 MemOS 实例和 Qdrant 存储路径。

    优先使用 entities 做搜索词；若 entities 为空则回退到 user_text。

    返回格式：
    ``- {matched_memory}``
    """
    query = " ".join(entities) if entities else (user_text.strip() or "")
    if not query:
        return ""

    try:
        from backend.services.mem_os_service import mos_search as _mos_search

        results = _mos_search(agent_id, query, top_k=3, mode="fast")
        if not results:
            return ""

        lines = []
        for i, mem in enumerate(results[:3], 1):
            # 截断过长的记忆文本，保持上下文紧凑
            short = mem[:250] if len(mem) > 250 else mem
            lines.append(f"- {short}")
        return "\n".join(lines)
    except Exception as e:
        _log.debug("memory_context: MemOS vector lookup failed: %s", e)
        return ""


# ── 启动引导缓存读取 ──────────────────────────────────────────────────────────


_BOOTSTRAP_CACHE_DIR = None


def _get_bootstrap_cache_dir() -> Path | None:
    """获取 bootstrap 缓存目录（优先使用子进程环境变量）。"""
    global _BOOTSTRAP_CACHE_DIR
    if _BOOTSTRAP_CACHE_DIR is not None:
        return _BOOTSTRAP_CACHE_DIR

    # 子进程中优先使用 studio.yaml / 环境变量指定的目录
    try:
        from backend.core.config import get_config
        memos_dir = get_config().memos_dir
        if memos_dir:
            _BOOTSTRAP_CACHE_DIR = Path(memos_dir) / "agent_bootstrap"
            return _BOOTSTRAP_CACHE_DIR
    except Exception:
        pass

    env_dir = os.environ.get("HERMES_STUDIO_MEMOS_DIR", "").strip()
    if env_dir:
        _BOOTSTRAP_CACHE_DIR = Path(env_dir) / "agent_bootstrap"
        return _BOOTSTRAP_CACHE_DIR

    # 回退到 pyproject.toml 定位
    try:
        cwd = Path.cwd().resolve()
        for parent in [cwd] + list(cwd.parents):
            if (parent / "pyproject.toml").is_file():
                _BOOTSTRAP_CACHE_DIR = parent / ".memos" / "agent_bootstrap"
                return _BOOTSTRAP_CACHE_DIR
    except Exception:
        pass

    return None


def _read_bootstrap_cache(agent_id: str) -> str:
    """读取 Agent 启动引导缓存文件。

    读取成功后重命名为 .done 避免重复注入。
    返回缓存的 context 内容，失败返回空字符串。
    """
    import os as _os

    cache_dir = _get_bootstrap_cache_dir()
    if cache_dir is None:
        return ""

    cache_file = cache_dir / f"{agent_id}.json"
    if not cache_file.is_file():
        return ""

    try:
        import json
        data = json.loads(cache_file.read_text(encoding="utf-8"))
        context = data.get("context", "")
        if context:
            # 读取后重命名，避免下次启动重复注入
            try:
                os.replace(cache_file, cache_file.with_suffix(".json.done"))
            except OSError:
                pass
        return context
    except Exception as e:
        _log.debug("memory_context: bootstrap cache read failed: %s", e)
        return ""


# ── 模块导出 ──────────────────────────────────────────────────────────────────

__all__ = [
    "build_session_startup_context",
    "build_routing_context",
    "build_memory_context_block",
    "build_self_model_context",
    "build_memory_delta_context",
    "build_turn_memory_context",
    "extract_entities",
    "is_first_turn_for_session",
    "reset_session_tracker",
    "record_session_mtimes",
    "cleanup_session_mtime",
]
