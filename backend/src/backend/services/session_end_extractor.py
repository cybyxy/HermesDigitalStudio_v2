"""Session-end 自动记忆提取引擎。

核心流程：
1. session 关闭时由 GatewayManager.close_session() 触发
2. 后台线程读取会话最后 N 条消息摘要
3. 通过 Agent 子进程提交提取 prompt，要求 Agent 使用 ``memory`` tool
   写入 2-5 条关键事实到 MEMORY.md
4. 缓存会话摘要到 ``smry_{agent_id}`` 表供后续快速读取

触发方式：
- 自动：session 关闭时（close_session 钩子）
"""

from __future__ import annotations

import json
import logging
import re
import threading
import time

_log = logging.getLogger(__name__)

# 频率控制：同一 Agent 同时只能有一个提取线程
_extraction_running: dict[str, bool] = {}
_extraction_lock = threading.Lock()

# 最小消息数量才会触发提取
_MIN_MESSAGES_FOR_EXTRACT = 6

# 单次提取超时（秒）
_EXTRACTION_TIMEOUT = 90.0

# 提取结果中的 JSON 解析正则
_JSON_RE = re.compile(r"```(?:json)?\s*\n?(.*?)\n?```", re.DOTALL)


def trigger_session_end_extraction(
    agent_id: str,
    session_id: str,
    gateway=None,
    mgr=None,
) -> bool:
    """触发异步 session-end 记忆提取（后台线程，不阻塞关闭流程）。

    Args:
        agent_id: Agent 标识
        session_id: 被关闭的会话 ID
        gateway: SubprocessGateway 实例（可选，worker 里通过 mgr 查找）
        mgr: GatewayManager 实例（可选）

    Returns:
        True 如果提取已启动，False 如果不满足条件。
    """
    with _extraction_lock:
        if _extraction_running.get(agent_id, False):
            _log.debug("session_end_extractor: agent=%s already extracting", agent_id)
            return False
        _extraction_running[agent_id] = True

    t = threading.Thread(
        target=_extraction_worker,
        args=(agent_id, session_id, gateway, mgr),
        daemon=True,
        name=f"session-end-extract-{session_id[:8]}",
    )
    t.start()
    return True


def _extraction_worker(
    agent_id: str,
    session_id: str,
    gateway=None,
    mgr=None,
) -> None:
    """后台线程：读取会话摘要 → 构建提取 prompt → 提交 Agent → 缓存结果。"""
    try:
        # 等待一小段让 session 完全关闭
        time.sleep(2.0)

        _log.info("session_end_extractor: start agent=%s session=%s", agent_id, session_id)

        # 1. 获取会话摘要
        session_summary = _build_session_digest(agent_id, session_id, gateway, mgr)
        if not session_summary:
            _log.info("session_end_extractor: agent=%s session=%s no messages to extract", agent_id, session_id)
            return

        # 2. 构建提取 prompt
        prompt = _build_extraction_prompt(agent_id, session_summary)

        # 3. 提交到 Agent 等待响应
        result = _submit_extraction(agent_id, prompt, mgr)
        if not result:
            _log.info("session_end_extractor: agent=%s session=%s no extraction reply", agent_id, session_id)
            return

        # 4. 解析并缓存摘要
        summary = _parse_and_cache(agent_id, session_id, result)

        _log.info(
            "session_end_extractor: completed agent=%s session=%s summary_len=%d",
            agent_id, session_id, len(summary) if summary else 0,
        )

    except Exception as e:
        _log.warning("session_end_extractor: agent=%s failed: %s", agent_id, e, exc_info=True)
    finally:
        with _extraction_lock:
            _extraction_running[agent_id] = False


def _build_session_digest(
    agent_id: str,
    session_id: str,
    gateway=None,
    mgr=None,
) -> str | None:
    """从会话历史中构建对话摘要，供提取 prompt 使用。

    Returns:
        对话摘要文本，如果无法获取或消息太少返回 None。
    """
    # 优先使用传入的 gateway，否则通过 mgr 查找
    if gateway is not None:
        gw = gateway
    else:
        try:
            from backend.services.agent import _get_manager
            mgr = mgr or _get_manager()
            info = mgr.find_agent_by_session(session_id)
            if info is None:
                return None
            gw = info.gateway
        except Exception:
            return None

    try:
        history = gw.session_history(session_id) or []
    except Exception:
        _log.debug("session_end_extractor: cannot read session history for %s", session_id)
        return None

    if len(history) < _MIN_MESSAGES_FOR_EXTRACT:
        return None

    # 提取最后 N 条消息，过滤助手回复
    recent = history[-30:]
    lines: list[str] = []
    user_messages: list[str] = []
    assistant_messages: list[str] = []

    for msg in recent:
        role = msg.get("role", "unknown")
        text = (msg.get("text") or msg.get("content") or "").strip()
        if not text:
            continue
        if role in ("user", "human"):
            user_messages.append(text[:300])
        elif role == "assistant":
            # 只取助手回复的前 200 字作为摘要
            assistant_messages.append(text[:200])
        else:
            continue

    if not user_messages:
        return None

    for i, um in enumerate(user_messages):
        lines.append(f"[用户·{i + 1}] {um}")
    for i, am in enumerate(assistant_messages[:8]):  # 最多 8 条助手回复
        lines.append(f"[助手·{i + 1}] {am}")

    return "\n\n".join(lines)


_EXTRACTION_TEMPLATE = """你是 Agent {agent_name}。在刚才的会话中，你和用户进行了交流。

## 对话摘要

{session_summary}

## 提取要求

请回顾以上对话，从中提取 **2-5 条值得长期记住的事实**。每条记忆请使用 `memory` tool 写入（add 方法），需指定 category:

- `pref`: 用户偏好（如 "用户喜欢简洁的UI"）
- `proj`: 项目信息（如 "项目 HermesV2 使用 FastAPI"）
- `decision`: 重要决策（如 "决定使用 PostgreSQL 替代 SQLite"）
- `lesson`: 经验教训（如 "部署时忘记设置 CORS 导致前端报错"）
- `fact`: 用户提及的事实（如 "用户生日是5月1日"）
- `plan`: 计划/待办事项（如 "下周要完成 API 文档"）

每条记忆内容应简洁明确，包含完整的上下文信息。

完成后，请用以下 JSON 格式总结你提取了什么：

```json
{{
  "extracted_count": 3,
  "categories_used": ["pref", "fact", "decision"],
  "brief": "提取了用户的UI偏好、生日信息和数据库选型决定"
}}
```

如果对话没有值得长期记住的内容，返回：
```json
{{"extracted_count": 0, "brief": "本次对话无值得长期记忆的内容"}}
```"""


def _build_extraction_prompt(agent_id: str, session_summary: str) -> str:
    """构建 session-end 记忆提取 prompt。"""
    # 获取 agent 名称
    agent_name = agent_id
    try:
        from backend.services.agent import _get_manager
        mgr = _get_manager()
        info = mgr.get_agent(agent_id)
        if info:
            agent_name = info.display_name or agent_id
    except Exception:
        pass

    return _EXTRACTION_TEMPLATE.format(
        agent_name=agent_name,
        session_summary=session_summary,
    )


def _submit_extraction(agent_id: str, prompt: str, mgr=None) -> str | None:
    """向 Agent 提交提取 prompt 并等待回复。

    Returns:
        Agent 回复文本，如果失败返回 None。
    """
    try:
        from backend.services.agent import _get_manager
        from backend.services.chat import create_session
        from backend.services.agent_chat_bridge import await_submit_and_complete

        mgr = mgr or _get_manager()

        # 创建临时 session
        session_info = create_session(agent_id, 120)
        sid = session_info.get("sessionId")
        if not sid:
            _log.warning("session_end_extractor: create_session failed for agent=%s", agent_id)
            return None

        gw = mgr.find_agent_by_session(sid)
        if gw is None:
            _log.warning("session_end_extractor: agent=%s not found after create_session", agent_id)
            return None

        def _do_submit():
            mgr.submit_prompt(sid, prompt, attachments=None)

        result = await_submit_and_complete(
            gw.gateway if hasattr(gw, "gateway") else mgr,
            sid,
            timeout=_EXTRACTION_TIMEOUT,
            submit_fn=_do_submit,
        )

        # 关闭临时 session
        try:
            mgr.close_session(sid)
        except Exception:
            pass

        if result.get("ok"):
            reply = result.get("reply", "").strip()
            if reply:
                return reply
        return None

    except Exception as e:
        _log.warning("session_end_extractor: submit to agent=%s failed: %s", agent_id, e)
        return None


def _parse_and_cache(agent_id: str, session_id: str, text: str) -> str:
    """从 Agent 回复中解析提取结果并缓存会话摘要。

    Returns:
        解析出的摘要文本（brief 字段），失败返回空字符串。
    """
    brief = ""

    # 尝试解析 JSON
    json_match = _JSON_RE.search(text)
    if json_match:
        candidate = json_match.group(1).strip()
    else:
        # 尝试从文本中找第一个 { 和最后一个 }
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            candidate = text[start:end + 1]
        else:
            candidate = text.strip()

    try:
        parsed = json.loads(candidate)
        if isinstance(parsed, dict):
            brief = parsed.get("brief", "") or ""
            count = parsed.get("extracted_count", 0)
            _log.info(
                "session_end_extractor: parsed agent=%s count=%d brief=%s",
                agent_id, count, brief[:100],
            )
    except json.JSONDecodeError:
        # 无法解析 JSON，用文本的前 300 字作为摘要
        brief = text[:300].strip()
        _log.debug("session_end_extractor: JSON parse failed, using raw text summary")

    # 缓存摘要到 smry_{agent_id} 表
    if brief:
        try:
            from backend.db.memory import SessionSummaryDAO
            SessionSummaryDAO.save_summary(
                agent_id=agent_id,
                session_id=session_id,
                summary=brief,
                token_count=len(text) // 3,
                model=(
                    "session_end_extract"
                    + (" (parsed)" if not _JSON_RE.search(text) else " (json)")
                ),
            )
        except Exception as e:
            _log.debug("session_end_extractor: summary cache failed: %s", e)

    return brief
