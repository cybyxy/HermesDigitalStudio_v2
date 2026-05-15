"""Agent-Chat 桥接模块 — 编排器与会话管理之间的共享接口。

提取原来散落在 ``chat.py`` / ``orchestrate.py`` 中需要跨模块引用的核心函数，
消除 ``orchestrate.py`` → ``chat._private_function()`` 的紧耦合，
同时提供 ``plan_chain.py`` 所需的 await 原语。

使用::

    from backend.services.agent_chat_bridge import (
        submit_with_hint,
        await_submit_and_complete,
        resolve_agent_id_for_token,
    )
"""

from __future__ import annotations

import logging
import re
import time
import threading
from typing import Any

_log = logging.getLogger(__name__)

_ASCII_ONLY = re.compile(r"^[\x00-\x7f]+$")

# ── 规划检测关键词（从 chat.py 提取）─────────────────────────────────────────

_PLANNING_HINT_SUBSTRINGS = (
    "任务", "规划", "计划", "步骤", "拆解",
    "预案", "编排", "思路", "提纲", "分步",
    "怎么做", "如何实现",
)
_PLANNING_SEQUENTIAL_RE = re.compile(r"先.+再")
_PLANNING_PHRASE_RE = re.compile(
    r"(规划一下|帮我规划|列个计划|梳理一下|安排一下|分步骤|step\s*by\s*step)",
    re.I,
)

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


# ── 规划检测 ──────────────────────────────────────────────────────────────────


def message_suggests_structured_plan(text: str) -> bool:
    """检测用户消息是否暗示需要结构化规划。"""
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


# ── 路由提示 ──────────────────────────────────────────────────────────────────


def build_studio_peer_routing_hint(mgr: Any, current_agent_id: str) -> str:
    """构建 Agent 子进程可用的同事路由说明（@profile 格式）。"""
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
        "用户用 `@` 转发时匹配的是这个英文标识，**不是**模型供应商或 API 品牌名。\n\n"
        "本工作室内还有其他 Agent。当你需要把用户转交给某位同事时，"
        "在**给用户的建议**里以单行 `@<profile> ` 开头"
        "（`profile` 为下表英文标识；`@` 与 handle **无空格**；`@profile` 后必须跟一个空格再写正文）。\n\n"
        "可用同事：\n" + "\n".join(lines)
    )


# ── Agent ID 解析 ─────────────────────────────────────────────────────────────


def resolve_agent_id_for_token(mgr: Any, token: str) -> str | None:
    """将用户输入的 token 解析为 ``agent_id``。匹配 profile / displayName / agentId。"""
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


# ── Session 查找/创建 ─────────────────────────────────────────────────────────


def find_or_create_session_for_agent(mgr: Any, agent_id: str, cols: int) -> dict[str, Any]:
    """为指定 Agent 查找或创建会话。返回 {"sessionId", "agentId", "displayName"}。"""
    from backend.services.chat import create_session

    sids = mgr.session_ids_for_agent(agent_id)
    if sids:
        disp = agent_id
        for a in mgr.list_agents():
            if a.get("agentId") == agent_id:
                disp = str(a.get("displayName") or "").strip() or agent_id
                break
        return {"sessionId": sids[0], "agentId": agent_id, "displayName": disp}
    return create_session(agent_id, cols)


# ── Prompt 提交（含路由提示）──────────────────────────────────────────────────


def submit_with_hint(session_id: str, text: str, attachments: list[str] | None) -> str:
    """通过 ``<memory-context>`` 注入管道提交 prompt；返回 agent_id。

    替代原来无效的 ``studio.set_routing_hint`` JSON-RPC 调用（vendor 不认此方法）。

    每个 turn 提交前：
    1. 首次提交时注入跨会话摘要（Gap 2）
    2. 每次提交时注入人格/路由/规划提示（Gap 0）
    3. 检测 MEMORY.md 变化并注入增量（Gap 1 / Phase 2）
    4. 所有上下文由 ``<memory-context>`` 包裹，vendor 自动过滤
    """
    from backend.services.agent import _get_manager

    mgr = _get_manager()
    info = mgr.find_agent_by_session(session_id)
    if info is None:
        raise ValueError("会话不存在")

    agent_id = info.agent_id
    user_text = text  # 保存原始用户消息，用于情感分析

    # 读取性格设定
    try:
        from backend.services import agent_db as _agent_db
        personality_data = _agent_db.get_personality(agent_id)
    except Exception:
        personality_data = {"personality": "", "catchphrases": "", "memes": ""}

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
        if random.random() < 0.6:
            chosen_meme = random.choice(meme_lines)
            personality_parts.append(f"【梗语】（可选使用）{chosen_meme}")

    personality_hint = ("\n".join(personality_parts) + "\n") if personality_parts else ""

    routing = build_studio_peer_routing_hint(mgr, agent_id)
    want_plan = message_suggests_structured_plan(text)
    if want_plan:
        _log.info(
            "studio: structured plan hint for session=%s agent=%s preview=%r",
            session_id,
            agent_id,
            (text or "")[:200].replace("\n", "\\n"),
        )

    # ── 能量门控：节能模式下拒绝新任务 ─────────────────────────────────
    try:
        import asyncio
        from backend.services.energy import get_energy_service
        energy_svc = get_energy_service()
        if asyncio.run(energy_svc.is_power_save(agent_id)):
            _log.info("bridge: power_save refused agent=%s", agent_id)
            raise RuntimeError("agent_power_save_refuse: Agent 饱食度过低，已进入节能模式")
    except Exception as e:
        if "agent_power_save_refuse" in str(e):
            raise
        _log.debug("bridge: power_save check failed for agent=%s: %s", agent_id, e)

    # ── 构建 <memory-context> 注入管道 ─────────────────────────────────

    from backend.vendor_patches.memory_context import (
        build_session_startup_context,
        build_routing_context,
        build_memory_context_block,
        build_self_model_context,
        build_memory_delta_context,
        build_turn_memory_context,
        is_first_turn_for_session,
    )

    memory_blocks: list[str] = []

    # Gap 2: 首次提交时注入跨会话摘要
    first_turn = is_first_turn_for_session(session_id)
    if first_turn:
        startup_ctx = build_session_startup_context(agent_id, session_id, True)
        if startup_ctx:
            memory_blocks.append(startup_ctx)

    # Gap 1 (Phase 2): 检测 MEMORY.md 变化，注入增量
    delta_ctx = build_memory_delta_context(agent_id, session_id)
    if delta_ctx:
        memory_blocks.append(delta_ctx)

    # Step 2: 注入自我模型（每 turn 执行）
    self_ctx = build_self_model_context(agent_id)
    if self_ctx:
        memory_blocks.append(self_ctx)

    # Phase 3+4: 实体提取 + 知识图谱查询 + MemOS 向量回溯（每 turn 执行）
    turn_ctx = build_turn_memory_context(
        agent_id, session_id, text,
        enable_vector_lookup=True,     # Phase 3: MemOS (Qdrant) 向量库已就绪
        enable_knowledge_graph=True,   # Phase 4: 知识图谱已就绪
    )
    if turn_ctx:
        memory_blocks.append(turn_ctx)

    # Gap 0: 路由/人格/规划提示
    # M2: 情绪状态注入
    emotion_hint = ""
    try:
        import asyncio
        from backend.services.emotion import get_emotion_service
        emotion_svc = get_emotion_service()
        emotion = asyncio.run(emotion_svc.get_emotion(agent_id))
        emotion_hint = (
            f"【当前情绪】愉悦度:{emotion['valence']:.1f} "
            f"唤醒度:{emotion['arousal']:.1f} "
            f"支配度:{emotion['dominance']:.1f}"
        )
    except Exception as e:
        _log.debug("bridge: emotion context fetch failed for agent=%s: %s", agent_id, e)

    routing_ctx = build_routing_context(
        agent_id,
        personality_hint=personality_hint,
        plan_hint=_STUDIO_PLAN_STRUCTURE_BLOCK if want_plan else "",
        peer_routing=routing,
        emotion_hint=emotion_hint,
    )
    if routing_ctx:
        memory_blocks.append(routing_ctx)

    # 组合所有上下文块，用 <memory-context> 包裹
    if memory_blocks:
        combined = "\n\n".join(memory_blocks)
        wrapped = build_memory_context_block(combined)
        text = f"{wrapped}\n\n{text}"

    # 提交 prompt
    # M3.4: 模型路由 — 分析输入并记录路由决策
    try:
        from backend.services.model_router import ModelRouter
        routing_decision = ModelRouter.route(agent_id, user_text)
        _log.debug("model_router: agent=%s routing=%s model=%s/%s privacy=%s",
                   agent_id, routing_decision.tier, routing_decision.provider,
                   routing_decision.model, routing_decision.privacy_sensitive)
    except Exception as e:
        _log.debug("model_router: route failed for agent=%s: %s", agent_id, e)

    # M4.1: 髓鞘化缓存查找 — 若高频问题已缓存答案则跳过 LLM
    cached_answer: str | None = None
    try:
        import asyncio
        from backend.services.myelination import MyelinationEngine
        myelination_engine = MyelinationEngine()
        # 用 user_text 前 120 字符作为缓存 key（去除记忆注入后的 text）
        cache_key = user_text[:120].strip()
        cached_answer = asyncio.run(myelination_engine.get_cache(agent_id, cache_key))
        if cached_answer:
            _log.info("myelination: cache hit for agent=%s key=%.60s", agent_id, cache_key)
        else:
            # 记录访问（不含缓存），推进阶段
            asyncio.run(myelination_engine.record_access(agent_id, cache_key, query_text=user_text))
    except Exception as e:
        _log.debug("myelination: cache lookup failed for agent=%s: %s", agent_id, e)

    if cached_answer:
        # 注入缓存答案代替用户消息
        text = f"【系统】以下问题是高频知识，已固化答案：\n用户问题：{user_text}\n固化答案：{cached_answer}\n\n请基于以上固化答案简短回复用户，不要重新推理。"
        _log.info("myelination: using cached answer for agent=%s", agent_id)

        # F5: 记录缓存命中成本（零费用）
        try:
            from backend.services.model_cost import get_cost_service
            get_cost_service().record_call(
                agent_id=agent_id,
                provider="local",
                model="cache",
                routing_tier="local",
                prompt_tokens=max(1, len(user_text) // 3),
                completion_tokens=max(1, len(cached_answer) // 3),
                cached=True,
            )
        except Exception as e:
            _log.debug("model_cost: cache record failed for agent=%s: %s", agent_id, e)

    ok = mgr.submit_prompt(session_id, text, attachments=attachments)
    if not ok:
        raise RuntimeError("提交失败")

    # 能量消耗：每轮推理消耗饱食度 + 微增生物电流
    try:
        import asyncio
        from backend.services.energy import get_energy_service
        energy_svc = get_energy_service()
        asyncio.run(energy_svc.apply_inference_cost(agent_id))
    except Exception as e:
        _log.debug("energy: inference cost apply failed for agent=%s: %s", agent_id, e)

    # M2: 用户消息情感分析并更新情绪
    try:
        import asyncio
        from backend.services.emotion import get_emotion_service, EmotionEngine
        emotion_svc = get_emotion_service()
        sentiment = EmotionEngine.analyze_sentiment(user_text)
        if sentiment:
            asyncio.run(emotion_svc.update_emotion(
                agent_id,
                valence_delta=sentiment.get("valence", 0.0),
                arousal_delta=sentiment.get("arousal", 0.0),
                dominance_delta=sentiment.get("dominance", 0.0),
                trigger="user_message_sentiment",
            ))
    except Exception as e:
        _log.debug("emotion: sentiment analysis failed for agent=%s: %s", agent_id, e)

    # M3.2: 顶嘴引擎 — 检测触发条件并生成顶嘴回复
    try:
        from backend.services.backtalk import BacktalkEngine, BacktalkIntensity
        backtalk_intensity = int(personality_data.get("backtalk_intensity", 0))
        if backtalk_intensity > 0:
            engine = BacktalkEngine()
            history_text = "\n".join(
                str(msg.get("content", ""))
                for msg in context[-10:] if isinstance(msg, dict)
            ) if context else ""
            triggers = engine.detect_triggers(
                user_text=user_text,
                history_snippet=history_text,
                agent_personality=personality_data,
            )
            if triggers:
                best_trigger = max(triggers, key=lambda t: t.confidence)
                import asyncio
                response = asyncio.run(engine.generate_response(
                    trigger=best_trigger,
                    intensity=backtalk_intensity,
                    agent_id=agent_id,
                ))
                if response:
                    from backend.services.gateway_studio_bridge import publish_gateway_event
                    asyncio.run(publish_gateway_event({
                        "type": "backtalk.generated",
                        "agent_id": agent_id,
                        "session_id": session_id,
                        "content": response.content,
                        "intensity": backtalk_intensity,
                        "intensity_label": BacktalkEngine.INTENSITY_LABELS.get(backtalk_intensity, "silent"),
                        "trigger_type": best_trigger.trigger_type,
                        "should_intercept": response.should_intercept,
                        "timestamp": time.time(),
                    }))
                    _log.info("backtalk: agent=%s intensity=%d trigger=%s", agent_id, backtalk_intensity, best_trigger.trigger_type)
    except Exception as e:
        _log.debug("backtalk: detect/generate failed for agent=%s: %s", agent_id, e)

    return agent_id


def submit_relay_payload(
    mgr: Any,
    target_aid: str,
    preferred_sid: str,
    payload: str,
    attachments: list[str] | None,
    cols: int,
) -> str:
    """向同事会话投递 handoff 正文；遇 busy 则 interrupt 后重试/新建会话。返回实际 session_id。"""

    def _try(sid: str) -> bool:
        try:
            submit_with_hint(sid, payload, attachments)
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
        "relay fallback new session %s → agent %s (preferred %s busy)",
        new_sid, target_aid, preferred_sid,
    )
    submit_with_hint(new_sid, payload, attachments)
    return new_sid


# ── 事件等待原语（从 orchestrate.py 提取）─────────────────────────────────────


def await_submit_and_complete(
    gw: Any,
    session_id: str,
    *,
    timeout: float,
    submit_fn: Any,
) -> dict[str, Any]:
    """先注册 handler，再执行 ``submit_fn()``，等待 ``message.complete``。

    返回 {"ok": bool, "error": str|None, "reply": str}
    """
    done = threading.Event()
    state: dict[str, Any] = {"streamed": "", "final": "", "err": ""}

    def handler(ev: dict) -> None:
        if str(ev.get("session_id") or "") != session_id:
            return
        et = str(ev.get("type") or "")
        pl = ev.get("payload") or {}
        if et == "message.delta":
            state["streamed"] += str(pl.get("text") or "")
        elif et == "message.complete":
            txt = pl.get("text")
            state["final"] = str(txt) if txt is not None else (state["streamed"] or "")
            done.set()
        elif et == "error":
            state["err"] = str(pl.get("message", pl))
            done.set()

    gw.on_event(handler)
    try:
        try:
            submit_fn()
        except Exception as exc:
            return {"ok": False, "error": str(exc), "reply": ""}
        if not done.wait(timeout=timeout):
            return {"ok": False, "error": "message_complete_timeout", "reply": state["streamed"]}
        if state["err"]:
            return {"ok": False, "error": state["err"], "reply": state["final"] or state["streamed"]}
        return {"ok": True, "error": None, "reply": state["final"] or state["streamed"]}
    finally:
        gw.remove_event(handler)


def await_submit_and_complete_any_sid(
    gw: Any,
    acceptable_sids: set[str],
    *,
    timeout: float,
    submit_fn: Any,
) -> dict[str, Any]:
    """``submit_fn`` 可能新建会话；用 ``acceptable_sids`` 集合匹配 ``session_id``。

    返回 {"ok": bool, "error": str|None, "reply": str}
    """
    done = threading.Event()
    state: dict[str, Any] = {"streamed": "", "final": "", "err": ""}

    def handler(ev: dict) -> None:
        sid = str(ev.get("session_id") or "")
        if sid not in acceptable_sids:
            return
        et = str(ev.get("type") or "")
        pl = ev.get("payload") or {}
        if et == "message.delta":
            state["streamed"] += str(pl.get("text") or "")
        elif et == "message.complete":
            txt = pl.get("text")
            state["final"] = str(txt) if txt is not None else (state["streamed"] or "")
            done.set()
        elif et == "error":
            state["err"] = str(pl.get("message", pl))
            done.set()

    gw.on_event(handler)
    try:
        try:
            submit_fn()
        except Exception as exc:
            return {"ok": False, "error": str(exc), "reply": ""}
        if not done.wait(timeout=timeout):
            return {"ok": False, "error": "message_complete_timeout", "reply": state["streamed"]}
        if state["err"]:
            return {"ok": False, "error": state["err"], "reply": state["final"] or state["streamed"]}
        return {"ok": True, "error": None, "reply": state["final"] or state["streamed"]}
    finally:
        gw.remove_event(handler)
