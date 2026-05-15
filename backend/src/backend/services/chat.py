"""Chat 业务逻辑层：会话管理、SSE 事件路由、Prompt 提交、审批/澄清响应。

对应 Spring Boot Service 层。
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import TYPE_CHECKING, Any, AsyncGenerator

if TYPE_CHECKING:
    pass

_log = logging.getLogger(__name__)

_ASCII_ONLY = re.compile(r"^[\x00-\x7f]+$")

# 用户或其它 Agent 投递的正文若呈现「任务 / 规划 / 步骤…」等编排语义，则向子进程额外注入结构化输出约定（经 &lt;memory-context&gt; 块合并进 prompt）。
_PLANNING_HINT_SUBSTRINGS = (
    "任务",
    "规划",
    "计划",
    "步骤",
    "拆解",
    "预案",
    "编排",
    "思路",
    "提纲",
    "分步",
    "怎么做",
    "如何实现",
)
_PLANNING_SEQUENTIAL_RE = re.compile(r"先.+再")
_PLANNING_PHRASE_RE = re.compile(
    r"(规划一下|帮我规划|列个计划|梳理一下|安排一下|分步骤|step\s*by\s*step)",
    re.I,
)

# 放在 ephemeral 最前（在 @ 路由说明之前），否则长路由段容易淹没 JSON 格式要求。
_STUDIO_PLAN_STRUCTURE_BLOCK = """
【Hermes Digital Studio｜本轮强制结构化输出】
判定：用户或其它 Agent 本条消息在要「规划 / 步骤 / 任务拆解 / 编排 / 怎么做」。你必须同时满足：
1) **回复正文第一个字符开始**：输出**唯一**一个 Markdown 围栏代码块，语言标记为 json；围栏内**只有**一个 JSON 对象（前后不要写中文解释）。
2) 围栏结束后**空一行**，再写面向用户的自然语言（分析、工具结果、文件路径等）。

JSON 形状（键名固定；`file_path` 可省略；`id` 为递增整数，从 1 开始）：
```json
{
  "name": "任务名称",
  "plan_summary": "一句总览",
  "steps": [
    {"id": 1, "title": "短标题", "action": "具体动作", "file_path": "可选"}
  ]
}
```

禁止省略 json 围栏；禁止把 JSON 放在第二段或附录；否则 Hermes Studio 左栏无法显示规划时间线。
""".strip()


def _message_suggests_structured_plan(text: str) -> bool:
    """检测用户消息是否暗示需要结构化规划（如任务、步骤、计划等关键词）。"""
    t = (text or "").strip()
    if not t:
        return False
    if any(k in t for k in _PLANNING_HINT_SUBSTRINGS):
        return True
    if _PLANNING_SEQUENTIAL_RE.search(t):
        return True
    if _PLANNING_PHRASE_RE.search(t):
        return True
    return False


def _build_studio_peer_routing_hint(mgr, current_agent_id: str) -> str:
    """供各 Agent 子进程注入系统层：需要用户转接同事时，应使用行首 ``@profile`` 格式。"""
    try:
        from backend.services import agent as agent_mod

        agents = agent_mod.list_agents()
    except Exception:
        return ""
    lines: list[str] = []
    for a in agents:
        aid = str(a.get("agentId") or "").strip()
        if not aid or aid == current_agent_id:
            continue
        prof = str(a.get("profile") or aid).strip()
        dn = str(a.get("displayName") or "").strip() or prof
        lines.append(f"- `@{prof}` — {dn}（profile=`{prof}`，与输入框行首 @ 一致）")
    if not lines:
        return ""
    self_handle = current_agent_id.strip() or "（未知）"
    return (
        "## Hermes Digital Studio — 与其他 Agent 通讯\n\n"
        f"**你本子进程的身份标识（`agentId` / profile）是 `{self_handle}`**；"
        "用户用 `@` 转发时匹配的是这个英文标识，**不是**模型供应商或 API 品牌名（例如配置里使用某厂商接口，"
        "也不代表你的 profile 变成 `default`）。`@default` 只指向 profile 目录名为 `default` 的那位同事。"
        f"用户若要转发到你，应使用 `@{self_handle}`（仅当 `{self_handle}` 为 `default` 时 `@default` 才是你）。"
        "**不要**把「模型品牌昵称」与 `@default` 说成同一人。\n\n"
        "本工作室内还有其他 Agent。当你需要把用户转交给某位同事、或请对方先处理/补充信息时，"
        "在**给用户的可直接复制发送的建议**里，该建议的**整段文本**必须以单独一行的 `@<profile> ` 开头"
        "（`profile` 为下表英文标识；`@` 与 handle **无空格**；`@profile` 后必须跟一个空格再写要传达的正文）。"
        "用户在本界面发送该格式即可把消息路由到对应 Agent 会话。\n"
        "亦支持 Bungalow 风格：`@profile | 正文` 或 `@profile 正文`；群发：`@所有人 | 同一说明`。\n"
        "**不要**用纯中文显示名作为 @ handle（须用下表中的 profile）。\n\n"
        "可用同事：\n" + "\n".join(lines)
    )


def _resolve_agent_id_for_token(mgr: Any, token: str) -> str | None:
    """将用户输入的 token 解析为 ``agent_id``（与前端一致）。

    必须使用 ``agent.list_agents()`` 的列表：其中 ``displayName`` 已与 SOUL.md 同步（如「崽崽」），
    不能只用 ``GatewayManager.list_agents()``，否则 @ 中文显示名永远无法命中。
    """
    from backend.services import agent as agent_mod

    t = (token or "").strip()
    if not t:
        return None
    lower = t.lower()
    for a in agent_mod.list_agents():
        aid = str(a.get("agentId") or "").strip()
        prof = str(a.get("profile") or "").strip()
        if not aid:
            continue
        if aid == t or (prof and prof == t):
            return aid
        if _ASCII_ONLY.match(aid) and aid.lower() == lower:
            return aid
        if prof and _ASCII_ONLY.match(prof) and prof.lower() == lower:
            return aid
        dn = str(a.get("displayName") or "").strip()
        if dn and dn == t:
            return aid
        if dn and _ASCII_ONLY.match(dn) and dn.lower() == lower:
            return aid
    return None


def _find_or_create_session_for_agent(mgr: Any, agent_id: str, cols: int) -> dict[str, Any]:
    sids = mgr.session_ids_for_agent(agent_id)
    if sids:
        disp = agent_id
        for a in mgr.list_agents():
            if a.get("agentId") == agent_id:
                disp = str(a.get("displayName") or "").strip() or agent_id
                break
        return {"sessionId": sids[0], "agentId": agent_id, "displayName": disp}
    return create_session(agent_id, cols)


def _submit_with_hint(session_id: str, text: str, attachments: list[str] | None) -> str:
    """对持有该会话的子进程设置路由提示（性格+同伴路由）并 ``prompt.submit``；返回 ``agent_id``。"""
    from backend.services.agent import _get_manager

    mgr = _get_manager()
    info = mgr.find_agent_by_session(session_id)
    if info is None:
        raise ValueError("会话不存在")

    # ── 读取性格设定 ─────────────────────────────────────────────────────────
    try:
        from backend.services import agent_db as _agent_db
        personality_data = _agent_db.get_personality(info.agent_id)
    except Exception:
        personality_data = {"personality": "", "catchphrases": "", "memes": ""}

    # 构造性格注入块（全部性格 + 随机一条口头禅/梗语）
    personality_parts: list[str] = []
    personality = (personality_data.get("personality") or "").strip()
    if personality:
        personality_parts.append(f"【性格】{personality}")

    catchphrase_lines = [l.strip() for l in (personality_data.get("catchphrases") or "").splitlines() if l.strip()]
    if catchphrase_lines:
        import random
        chosen = random.choice(catchphrase_lines)
        personality_parts.append(f"【口头禅】（优先使用）{chosen}")

    meme_lines = [l.strip() for l in (personality_data.get("memes") or "").splitlines() if l.strip()]
    if meme_lines:
        import random
        if random.random() < 0.6:  # 梗语 60% 概率注入
            chosen_meme = random.choice(meme_lines)
            personality_parts.append(f"【梗语】（可选使用）{chosen_meme}")

    personality_hint = ("\n".join(personality_parts) + "\n") if personality_parts else ""

    # ── 路由提示（同伴转接）────────────────────────────────────────────────
    routing = _build_studio_peer_routing_hint(mgr, info.agent_id)
    want_plan = _message_suggests_structured_plan(text)
    if want_plan:
        _log.info(
            "studio: structured plan hint for session=%s agent=%s preview=%r",
            session_id,
            info.agent_id,
            (text or "")[:200].replace("\n", "\\n"),
        )

    hint_parts: list[str] = []
    if personality_hint:
        hint_parts.append(personality_hint)
    if want_plan:
        hint_parts.append(_STUDIO_PLAN_STRUCTURE_BLOCK)
    if routing:
        hint_parts.append(routing)

    hint = "\n\n".join(hint_parts).strip()

    # 将人格/计划/路由 hint 通过 <memory-context> 注入用户 prompt
    # （vendor StreamingContextScrubber 会自动过滤此块，不进入用户可见输出）
    if hint:
        text = f"<memory-context>{hint}</memory-context>\n\n{text}"

    ok = mgr.submit_prompt(session_id, text, attachments=attachments)
    if not ok:
        raise RuntimeError("提交失败")
    return info.agent_id


def _submit_relay_payload(
    mgr: Any,
    target_aid: str,
    preferred_sid: str,
    payload: str,
    attachments: list[str] | None,
    cols: int,
) -> str:
    """向同事会话投递 handoff 正文；遇 ``session busy`` 则 interrupt 后重试，仍失败则新建会话再提交。返回实际写入的 ``session_id``。"""
    import time

    def _try(sid: str) -> bool:
        try:
            _submit_with_hint(sid, payload, attachments)
            return True
        except RuntimeError:
            return False

    if _try(preferred_sid):
        return preferred_sid

    try:
        mgr.interrupt(preferred_sid)
    except Exception as exc:
        _log.debug("relay interrupt %s: %s", preferred_sid, exc)
    time.sleep(0.25)
    if _try(preferred_sid):
        return preferred_sid

    info = mgr.get_agent(target_aid)
    if info is None:
        raise RuntimeError("转发失败：目标 Agent 不存在")
    new_sid, session_key = info.gateway.create_session_with_key(cols=cols)
    if not new_sid:
        raise RuntimeError("转发失败：无法为同事创建新会话")
    mgr.register_session(new_sid, target_aid, session_key=session_key)
    _log.warning(
        "relay fallback new session %s → agent %s (preferred %s busy/unavailable)",
        new_sid,
        target_aid,
        preferred_sid,
    )
    _submit_with_hint(new_sid, payload, attachments)
    return new_sid


# ── 会话管理 ────────────────────────────────────────────────────────────────

def create_session(agent_id: str | None, cols: int, parent_session_id: str | None = None) -> dict:
    """创建一个新的会话。

    若不指定 agentId，则自动绑定到列表中的第一个 Agent。
    若指定 parent_session_id，则表示该 session 是从另一个 session 压缩/续接而来的。

    返回 {"sessionId": str, "agentId": str}。
    """
    from backend.services.agent import _get_manager

    mgr = _get_manager()

    if agent_id:
        info = mgr.get_agent(agent_id)
        if info is None:
            raise ValueError("Agent 不存在")
    else:
        agents = mgr.list_agents()
        if not agents:
            raise ValueError("没有运行中的 Agent")
        info = mgr.get_agent(agents[0]["agentId"])
        if info is None:
            raise RuntimeError("Agent 查询失败")

    sid, session_key = info.gateway.create_session_with_key(cols=cols)
    if sid is None:
        raise RuntimeError("创建会话失败")
    mgr.register_session(sid, info.agent_id, parent_session_id, session_key)
    disp = info.display_name
    try:
        from backend.services import agent as agent_mod

        row = agent_mod.get_agent(info.agent_id)
        if (row.get("displayName") or "").strip():
            disp = str(row["displayName"]).strip()
    except Exception:
        pass
    return {"sessionId": sid, "agentId": info.agent_id, "displayName": disp}


def close_session(session_id: str) -> bool:
    """关闭指定会话。成功返回 True。"""
    from backend.services.agent import _get_manager
    return _get_manager().close_session(session_id)


def resume_session(session_id: str, cols: int = 120) -> dict:
    """恢复一个旧会话（复用 state.db 历史）。

    使用旧 session 的 session_key 创建新会话，保留历史消息。
    返回 {"sessionId": new_id, "agentId": agent_id} 或 {"error": "..."}.
    """
    from backend.services.agent import _get_manager
    from backend.services import agent_db as _agent_db

    mgr = _get_manager()

    # 从 DB 查找 agent_id
    all_sessions = _agent_db.list_all_sessions()
    agent_id = None
    for s in all_sessions:
        if s.get("sessionId") == session_id:
            agent_id = s.get("agentId")
            break

    if not agent_id:
        raise ValueError("未找到该会话的 Agent")

    result = mgr.resume_session(agent_id, session_id, cols=cols)
    if "error" in result:
        raise RuntimeError(result["error"])
    return result


def delete_session(session_id: str) -> dict:
    """彻底删除会话及其所有关联数据。

    依次删除：hermes state.db 记录 → sessions/ 磁盘文件 → backend agent_sessions 表。
    返回 {"deleted": True} 或 {"deleted": False, "error": "..."}.
    """
    from backend.services.agent import _get_manager
    from backend.services import agent_db as _agent_db

    mgr = _get_manager()

    # 从 DB 查找 agent_id
    all_sessions = _agent_db.list_all_sessions()
    agent_id = None
    for s in all_sessions:
        if s.get("sessionId") == session_id:
            agent_id = s.get("agentId")
            break

    if not agent_id:
        # 不在 DB 中，可能已被清理
        return {"deleted": True}

    return mgr.delete_session_by_db_record(agent_id, session_id)


def get_session_history(session_id: str) -> list[dict]:
    """获取指定会话的所有历史消息。

    优先从内存中查找 session，若内存中不存在（如后端重启后），
    则从 DB 中根据 session_id 或 session_key 恢复。
    """
    from backend.services.agent import _get_manager
    from backend.services import agent_db as _agent_db

    info = _get_manager().find_agent_by_session(session_id)
    if info is not None:
        return info.gateway.session_history(session_id) or []

    # 内存中未找到，尝试从 DB 恢复：先查 session_id，再查 session_key
    all_sessions = _agent_db.list_all_sessions()
    session_key = None
    agent_id = None
    for s in all_sessions:
        if s.get("sessionId") == session_id or s.get("sessionKey") == session_id:
            session_key = s.get("sessionKey")
            agent_id = s.get("agentId")
            break

    if session_key and agent_id:
        mgr = _get_manager()
        info = mgr.get_agent(agent_id)
        if info is not None:
            return info.gateway.session_history_by_key(session_key) or []

    raise ValueError("会话不存在")


def get_session_history_from_file(session_id: str) -> list[dict]:
    """直接从 Agent 的 sessions/*.jsonl 文件读取会话历史。

    不经过 Gateway JSON-RPC，直接读取磁盘 JSONL 文件。
    每条 JSONL 行是一个 message dict，包含 role、content、tool_name 等字段。
    返回的消息将 content 字段映射为 text 以保持与旧 API 格式一致。
    """
    import os
    from pathlib import Path

    from backend.services import agent_db as _agent_db
    from backend.services.agent import _get_manager

    # 1. 查找 session_key 和 agent_id
    all_sessions = _agent_db.list_all_sessions()
    session_key = None
    agent_id = None
    for s in all_sessions:
        if s.get("sessionId") == session_id:
            session_key = s.get("sessionKey")
            agent_id = s.get("agentId")
            break

    if not session_key:
        raise ValueError("会话不存在")

    # 2. 推导 hermes_home
    mgr = _get_manager()
    info = mgr.get_agent(agent_id) if agent_id else None
    if info is not None and hasattr(info, "gateway"):
        gw_home = getattr(info.gateway, "hermes_home", None)
        if gw_home:
            hermes_home = str(Path(gw_home).expanduser())
        else:
            from backend.services.profile_scanner import _hermes_home_path_for_profile
            hermes_home = _hermes_home_path_for_profile(info.profile)
    else:
        from backend.services.profile_scanner import _hermes_home_path_for_profile
        hermes_home = _hermes_home_path_for_profile(agent_id or "default")

    # 3. 读取 JSONL 文件
    jsonl_path = Path(hermes_home) / "sessions" / f"{session_key}.jsonl"
    if not jsonl_path.is_file():
        raise FileNotFoundError(f"JSONL file not found: {jsonl_path}")

    messages: list[dict] = []
    with open(jsonl_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                _log.warning("Skipping corrupt line in transcript %s", jsonl_path)
                continue
            # 统一字段名：content → text
            if isinstance(msg, dict):
                if "content" in msg and "text" not in msg:
                    msg["text"] = msg["content"]
                messages.append(msg)

    return messages


def _get_agent_hermes_home(agent_id: str) -> str:
    """推导 Agent 的 hermes_home 目录路径。"""
    from pathlib import Path

    from backend.services.agent import _get_manager
    from backend.services.profile_scanner import _hermes_home_path_for_profile

    mgr = _get_manager()
    info = mgr.get_agent(agent_id)
    if info is not None and hasattr(info, "gateway"):
        gw_home = getattr(info.gateway, "hermes_home", None)
        if gw_home:
            return str(Path(gw_home).expanduser())
        return _hermes_home_path_for_profile(info.profile)
    return _hermes_home_path_for_profile(agent_id or "default")


def list_session_files(agent_id: str) -> list[dict]:
    """列出 Agent sessions 目录下的会话文件（.jsonl 和 session_*.json）。

    返回文件信息列表，按修改时间倒序排列。
    """
    import os
    from pathlib import Path

    hermes_home = _get_agent_hermes_home(agent_id)
    sessions_dir = Path(hermes_home) / "sessions"

    if not sessions_dir.is_dir():
        return []

    files: list[dict] = []
    for entry in sorted(sessions_dir.iterdir(), key=lambda e: e.stat().st_mtime, reverse=True):
        if not entry.is_file():
            continue
        name = entry.name
        # 只匹配 .jsonl 文件 和 session_*.json 文件
        if not (name.endswith(".jsonl") or (name.startswith("session_") and name.endswith(".json"))):
            continue
        st = entry.stat()
        files.append({
            "name": name,
            "size": st.st_size,
            "mtime": st.st_mtime,
        })

    return files


def get_session_file_content(agent_id: str, file_name: str) -> list[dict]:
    """读取指定会话文件的内容（兼容 .jsonl 和 session_*.json 格式）。

    统一将 content 字段映射为 text。
    """
    import os
    from pathlib import Path

    # 安全检查：防止路径穿越
    safe_name = Path(file_name).name
    if safe_name != file_name or ".." in safe_name:
        raise ValueError("Invalid file name")

    hermes_home = _get_agent_hermes_home(agent_id)
    file_path = Path(hermes_home) / "sessions" / safe_name

    if not file_path.is_file():
        raise FileNotFoundError(f"Session file not found: {file_path}")

    with open(file_path, "r", encoding="utf-8") as f:
        raw = f.read().strip()

    messages: list[dict] = []

    if safe_name.endswith(".jsonl"):
        # JSONL 格式：逐行解析
        for line in raw.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                _log.warning("Skipping corrupt line in %s", file_path)
                continue
            if isinstance(msg, dict):
                if "content" in msg and "text" not in msg:
                    msg["text"] = msg["content"]
                messages.append(msg)
    else:
        # session_*.json 格式：顶层 JSON 包含 messages 数组
        try:
            doc = json.loads(raw)
        except json.JSONDecodeError:
            raise ValueError("Invalid JSON file")
        if isinstance(doc, dict) and isinstance(doc.get("messages"), list):
            for m in doc["messages"]:
                if isinstance(m, dict):
                    if "content" in m and "text" not in m:
                        m["text"] = m["content"]
                    messages.append(m)

    return messages


def get_full_session_chain_history(session_id: str, max_depth: int = 10) -> list[dict]:
    """获取 session 完整续接链的历史消息（从最老到最新）。

    用于压缩上下文后新 session 续接旧对话时，获取完整的对话历史。
    """
    from backend.services import agent_db as agent_db_mod
    from backend.services.agent import _get_manager

    chain = agent_db_mod.get_session_chain(session_id, max_depth)
    mgr = _get_manager()
    all_messages = []

    for sid in chain:
        info = mgr.find_agent_by_session(sid)
        if info is None:
            continue
        messages = info.gateway.session_history(sid) or []
        for msg in messages:
            msg["_session_id"] = sid
        all_messages.extend(messages)

    return all_messages


# ── Prompt 提交 ──────────────────────────────────────────────────────────────

def submit_prompt(session_id: str, text: str, attachments: list[str] | None = None, cols: int = 120) -> dict[str, Any]:
    """提交用户输入给 Agent 子进程；若文本为 @ /relay 转发格式则投递到目标会话。

    返回 ``sessionId``（及广播时的 ``sessionIds``）供前端对齐 SSE。attachments 为上传接口返回的路径列表。
    """
    from backend.services.agent import _get_manager
    from backend.services.handoff_parser import (
        is_broadcast_all_handoff_token,
        normalize_handoff_input,
        parse_user_handoff_prefix,
        relay_payload_from_handoff,
    )

    mgr = _get_manager()
    info = mgr.find_agent_by_session(session_id)
    if info is None:
        raise ValueError("会话不存在")

    text = normalize_handoff_input(text)
    handoff = parse_user_handoff_prefix(text)
    if not handoff:
        if "@" in text:
            _log.info(
                "handoff not parsed (relayed=false): session=%s owner=%s text_prefix=%r",
                session_id,
                info.agent_id,
                text[:240],
            )
        agent_id = _submit_with_hint(session_id, text, attachments)
        return {
            "ok": True,
            "status": "streaming",
            "sessionId": session_id,
            "agentId": agent_id,
            "relayed": False,
        }

    _log.info(
        "chat relay: from_session=%s source_agent=%s token=%r",
        session_id,
        info.agent_id,
        handoff.get("token"),
    )

    token = str(handoff.get("token") or "").strip()
    message = str(handoff.get("message") or "").strip()
    leading = str(handoff.get("leading") or "")
    payload = relay_payload_from_handoff(leading, message)
    source_agent = info.agent_id

    if is_broadcast_all_handoff_token(token):
        from backend.services import agent as agent_mod

        targets: list[str] = []
        for a in agent_mod.list_agents():
            aid = str(a.get("agentId") or "").strip()
            if not aid or aid == source_agent:
                continue
            targets.append(aid)
        if not targets:
            raise ValueError("广播转交需要至少一名其他 Agent")
        session_ids: list[str] = []
        relay_targets: list[dict[str, Any]] = []
        first_aid = ""
        for aid in targets:
            sinfo = _find_or_create_session_for_agent(mgr, aid, cols)
            sid_use = str(sinfo["sessionId"])
            final_sid = _submit_relay_payload(mgr, aid, sid_use, payload, attachments, cols)
            session_ids.append(final_sid)
            relay_targets.append(
                {
                    "sessionId": final_sid,
                    "agentId": aid,
                    "displayName": str(sinfo.get("displayName") or ""),
                }
            )
            if not first_aid:
                first_aid = aid
        disp = ""
        for a in agent_mod.list_agents():
            if a.get("agentId") == first_aid:
                disp = str(a.get("displayName") or "").strip()
                break
        return {
            "ok": True,
            "status": "streaming",
            "sessionId": session_ids[0],
            "sessionIds": session_ids,
            "relayTargets": relay_targets,
            "agentId": first_aid,
            "displayName": disp,
            "relayed": True,
            "broadcast": True,
        }

    target_aid = _resolve_agent_id_for_token(mgr, token)
    if not target_aid:
        raise ValueError(f"未找到 handle 对应的 Agent: {token}")

    if target_aid == source_agent:
        agent_id = _submit_with_hint(session_id, payload, attachments)
        return {
            "ok": True,
            "status": "streaming",
            "sessionId": session_id,
            "agentId": agent_id,
            "relayed": False,
        }

    sinfo = _find_or_create_session_for_agent(mgr, target_aid, cols)
    target_sid = str(sinfo["sessionId"])
    final_sid = _submit_relay_payload(mgr, target_aid, target_sid, payload, attachments, cols)
    return {
        "ok": True,
        "status": "streaming",
        "sessionId": final_sid,
        "agentId": target_aid,
        "displayName": str(sinfo.get("displayName") or ""),
        "relayed": True,
        "broadcast": False,
    }


def interrupt_session(session_id: str) -> bool:
    """中断指定会话正在进行的模型推理。"""
    from backend.services.agent import _get_manager
    from backend.services.plan_chain import cancel_plan_chain

    cancel_plan_chain(session_id)
    return _get_manager().interrupt(session_id)


def start_plan_chain(
    session_id: str,
    plan_anchor_ts: int,
    plan_summary: str,
    steps: list[dict[str, Any]],
    *,
    step_timeout: float = 900.0,
    name: str = "",
    raw_text: str | None = None,
    agent_id: str = "",
) -> tuple[bool, str, int | None]:
    """启动服务端规划链（后台线程）。

    先将规划（含步骤）写入 plan_artifacts + plan_artifact_steps，再启动执行线程。
    返回 (ok, message, artifact_id)。
    """
    from backend.services import agent as _agent_svc
    from backend.services.plan_chain import start_plan_chain_background

    # 写库：主表 + 步骤子表
    artifact_id = _agent_svc.save_plan_artifact(
        session_id=session_id,
        agent_id=agent_id,
        name=name,
        plan_summary=plan_summary,
        steps=steps,
        raw_text=raw_text,
    )
    if artifact_id is None:
        return False, "保存规划失败", None

    ok, msg = start_plan_chain_background(
        session_id,
        plan_anchor_ts,
        plan_summary,
        steps,
        step_timeout=step_timeout,
        artifact_id=artifact_id,
        name=name,
    )
    return ok, msg, artifact_id if ok else None


# ── 审批 / 澄清 ────────────────────────────────────────────────────────────

def respond_approval(session_id: str, choice: str, all: bool) -> bool:
    """响应 Agent 发起的工具调用审批请求。

    choice 说明:
    - "once":    仅本次允许
    - "session": 本会话内后续自动允许
    - "deny":    拒绝此次调用
    """
    from backend.services.agent import _get_manager
    return _get_manager().respond_approval(session_id, choice, all)


def respond_clarify(session_id: str, request_id: str, answer: str) -> bool:
    """响应 Agent 发起的澄清请求（多选一交互）。"""
    from backend.services.agent import _get_manager
    return _get_manager().respond_clarify(session_id, request_id, answer)


# ── SSE 事件流生成器 ─────────────────────────────────────────────────────────

def sse_generate(session_id: str) -> AsyncGenerator[str, None]:
    """SSE 事件流生成器 — 将 Agent 子进程的 JSON-RPC 事件实时推送至前端。

    每个 SSE 连接维护一个 asyncio.Queue，事件回调将子进程事件放入队列。
    """
    from backend.services.agent import _get_manager

    async def _generate() -> AsyncGenerator[str, None]:
        manager = _get_manager()
        info = manager.find_agent_by_session(session_id)
        if info is None:
            err_data = json.dumps({"error": "session not found"})
            yield "data: " + err_data + "\n\n"
            return

        event_queue: asyncio.Queue[dict | None] = asyncio.Queue()
        loop = asyncio.get_running_loop()

        def on_event(event: dict) -> None:
            asyncio.run_coroutine_threadsafe(event_queue.put(event), loop)

        info.gateway.on_event(on_event)

        try:
            while True:
                try:
                    obj = await asyncio.wait_for(event_queue.get(), timeout=55.0)
                    if obj is None:
                        break
                    data_line = "data: " + json.dumps(obj, ensure_ascii=False) + "\n\n"
                    yield data_line
                except asyncio.TimeoutError:
                    # 55s 保持连接心跳
                    yield ": keepalive\n\n"
        except GeneratorExit:
            pass
        finally:
            event_queue.put_nowait(None)

    return _generate()


def get_last_active_session() -> dict:
    """返回所有 agent 中最晚活跃的 session。若不在内存中则自动恢复。

    Returns:
        {"session": dict | None, "restored": bool}
    """
    from backend.services import agent_db as _agent_db
    from backend.services.agent import _get_manager

    sessions = _agent_db.list_all_sessions()  # 按 last_used_at DESC, 返回 camelCase keys
    for s in sessions:
        agent_id = s.get("agentId")
        session_id = s.get("sessionId")
        if not agent_id or not session_id:
            continue

        mgr = _get_manager()
        if mgr.find_agent_by_session(session_id):
            return {"session": s, "restored": False}

        # 不在内存中 → 尝试自动恢复
        try:
            resume_session(session_id)
            return {"session": s, "restored": True}
        except Exception:
            continue

    return {"session": None, "restored": False}
