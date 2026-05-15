"""自我反思引擎 — Agent 在会话结束后回顾对话，提炼教训更新自我模型。

核心流程：
1. 构建反思 prompt（包含当前 self model + session 摘要）
2. 通过 Agent 子进程提交 prompt 并等待响应
3. 解析 LLM 返回的 JSON 格式反思结果
4. 更新 self_model.json（preferences、capabilities、behavioral_patterns 等）
5. 追加到 reflection_history

触发方式：
- 手动：通过 API ``POST /agents/{agent_id}/self-model/reflect``
- 自动：context compression 后（session.switch 事件）
- 自动：定时轮询（GatewayManager 后台线程）
"""

from __future__ import annotations

import json
import logging
import threading
import time
from pathlib import Path
from typing import Any

_log = logging.getLogger(__name__)

# ── 频率控制 ──────────────────────────────────────────────────────────────────

# agent_id → 上次反思时间戳
_LAST_REFLECTION: dict[str, float] = {}
_reflection_lock = threading.Lock()

REFLECTION_COOLDOWN_SECONDS = 86400       # 24 小时冷却
MIN_MESSAGES_BEFORE_REFLECT = 30          # 至少 30 条消息才触发
AUTO_ADAPT_STYLE = False                  # 是否自动将风格相关反思写入 SOUL.md Style 节

# 单个 Agent 同时只能有一个反思线程
_reflection_running: dict[str, bool] = {}
_run_lock = threading.Lock()


def check_reflection_eligibility(agent_id: str, session_id: str) -> bool:
    """检查是否满足反思条件。

    Returns:
        True 如果满足所有条件（冷却、消息量、不忙碌）
    """
    # 1. 冷却时间检查
    last_time = _LAST_REFLECTION.get(agent_id, 0)
    if time.time() - last_time < REFLECTION_COOLDOWN_SECONDS:
        _log.debug("self_reflection: agent=%s cooldown not expired", agent_id)
        return False

    # 2. 消息量检查
    try:
        msg_count = _get_session_message_count(session_id)
        if msg_count < MIN_MESSAGES_BEFORE_REFLECT:
            _log.debug(
                "self_reflection: agent=%s session=%s msg_count=%d < %d",
                agent_id, session_id, msg_count, MIN_MESSAGES_BEFORE_REFLECT,
            )
            return False
    except Exception as e:
        _log.debug("self_reflection: msg count check failed: %s", e)
        return False

    # 3. 忙碌状态检查
    with _run_lock:
        if _reflection_running.get(agent_id, False):
            _log.debug("self_reflection: agent=%s already reflecting", agent_id)
            return False

    return True


def trigger_reflection(agent_id: str, session_id: str) -> bool:
    """触发异步反思，在后台线程执行，不阻塞调用者。

    Returns:
        True 如果反思已启动，False 如果不满足条件。
    """
    if not check_reflection_eligibility(agent_id, session_id):
        return False

    with _run_lock:
        _reflection_running[agent_id] = True

    thread = threading.Thread(
        target=_run_reflection_sync,
        args=(agent_id, session_id),
        daemon=True,
        name=f"reflection-{agent_id[:8]}",
    )
    thread.start()
    return True


def _run_reflection_sync(agent_id: str, session_id: str) -> None:
    """在后台线程中执行反思（同步流程）。"""
    try:
        _log.info("self_reflection: start agent=%s session=%s", agent_id, session_id)

        # 1. 获取当前自我模型
        from backend.services.self_model import get_self_model_for_agent, append_reflection_entry, update_self_model_field
        model = get_self_model_for_agent(agent_id)

        # 2. 获取 session 摘要
        session_summary = _build_session_summary(agent_id, session_id)

        # 3. 构建反思 prompt
        prompt = _build_reflection_prompt(agent_id, model, session_summary)

        # 4. 提交到 Agent 等待响应
        result = _submit_reflection(agent_id, prompt)
        if not result:
            _log.info("self_reflection: agent=%s no new insights", agent_id)
            return

        # 5. 解析 JSON 响应
        parsed = _parse_reflection_result(result)
        if not parsed:
            _log.info("self_reflection: agent=%s no parsable result", agent_id)
            return

        # 6. 更新 self_model（含可选 SOUL.md 适配）
        _apply_reflection(agent_id, parsed, update_self_model_field, append_reflection_entry, auto_adapt_style=AUTO_ADAPT_STYLE)

        # 7. 更新冷却时间
        _LAST_REFLECTION[agent_id] = time.time()

        _log.info(
            "self_reflection: completed agent=%s confidence=%s",
            agent_id, parsed.get("confidence", "unknown"),
        )

    except Exception as e:
        _log.warning("self_reflection: agent=%s failed: %s", agent_id, e, exc_info=True)
    finally:
        with _run_lock:
            _reflection_running[agent_id] = False


def _build_session_summary(agent_id: str, session_id: str) -> str:
    """构建 session 摘要，供反思 prompt 使用。"""
    from backend.services.agent import _get_manager

    mgr = _get_manager()
    info = mgr.find_agent_by_session(session_id)
    if info is None:
        return "（session 不可用）"

    try:
        history = info.gateway.session_history(session_id) or []
    except Exception:
        return "（无法获取历史）"

    # 提取最近 N 条消息的摘要
    recent = history[-20:]  # 最近 20 条
    lines = []
    for msg in recent:
        role = msg.get("role", "?")
        text = (msg.get("text") or msg.get("content") or "")[:200]
        lines.append(f"[{role}] {text}")

    return "\n".join(lines)


def _build_reflection_prompt(agent_id: str, model: dict, session_summary: str) -> str:
    """构建反思 prompt。"""
    prompt_path = Path(__file__).parent.parent / "prompts" / "reflection_prompt.md"
    if prompt_path.is_file():
        template = prompt_path.read_text(encoding="utf-8")
    else:
        _log.warning("reflection_prompt.md not found at %s, using inline template", prompt_path)
        template = _INLINE_REFLECTION_TEMPLATE

    # 构建当前自模型摘要
    model_lines = []
    if model.get("preferences"):
        model_lines.append(f"偏好：{model['preferences'][:200]}")
    if model.get("behavioral_patterns"):
        model_lines.append(f"行为模式：{model['behavioral_patterns'][:200]}")
    num_reflections = len(model.get("reflection_history", []))
    if num_reflections > 0:
        latest = model["reflection_history"][-1]
        model_lines.append(f"已有 {num_reflections} 次反思，最近：{latest.get('lesson', '')[:100]}")

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

    return template.format(
        agent_name=agent_name,
        current_self_model_summary="\n".join(model_lines) if model_lines else "（暂无）",
        session_summary=session_summary,
    )


# 内联模板（当 reflection_prompt.md 不存在时的兜底）
_INLINE_REFLECTION_TEMPLATE = """你是 Agent {agent_name}。请基于近期对话内容进行自我反思。

## 当前自我认知
{current_self_model_summary}

## 近期对话摘要
{session_summary}

## 反思要求
请分析近期对话，找出以下信息。仅以 JSON 格式返回：

{{"preferences_updates": [], "capabilities_learned": [], "behavior_updates": [], "traits_derived": [], "lesson_learned": "", "confidence": "medium"}}

注意事项：
- 只反映从对话中确实观察到的模式，不要臆测
- 如果没发现新内容，返回空数组"""


def _submit_reflection(agent_id: str, prompt: str) -> str | None:
    """向 Agent 提交反思 prompt 并等待回复。

    Returns:
        Agent 回复文本，如果失败返回 None。
    """
    from backend.services.agent import _get_manager
    from backend.services.chat import create_session
    from backend.services.agent_chat_bridge import await_submit_and_complete

    mgr = _get_manager()

    try:
        # 创建临时 session
        session_info = create_session(agent_id, 120)
        sid = session_info.get("sessionId")
        if not sid:
            return None

        gw = mgr.find_agent_by_session(sid)
        if gw is None:
            return None

        # 提交反思 prompt
        def _do_submit():
            mgr.submit_prompt(sid, prompt, attachments=None)

        result = await_submit_and_complete(
            gw.gateway if hasattr(gw, "gateway") else mgr,
            sid,
            timeout=120.0,
            submit_fn=_do_submit,
        )

        # 关闭临时 session
        try:
            mgr.close_session(sid)
        except Exception:
            pass

        if result.get("ok"):
            return result.get("reply", "").strip()
        return None

    except Exception as e:
        _log.warning("self_reflection: submit to agent=%s failed: %s", agent_id, e)
        return None


def _parse_reflection_result(text: str) -> dict[str, Any] | None:
    """从 LLM 回复中解析 JSON 格式的反思结果。

    尝试：
    1. 提取 JSON 代码块内的内容
    2. 直接解析整段文本为 JSON
    """
    if not text:
        return None

    # 尝试提取 JSON 代码块
    import re

    json_match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
    if json_match:
        candidate = json_match.group(1).strip()
    else:
        candidate = text.strip()

    try:
        parsed = json.loads(candidate)
        if not isinstance(parsed, dict):
            return None
        return parsed
    except json.JSONDecodeError:
        # 尝试找第一个 { 和最后一个 }
        start = candidate.find("{")
        end = candidate.rfind("}")
        if start >= 0 and end > start:
            try:
                parsed = json.loads(candidate[start:end + 1])
                if isinstance(parsed, dict):
                    return parsed
            except json.JSONDecodeError:
                pass
        return None


def _apply_reflection(
    agent_id: str,
    parsed: dict[str, Any],
    update_fn,
    append_fn,
    auto_adapt_style: bool = False,
) -> None:
    """将反思结果应用到 self_model，并可选地自动适配 SOUL.md。

    Args:
        auto_adapt_style: 是否自动将高置信度的风格偏好写入 SOUL.md Style 节。
            默认为 False，需用户手动开启。
    """
    # 1. 更新偏好
    prefs = parsed.get("preferences_updates", [])
    if isinstance(prefs, list) and prefs:
        for pref in prefs:
            if isinstance(pref, str) and pref.strip():
                update_fn(agent_id, "preferences", f"- {pref.strip()}")

    # 2. 更新能力自知
    caps = parsed.get("capabilities_learned", [])
    if isinstance(caps, list) and caps:
        for cap in caps:
            if isinstance(cap, str) and cap.strip():
                update_fn(agent_id, "capabilities", f"- {cap.strip()}")

    # 3. 更新行为模式
    behaviors = parsed.get("behavior_updates", [])
    if isinstance(behaviors, list) and behaviors:
        for b in behaviors:
            if isinstance(b, str) and b.strip():
                update_fn(agent_id, "behavioral_patterns", f"- {b.strip()}")

    # 4. 更新衍生特质
    traits = parsed.get("traits_derived", [])
    if isinstance(traits, list) and traits:
        for t in traits:
            if isinstance(t, str) and t.strip():
                update_fn(agent_id, "derived_traits", f"- {t.strip()}")

    # 5. 追加教训到反思历史
    lesson = parsed.get("lesson_learned", "")
    confidence = parsed.get("confidence", "medium")
    if isinstance(lesson, str) and lesson.strip():
        append_fn(agent_id, lesson.strip(), confidence)

    # 6. 可选：高置信度风格相关内容自动写入 SOUL.md Style 节
    if auto_adapt_style and confidence == "high":
        _adapt_soul_md_style(agent_id, prefs, behaviors)


_STYLE_KEYWORDS: set[str] = {
    "风格", "语气", "语调", "口吻",
    "语言", "回复", "表述",
    "格式", "排版", "结构",
    "正式", "非正式", "口头", "书面",
    "简短", "简洁", "详细", "详尽", "精炼",
    "礼貌", "直接", "委婉", "热情", "冷静",
    "幽默", "严肃", "专业",
    "style", "tone", "language",
    "concise", "detailed", "formal", "casual",
    "polite", "direct", "professional",
}


def _adapt_soul_md_style(
    agent_id: str,
    prefs: list[Any],
    behaviors: list[Any],
) -> None:
    """将高置信度的风格偏好自动写入 SOUL.md Style 节。

    仅当发现的内容与风格/语气/表述方式相关时才写入。
    """
    style_lines: list[str] = []
    for item in list(prefs) + list(behaviors):
        if isinstance(item, str) and item.strip():
            text = item.strip()
            if any(kw in text for kw in _STYLE_KEYWORDS):
                style_lines.append(f"- {text}（自我反思发现）")

    if not style_lines:
        return

    try:
        from backend.services.self_model import _resolve_hermes_home
        from backend.services.soul_md import update_soul_md_field

        hermes_home = _resolve_hermes_home(agent_id)
        if not hermes_home:
            return

        for line in style_lines:
            update_soul_md_field(hermes_home, "Style", line)
    except Exception as e:
        _log.warning("_adapt_soul_md_style(%s) failed: %s", agent_id, e)


def _get_session_message_count(session_id: str) -> int:
    """获取 session 的消息数量（通过 gateway 查询）。"""
    from backend.services.agent import _get_manager

    mgr = _get_manager()
    info = mgr.find_agent_by_session(session_id)
    if info is None:
        return 0

    try:
        history = info.gateway.session_history(session_id) or []
        return len(history)
    except Exception:
        return 0
