"""Bungalow 风格编排：主 Agent 一轮结束后解析 assistant 中的 ``@`` 行并投递同伴会话。

支持两种入口：
- ``orchestrated_chat_sync``：阻塞直到结束（兼容旧 ``POST /orchestrated``）。
- ``start_orchestrated_background_run`` + ``orchestrated_control_stream``：``POST …/run`` 立即返回 ``run_id``，
  客户端用 ``GET …/stream?run_id=`` 收阶段事件与最终 ``orch_done``（缩短阻塞感）。
"""

from __future__ import annotations

import asyncio
import json
import logging
import queue
import re
import threading
import uuid
from collections.abc import Callable
from typing import Any

from backend.services.agent import _get_manager
from backend.services.agent_chat_bridge import (
    await_submit_and_complete,
    await_submit_and_complete_any_sid,
    find_or_create_session_for_agent,
    resolve_agent_id_for_token,
    submit_relay_payload,
    submit_with_hint,
)
from backend.services.chat import submit_prompt
from backend.services.handoff_parser import (
    expand_broadcast_invokes_studio,
    normalize_handoff_input,
    parse_assistant_invokes,
    parse_user_handoff_prefix,
    strip_assistant_invoke_lines,
)

_log = logging.getLogger(__name__)

MAX_INVOKE_DEPTH = 5
HANDOFF_CONTEXT_MAX = 28000

# F5 云端老师模式：提取云模型返回中的 MYELINATE 标记并固化为髓鞘化节点
_MYELINATE_RE = re.compile(r'<!--\s*MYELINATE:\s*(.*?)-->', re.DOTALL)

_ORCH_LOCK = threading.Lock()
_ORCH_QUEUES: dict[str, queue.Queue[dict[str, Any]]] = {}
_ORCH_META: dict[str, dict[str, Any]] = {}

_DELEGATION_GATES: dict[str, threading.Event] = {}
_DELEGATION_GATES_LOCK = threading.Lock()
# Studio 场景：同伴 relay 前由前端将双方走位到面对面，再 POST delegation_ready 解锁
_DELEGATION_SCENE_GATE_TIMEOUT_SEC = 180.0


def notify_delegation_ready(delegation_token: str) -> bool:
    """前端完成「走到同伴旁并面对面」后的回执，对应 ``orch_delegation_start.delegation_token``。"""
    tok = (delegation_token or "").strip()
    if not tok:
        return False
    with _DELEGATION_GATES_LOCK:
        ev = _DELEGATION_GATES.get(tok)
    if ev is None:
        return False
    ev.set()
    return True


def _orch_emit(sink: Callable[[dict[str, Any]], None] | None, ev: dict[str, Any]) -> None:
    """向 SSE sink 发送编排阶段事件，若 sink 为空则忽略。"""
    if sink is None:
        return
    try:
        sink(ev)
    except Exception as exc:
        _log.debug("orchestrate sink failed: %s", exc)


def _truncate_ctx(text: str, max_len: int = HANDOFF_CONTEXT_MAX) -> str:
    """截断上下文文本，保留首尾部分（头部 35%，尾部约 65%-80 字符），中间省略。"""
    u = text.strip()
    if len(u) <= max_len:
        return u
    head = int(max_len * 0.35)
    tail = max_len - head - 80
    if tail < 500:
        return u[:max_len] + "\n…[truncated]"
    omitted = len(u) - head - tail
    return f"{u[:head]}\n\n…[省略 {omitted} 字]…\n\n{u[-tail:]}"


def _compose_peer_payload(_mgr: Any, _peer_aid: str, invoker_reply: str, invoke_body: str) -> str:
    """构造发送给同伴 Agent 的用户消息：仅包含任务上下文与指令，路由说明由上层注入。"""
    stripped = strip_assistant_invoke_lines(invoker_reply)
    body = (invoke_body or "").strip()
    if not stripped.strip():
        return body
    return f"{_truncate_ctx(stripped)}\n\n{body}"


def _self_invoke_tokens(agent_id: str, agents: list[dict[str, Any]]) -> set[str]:
    """获取指定 Agent 的所有标识符（agentId、profile、displayName），用于检测自我调用。"""
    row = next((a for a in agents if str(a.get("agentId") or "") == agent_id), None)
    if not row:
        return {agent_id}
    toks = {
        agent_id,
        str(row.get("profile") or "").strip(),
        str(row.get("displayName") or "").strip(),
    }
    return {x for x in toks if x}


def _run_invokes_recursive(
    mgr: Any,
    invoker_aid: str,
    invoke_rows: list[tuple[str, str]],
    depth: int,
    invoker_full_reply: str,
    agents: list[dict[str, Any]],
    cols: int,
    complete_timeout: float,
    sink: Callable[[dict[str, Any]], None] | None,
) -> list[dict[str, Any]]:
    if depth > MAX_INVOKE_DEPTH:
        return []
    expanded = expand_broadcast_invokes_studio(invoker_aid, invoke_rows, agents)
    out: list[dict[str, Any]] = []
    self_t = _self_invoke_tokens(invoker_aid, agents)
    for target_token, submsg in expanded:
        tt = str(target_token).strip()
        if tt in self_t:
            out.append(
                {
                    "target": tt,
                    "ok": False,
                    "sessionId": None,
                    "agentId": None,
                    "displayName": "",
                    "error": "self_invoke_skipped",
                    "nested": [],
                }
            )
            continue
        peer_aid = resolve_agent_id_for_token(mgr, tt)
        if not peer_aid:
            out.append(
                {
                    "target": tt,
                    "ok": False,
                    "sessionId": None,
                    "agentId": None,
                    "displayName": "",
                    "error": "target_not_found",
                    "nested": [],
                }
            )
            continue
        sinfo = find_or_create_session_for_agent(mgr, peer_aid, cols)
        peer_sid = str(sinfo["sessionId"])
        disp = str(sinfo.get("displayName") or "").strip() or peer_aid
        payload = _compose_peer_payload(mgr, peer_aid, invoker_full_reply, submsg)
        peer_info = mgr.get_agent(peer_aid)
        if peer_info is None:
            out.append(
                {
                    "target": tt,
                    "ok": False,
                    "sessionId": peer_sid,
                    "agentId": peer_aid,
                    "displayName": disp,
                    "error": "peer_agent_missing",
                    "nested": [],
                }
            )
            continue
        # 有 SSE sink 时：先发事件让 Studio 场景走位，再 relay（无 sink 的旧同步入口不阻塞）
        if sink is not None:
            delegation_token = uuid.uuid4().hex[:16]
            gate = threading.Event()
            with _DELEGATION_GATES_LOCK:
                _DELEGATION_GATES[delegation_token] = gate
            try:
                _orch_emit(
                    sink,
                    {
                        "type": "orch_delegation_start",
                        "from_agent_id": invoker_aid,
                        "to_agent_id": peer_aid,
                        "target": tt,
                        "session_id": peer_sid,
                        "delegation_token": delegation_token,
                    },
                )
                if not gate.wait(timeout=_DELEGATION_SCENE_GATE_TIMEOUT_SEC):
                    _log.warning(
                        "orchestrate delegation scene gate timeout token=%s from=%s to=%s",
                        delegation_token,
                        invoker_aid,
                        peer_aid,
                    )
            finally:
                with _DELEGATION_GATES_LOCK:
                    _DELEGATION_GATES.pop(delegation_token, None)
        acceptable: set[str] = {peer_sid}
        sid_out: list[str] = [peer_sid]

        def submit_fn() -> None:
            sid_out[0] = str(submit_relay_payload(mgr, peer_aid, peer_sid, payload, None, cols))
            acceptable.add(sid_out[0])

        wait = await_submit_and_complete_any_sid(
            peer_info.gateway,
            acceptable,
            timeout=complete_timeout,
            submit_fn=submit_fn,
        )
        final_sid = sid_out[0]

        peer_reply = str(wait.get("reply") or "")
        nested_invokes = parse_assistant_invokes(peer_reply) if wait.get("ok") else []
        nested_list: list[dict[str, Any]] = []
        if nested_invokes:
            nested_list = _run_invokes_recursive(
                mgr,
                peer_aid,
                nested_invokes,
                depth + 1,
                peer_reply,
                agents,
                cols,
                complete_timeout,
                sink,
            )
        row = {
            "target": tt,
            "ok": bool(wait.get("ok")),
            "sessionId": final_sid,
            "agentId": peer_aid,
            "displayName": disp,
            "error": wait.get("error"),
            "reply": peer_reply if wait.get("ok") else None,
            "nested": nested_list,
        }
        out.append(row)
        _orch_emit(
            sink,
            {
                "type": "orch_delegation_end",
                "from_agent_id": invoker_aid,
                "to_agent_id": peer_aid,
                "target": tt,
                "ok": row["ok"],
                "session_id": final_sid,
                "error": wait.get("error"),
            },
        )
    return out


def orchestrated_chat_sync_with_sink(
    sink: Callable[[dict[str, Any]], None] | None,
    session_id: str,
    text: str,
    *,
    attachments: list[str] | None = None,
    cols: int = 120,
    auto_peer: bool = True,
    complete_timeout: float = 480.0,
) -> dict[str, Any]:
    """编排核心；``sink`` 用于 ``/run`` 控制面向前端推送阶段（主 Hermes 流式仍走既有 ``/sse/{session}``）。"""
    from backend.services import agent as agent_mod

    mgr = _get_manager()
    info = mgr.find_agent_by_session(session_id)
    if info is None:
        raise ValueError("会话不存在")

    _orch_emit(sink, {"type": "orch_phase", "phase": "start", "session_id": session_id})

    text_n = normalize_handoff_input(text)
    handoff = parse_user_handoff_prefix(text_n)
    if handoff:
        _orch_emit(sink, {"type": "orch_phase", "phase": "user_handoff"})
        base = submit_prompt(session_id, text, attachments=attachments, cols=cols)
        base["orchestrated"] = True
        base["delegations"] = []
        base["primary"] = {"ok": True, "userHandoff": True, "error": None}
        _orch_emit(sink, {"type": "orch_phase", "phase": "user_handoff_done"})
        return base

    agents = agent_mod.list_agents()
    source_aid = info.agent_id
    gw = info.gateway

    _orch_emit(
        sink,
        {"type": "orch_primary_begin", "session_id": session_id, "agent_id": source_aid},
    )

    # ── 能量门控：节能模式下拒绝新任务 ─────────────────────────────────
    try:
        import asyncio
        from backend.services.energy import get_energy_service
        energy_svc = get_energy_service()
        if asyncio.run(energy_svc.is_power_save(source_aid)):
            _log.info("orchestrate: power_save refused agent=%s", source_aid)
            _orch_emit(sink, {"type": "orch_phase", "phase": "power_save_blocked",
                              "agent_id": source_aid})
            return {
                "ok": False,
                "orchestrated": True,
                "status": "power_save_refused",
                "message": "Agent 饱食度过低，已进入节能模式，请稍后再试",
                "sessionId": session_id,
                "agentId": source_aid,
            }
    except Exception as e:
        _log.debug("orchestrate: power_save check failed: %s", e)

    # ── 任务提交前根据复杂度提升生物电流 ───────────────────────────────
    try:
        text_n = text_n or ""
        complexity = "simple" if len(text_n) < 100 else ("large" if len(text_n) > 500 else "medium")
        asyncio.run(energy_svc.apply_task_submit(source_aid, complexity))
    except Exception as e:
        _log.debug("orchestrate: task_submit energy failed: %s", e)

    wait = await_submit_and_complete(
        gw,
        session_id,
        timeout=complete_timeout,
        submit_fn=lambda: submit_with_hint(session_id, text_n, attachments),
    )
    _orch_emit(
        sink,
        {
            "type": "orch_primary_end",
            "session_id": session_id,
            "agent_id": source_aid,
            "ok": bool(wait.get("ok")),
            "error": wait.get("error"),
        },
    )
    if not wait.get("ok"):
        return {
            "ok": False,
            "orchestrated": True,
            "status": "error",
            "sessionId": session_id,
            "agentId": source_aid,
            "relayed": False,
            "delegations": [],
            "primary": {"ok": False, "error": wait.get("error"), "userHandoff": False},
        }

    primary_reply = str(wait.get("reply") or "")

    # F5 云端老师模式：提取云模型返回中的 MYELINATE 标记并固化为髓鞘化节点
    myelinate_matches = _MYELINATE_RE.findall(primary_reply)
    if myelinate_matches:
        try:
            from backend.services.myelination import MyelinationEngine
            engine = MyelinationEngine()
            user_key = (text_n or text)[:120].strip()
            for match in myelinate_matches:
                content = match.strip()
                if content:
                    asyncio.run(engine.set_cache(source_aid, user_key, content))
                    _log.info("orchestrate: MYELINATE extracted for agent=%s (len=%d)", source_aid, len(content))
            # 从回复中移除 MYELINATE 注释，确保前端不可见
            primary_reply = _MYELINATE_RE.sub('', primary_reply).strip()
        except Exception as e:
            _log.debug("orchestrate: MYELINATE extraction failed for agent=%s: %s", source_aid, e)

    # F5: 记录本轮模型调用成本（token 估算，非关键路径）
    if source_aid and primary_reply:
        try:
            from backend.services.model_router import ModelRouter
            from backend.services.model_cost import get_cost_service
            user_input = text_n or text
            routing = ModelRouter.route(source_aid, user_input)
            get_cost_service().record_call(
                agent_id=source_aid,
                provider=routing.provider,
                model=routing.model,
                routing_tier=routing.tier,
                prompt_tokens=max(1, len(user_input) // 3),
                completion_tokens=max(1, len(primary_reply) // 3),
                cached=False,
            )
        except Exception as e:
            _log.debug("orchestrate: model_cost record failed for agent=%s: %s", source_aid, e)

    # ── 自动写入本轮对话到 MemOS 向量库 + 知识图谱 ──────────────────
    try:
        from backend.services.mem_os_service import mos_add_text as _mos_add
        _user_input = text_n or text
        if _user_input.strip() and primary_reply.strip():
            _mem_text = (
                f"## 对话记录\n\n"
                f"**用户**: {_user_input}\n\n"
                f"**助手**: {primary_reply[:2000]}"
            )
            _mos_add(source_aid, _mem_text, session_id=session_id)
    except Exception:
        pass

    # 任务完成后恢复饱食度（正向激励）
    if source_aid:
        try:
            import asyncio
            from backend.services.energy import get_energy_service
            energy_svc = get_energy_service()
            asyncio.run(energy_svc.apply_positive_interaction(source_aid, "task_complete"))
        except Exception as e:
            _log.debug("orchestrate: energy recovery failed for agent=%s: %s", source_aid, e)

        # M2: 复杂任务完成 → 提升唤醒度
        try:
            from backend.services.emotion import get_emotion_service
            emotion_svc = get_emotion_service()
            asyncio.run(emotion_svc.update_emotion(
                source_aid, 0.0, 0.15, 0.0, "complex_task_complete",
            ))
        except Exception as e:
            _log.debug("orchestrate: emotion arousal boost failed: %s", e)

    delegations: list[dict[str, Any]] = []
    if auto_peer and len(agents) > 1:
        invokes = parse_assistant_invokes(primary_reply)
        if invokes:
            _orch_emit(sink, {"type": "orch_phase", "phase": "delegations", "count": len(invokes)})
            delegations = _run_invokes_recursive(
                mgr,
                source_aid,
                invokes,
                0,
                primary_reply,
                agents,
                cols,
                complete_timeout,
                sink,
            )

    return {
        "ok": True,
        "orchestrated": True,
        "status": "streaming",
        "sessionId": session_id,
        "agentId": source_aid,
        "relayed": False,
        "delegations": delegations,
        "primary": {"ok": True, "error": None, "userHandoff": False},
    }


def orchestrated_chat_sync(
    session_id: str,
    text: str,
    *,
    attachments: list[str] | None = None,
    cols: int = 120,
    auto_peer: bool = True,
    complete_timeout: float = 480.0,
) -> dict[str, Any]:
    """阻塞编排（无控制面 sink）。"""
    return orchestrated_chat_sync_with_sink(
        None,
        session_id,
        text,
        attachments=attachments,
        cols=cols,
        auto_peer=auto_peer,
        complete_timeout=complete_timeout,
    )


def _orch_queue_put(run_id: str, item: dict[str, Any]) -> None:
    with _ORCH_LOCK:
        q = _ORCH_QUEUES.get(run_id)
    if q is not None:
        try:
            q.put_nowait(item)
        except Exception:
            q.put(item)


def _orch_worker(
    run_id: str,
    session_id: str,
    text: str,
    attachments: list[str] | None,
    cols: int,
    auto_peer: bool,
    complete_timeout: float,
) -> None:
    def sink(ev: dict[str, Any]) -> None:
        _orch_queue_put(run_id, {**ev, "run_id": run_id})

    try:
        result = orchestrated_chat_sync_with_sink(
            sink,
            session_id,
            text,
            attachments=attachments,
            cols=cols,
            auto_peer=auto_peer,
            complete_timeout=complete_timeout,
        )
        _orch_queue_put(run_id, {"type": "orch_done", "result": result})
    except ValueError as e:
        _orch_queue_put(
            run_id,
            {
                "type": "orch_done",
                "result": {
                    "ok": False,
                    "orchestrated": True,
                    "error": str(e),
                    "sessionId": session_id,
                    "relayed": False,
                    "delegations": [],
                    "primary": {"ok": False, "error": str(e), "userHandoff": False},
                },
            },
        )
    except Exception as e:
        _log.exception("orchestrated run %s failed", run_id)
        _orch_queue_put(
            run_id,
            {
                "type": "orch_done",
                "result": {
                    "ok": False,
                    "orchestrated": True,
                    "error": str(e),
                    "sessionId": session_id,
                    "relayed": False,
                    "delegations": [],
                    "primary": {"ok": False, "error": str(e), "userHandoff": False},
                },
            },
        )
    finally:
        with _ORCH_LOCK:
            m = _ORCH_META.get(run_id)
            if m is not None:
                m["done"] = True


def start_orchestrated_background_run(
    session_id: str,
    text: str,
    *,
    attachments: list[str] | None = None,
    cols: int = 120,
    auto_peer: bool = True,
    complete_timeout: float = 480.0,
) -> str:
    """启动后台编排线程；返回 ``run_id``。客户端应连接 ``GET …/orchestrated/stream``。"""
    run_id = uuid.uuid4().hex[:16]
    q: queue.Queue[dict[str, Any]] = queue.Queue()
    with _ORCH_LOCK:
        _ORCH_QUEUES[run_id] = q
        _ORCH_META[run_id] = {"done": False, "session_id": session_id}
    threading.Thread(
        target=_orch_worker,
        args=(run_id, session_id, text, attachments, cols, auto_peer, complete_timeout),
        daemon=True,
        name=f"orch-{run_id}",
    ).start()
    _log.info("orchestrated run_start run_id=%s session=%s", run_id, session_id)
    return run_id


def orchestrated_pending(run_id: str) -> dict[str, Any]:
    """与 Bungalow ``pending`` 类似：轮询是否已结束。"""
    with _ORCH_LOCK:
        meta = _ORCH_META.get(run_id)
        q_exists = run_id in _ORCH_QUEUES
    if not q_exists:
        return {"ok": True, "done": True, "run_id": run_id}
    return {
        "ok": True,
        "done": bool(meta and meta.get("done")),
        "run_id": run_id,
        "session_id": (meta or {}).get("session_id"),
    }


def _cleanup_run(run_id: str) -> None:
    with _ORCH_LOCK:
        _ORCH_QUEUES.pop(run_id, None)
        _ORCH_META.pop(run_id, None)


async def orchestrated_control_stream(run_id: str) -> Any:
    """Async generator：``data:`` JSON 行，直至 ``orch_done``。"""
    with _ORCH_LOCK:
        q = _ORCH_QUEUES.get(run_id)
    if q is None:
        yield "data: " + json.dumps({"type": "orch_error", "message": "unknown_run_id", "run_id": run_id}) + "\n\n"
        return

    try:
        while True:
            try:
                item = await asyncio.wait_for(
                    asyncio.to_thread(lambda: q.get(timeout=25.0)),
                    timeout=30.0,
                )
            except asyncio.TimeoutError:
                with _ORCH_LOCK:
                    done = bool((_ORCH_META.get(run_id) or {}).get("done"))
                if done and q.empty():
                    break
                yield ": keepalive\n\n"
                continue
            line = "data: " + json.dumps(item, ensure_ascii=False) + "\n\n"
            yield line
            if item.get("type") == "orch_done":
                break
    finally:
        _cleanup_run(run_id)
