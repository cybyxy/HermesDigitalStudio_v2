"""GatewayManager — 多 Agent 子进程池管理与 session 路由。

管理多个 SubprocessGateway 实例：
- 创建/关闭 Agent 子进程
- session 到 agent 的路由映射
- session 持久化与恢复
- session.switch 事件处理（上下文压缩）
"""

from __future__ import annotations

import logging
import re
import threading
import time
from dataclasses import dataclass

from backend.gateway.subprocess_gateway import SubprocessGateway

_log = logging.getLogger(__name__)


@dataclass
class AgentInfo:
    """Agent 元信息：子进程网关 + 标识属性。"""
    gateway: SubprocessGateway
    agent_id: str
    profile: str
    display_name: str
    created_at: float


class GatewayManager:
    """Manages multiple SubprocessGateway instances.

    Each agent is an independent hermes subprocess.  Sessions are routed
    to the agent that owns them via _sessions dict.
    """

    def __init__(self) -> None:
        self._agents: dict[str, AgentInfo] = {}
        self._sessions: dict[str, str] = {}  # session_id → agent_id
        self._lock = threading.Lock()
        self._shutdown_reflection = threading.Event()

        # 启动定时反思轮询（每 30 分钟兜底检查）
        self._reflection_timer = threading.Timer(
            1800.0, self._reflection_tick,
        )
        self._reflection_timer.daemon = True
        self._reflection_timer.start()
        _log.info("[GatewayManager] periodic reflection timer started (interval=1800s)")

    def _reflection_tick(self) -> None:
        """定时反思轮询：遍历所有 Agent 的 session，检查是否需要反思。

        这是一个兜底机制——主要触发点仍是 session.switch 时的 `_handle_session_switch`。
        定时器每 1800 秒（30 分钟）执行一次。
        """
        if self._shutdown_reflection.is_set():
            return

        try:
            from backend.vendor_patches.self_reflection import (
                check_reflection_eligibility,
                trigger_reflection,
            )

            agents = list(self._agents.keys())
            for agent_id in agents:
                # 获取该 agent 的所有 session
                try:
                    from backend.db.agent import AgentSessionDAO
                    sessions = AgentSessionDAO.list_agent_sessions(agent_id)
                except Exception:
                    continue

                for s in (sessions or []):
                    session_id = s.get("sessionId") or s.get("session_id")
                    if not session_id:
                        continue
                    # 检查 eligibility（内部含冷却、消息量、忙碌检查）
                    try:
                        if check_reflection_eligibility(agent_id, session_id):
                            trigger_reflection(agent_id, session_id)
                    except Exception:
                        continue
        except Exception as e:
            _log.debug("[GatewayManager] reflection tick error (non-fatal): %s", e)
        finally:
            if not self._shutdown_reflection.is_set():
                self._reflection_timer = threading.Timer(
                    1800.0, self._reflection_tick,
                )
                self._reflection_timer.daemon = True
                self._reflection_timer.start()

    def create_agent(self, profile: str = "default", display_name: str = "",
                     hermes_home: str | None = None,
                     agent_id: str | None = None,
                     model: str | None = None,
                     model_provider: str | None = None) -> AgentInfo:
        """Start a new hermes subprocess and register it.

        ``agent_id`` 与 Hermes profile 目录名一致（如 ``default``、``chengdu``）。
        若未传入或为空，则使用 ``profile``。
        """
        with self._lock:
            if not (agent_id and str(agent_id).strip()):
                agent_id = profile
            else:
                agent_id = str(agent_id).strip()
            prof_key = (profile or "default").strip() or "default"
            if re.fullmatch(r"agent-\d+", agent_id) and agent_id != prof_key:
                _log.warning(
                    "[GatewayManager] agent_id %r 为旧式编号，已改为 profile %r",
                    agent_id,
                    prof_key,
                )
                agent_id = prof_key
            if not display_name:
                display_name = f"{profile.capitalize()} Agent"
            gw = SubprocessGateway(
                session_id=agent_id,
                hermes_home=hermes_home,
                model=model,
                model_provider=model_provider,
            )
            gw.start()
            _capture_agent_id = agent_id
            gw._on_session_switch = lambda old_sid, new_sid: self._handle_session_switch(_capture_agent_id, old_sid, new_sid)
            info = AgentInfo(
                gateway=gw,
                agent_id=agent_id,
                profile=profile,
                display_name=display_name,
                created_at=time.monotonic(),
            )
            self._agents[agent_id] = info
            _log.info(
                "[GatewayManager] created agent %s (profile=%s, hermes_home=%s, model=%s, provider=%s)",
                agent_id, profile, hermes_home, model, model_provider,
            )
            return info

    def get_agent(self, agent_id: str) -> AgentInfo | None:
        """根据 agent_id 查询已注册的 Agent 信息。"""
        return self._agents.get(agent_id)

    def find_agent_by_session(self, session_id: str) -> AgentInfo | None:
        """根据 session_id 查找持有该会话的 Agent。"""
        ag_id = self._sessions.get(session_id)
        if ag_id:
            return self._agents.get(ag_id)
        return None

    def register_session(self, session_id: str, agent_id: str, parent_session_id: str | None = None, session_key: str | None = None) -> None:
        """将 session_id 与 agent_id 关联注册。"""
        self._sessions[session_id] = agent_id
        self._persist_session_to_db(agent_id, session_id, parent_session_id, session_key)

    def session_ids_for_agent(self, agent_id: str) -> list[str]:
        """返回当前映射到该 agent 的所有会话 id。"""
        with self._lock:
            return sorted(sid for sid, aid in self._sessions.items() if aid == agent_id)

    def ensure_default_session(self, agent_id: str, cols: int = 120) -> str | None:
        """若该 Agent 尚无已登记会话，则在子进程内 ``session.create`` 并登记到本 Manager。

        优先从 DB 恢复该 agent 最近活跃的 session（若子进程中仍存在），否则创建新 session。
        """
        # 1. 检查内存中是否已有 session
        with self._lock:
            existing = sorted(sid for sid, aid in self._sessions.items() if aid == agent_id)
            if existing:
                return existing[0]

        # 2. 尝试从 DB 恢复最近活跃的 session
        info = self._agents.get(agent_id)
        if info is not None:
            saved_sid = self._restore_session_from_db(agent_id, info, cols)
            if saved_sid:
                with self._lock:
                    self._sessions[saved_sid] = agent_id
                return saved_sid

        # 3. 创建新 session
        if info is None:
            return None
        sid, session_key = info.gateway.create_session_with_key(cols=cols)
        if not sid:
            _log.warning("[GatewayManager] ensure_default_session: create_session failed agent=%s", agent_id)
            return None
        with self._lock:
            self._sessions[sid] = agent_id
        self._persist_session_to_db(agent_id, sid, session_key=session_key)
        _log.info("[GatewayManager] created new default session %s → agent %s", sid, agent_id)
        return sid

    def _restore_session_from_db(self, agent_id: str, info: "AgentInfo", cols: int) -> str | None:
        """从 DB 恢复 agent 最近活跃的 session（若子进程中仍存在）。"""
        try:
            from backend.services import agent_db
        except ImportError:
            return None

        saved_sid = agent_db.get_active_agent_session(agent_id)
        if not saved_sid:
            return None

        sessions = info.gateway.session_list()
        session_ids = [s.get("id") or s.get("session_id") for s in sessions]
        if saved_sid not in session_ids:
            _log.info("[GatewayManager] DB session %s not found in subprocess, will create new", saved_sid)
            return None

        _log.info("[GatewayManager] restored session %s from DB for agent %s", saved_sid, agent_id)
        return saved_sid

    def _persist_session_to_db(self, agent_id: str, session_id: str, parent_session_id: str | None = None, session_key: str | None = None) -> None:
        """持久化 session 到 DB。"""
        try:
            from backend.services import agent_db
            agent_db.register_agent_session(agent_id, session_id, parent_session_id, session_key)
        except ImportError:
            _log.warning("[GatewayManager] failed to persist session to DB (import error)")

    def _handle_session_switch(self, agent_id: str, old_session_id: str, new_session_id: str) -> None:
        """处理子进程中上下文压缩导致的 session 切换。

        除了更新 session 路由映射和 DB 持久化外，同时记录压缩映射关系（需求 A），
        使后续 session 可通过 ``<memory-context>`` 获得追溯指引。
        """
        self._sessions[new_session_id] = agent_id

        try:
            from backend.services import agent_db
            old_sessions = agent_db.list_agent_sessions(agent_id)
            old_key = None
            for s in old_sessions:
                if s.get("session_id") == old_session_id:
                    old_key = s.get("session_key")
                    break

            self._persist_session_to_db(
                agent_id, new_session_id,
                parent_session_id=old_session_id,
                session_key=old_key,
            )
            agent_db.set_active_agent_session(agent_id, new_session_id)

            # 记录压缩映射（需求 A）
            try:
                from backend.db.memory import CompressionMapDAO
                CompressionMapDAO.record_compression(
                    agent_id=agent_id,
                    compressed_session_id=new_session_id,
                    original_session_id=old_session_id,
                    summary="",       # 由 S2 session_end 异步补充
                    key_topics="",     # 由 S2 session_end 异步补充
                )
            except Exception as e:
                _log.debug("compression map record failed (non-fatal): %s", e)

            _log.info(
                "[GatewayManager] session switch: %s → %s (agent=%s)",
                old_session_id, new_session_id, agent_id,
            )

            # 触发异步反思（L4 / Step 3）
            try:
                from backend.vendor_patches.self_reflection import trigger_reflection
                trigger_reflection(agent_id, old_session_id)
            except Exception as e:
                _log.debug("[GatewayManager] reflection trigger failed (non-fatal): %s", e)
        except Exception as e:
            _log.warning("[GatewayManager] session.switch persist failed: %s", e)

    def submit_prompt(self, session_id: str, text: str, attachments: list[str] | None = None) -> str | None:
        """向指定会话提交用户输入，返回所属 Agent 的 agent_id。"""
        info = self.find_agent_by_session(session_id)
        if info is None:
            _log.warning("[GatewayManager] session %s not found", session_id)
            return None
        ok = info.gateway.submit_prompt(session_id, text, attachments=attachments)
        if ok:
            self._sessions[session_id] = info.agent_id
            self._persist_session_to_db(info.agent_id, session_id)
            return info.agent_id
        return None

    def interrupt(self, session_id: str) -> bool:
        """中断指定会话的模型推理。"""
        info = self.find_agent_by_session(session_id)
        if info is None:
            return False
        return info.gateway.interrupt(session_id)

    def close_session(self, session_id: str) -> bool:
        """关闭指定会话，并触发 session-end 记忆提取。"""
        info = self.find_agent_by_session(session_id)
        if info is None:
            return False

        agent_id = info.agent_id
        self._sessions.pop(session_id, None)
        result = info.gateway.close_session(session_id)

        # Session-end 自动记忆提取（后台线程，不阻塞关闭流程）
        if result and agent_id:
            try:
                from backend.services.session_end_extractor import trigger_session_end_extraction
                trigger_session_end_extraction(agent_id, session_id, info.gateway, self)
            except Exception as e:
                _log.debug("close_session: extraction trigger failed: %s", e)

        return result

    def delete_session_by_db_record(self, agent_id: str, session_id: str) -> dict:
        """彻底删除会话：hermes state.db + 磁盘文件 + backend agent_sessions 表。"""
        try:
            from backend.services import agent_db
            sessions = agent_db.list_agent_sessions(agent_id)
        except Exception as e:
            return {"deleted": False, "error": f"无法查询会话记录: {e}"}

        session_key = None
        for s in sessions:
            if s.get("session_id") == session_id:
                session_key = s.get("session_key")
                break

        if not session_key:
            _log.warning("[GatewayManager] delete: no session_key for session_id=%s", session_id)
            try:
                from backend.db.agent import AgentSessionDAO
                AgentSessionDAO.delete_session(agent_id, session_id)
            except Exception:
                pass
            return {"deleted": True}

        info = self._agents.get(agent_id)
        if info is not None:
            ok = info.gateway.delete_session_by_key(session_key)
            if not ok:
                return {"deleted": False, "error": "子进程删除 hermes 会话失败"}

        self._sessions.pop(session_id, None)
        try:
            from backend.db.agent import AgentSessionDAO
            AgentSessionDAO.delete_session(agent_id, session_id)
        except Exception as e:
            _log.warning("[GatewayManager] delete: DB cleanup failed: %s", e)

        _log.info("[GatewayManager] deleted session %s (key=%s) for agent %s", session_id, session_key, agent_id)
        return {"deleted": True}

    def resume_session(self, agent_id: str, session_id: str, cols: int = 120) -> dict:
        """恢复一个旧会话：使用原始 session_id 和 session_key 重建。"""
        try:
            from backend.services import agent_db
            sessions = agent_db.list_agent_sessions(agent_id)
        except Exception as e:
            return {"error": f"无法查询会话记录: {e}"}

        session_key = None
        old_parent_session_id = None
        for s in sessions:
            if s.get("session_id") == session_id:
                session_key = s.get("session_key")
                old_parent_session_id = s.get("parent_session_id")
                break

        if not session_key:
            return {"error": "未找到该会话的 session_key（可能为旧版本数据）"}

        info = self._agents.get(agent_id)
        if info is None:
            return {"error": "Agent 未运行"}

        new_sid, _ = info.gateway.resume_session(session_key, session_id=session_id, cols=cols)
        if not new_sid:
            return {"error": "恢复会话失败（子进程创建超时）"}

        self._sessions[session_id] = agent_id
        self._persist_session_to_db(agent_id, session_id, parent_session_id=old_parent_session_id, session_key=session_key)
        try:
            from backend.db.agent import AgentSessionDAO
            AgentSessionDAO.set_active_session(agent_id, session_id)
        except Exception:
            pass

        _log.info("[GatewayManager] resumed session %s (key=%s, agent=%s)", session_id, session_key, agent_id)
        return {"sessionId": session_id, "agentId": agent_id}

    def close_agent(self, agent_id: str) -> None:
        """关闭指定 Agent 及其所有会话，释放子进程资源。"""
        with self._lock:
            info = self._agents.pop(agent_id, None)
        if info is None:
            return
        to_remove = [sid for sid, aid in list(self._sessions.items()) if aid == agent_id]
        for sid in to_remove:
            self._sessions.pop(sid, None)
        info.gateway.close()
        _log.info("[GatewayManager] closed agent %s", agent_id)

    def list_agents(self) -> list[dict]:
        """返回所有已注册的 Agent 列表（含运行状态）。"""
        with self._lock:
            return [
                {
                    "agentId": info.agent_id,
                    "profile": info.profile,
                    "displayName": info.display_name,
                    "createdAt": info.created_at,
                    "alive": info.gateway.is_alive(),
                }
                for info in self._agents.values()
            ]

    def shutdown_all(self) -> None:
        """关闭所有 Agent 子进程和后台定时器。"""
        self._shutdown_reflection.set()
        timer = getattr(self, "_reflection_timer", None)
        if timer:
            try:
                timer.cancel()
            except Exception:
                pass
        with self._lock:
            for agent_id in list(self._agents.keys()):
                info = self._agents.pop(agent_id, None)
                if info is not None:
                    info.gateway.close()
            self._sessions.clear()

    def respond_approval(self, session_id: str, choice: str, all: bool = False) -> bool:
        """转发工具调用审批响应到对应 Agent 子进程。"""
        info = self.find_agent_by_session(session_id)
        if info is None:
            return False
        return info.gateway.respond_approval(session_id, choice, all)

    def respond_clarify(self, session_id: str, request_id: str, answer: str) -> bool:
        """转发澄清响应到对应 Agent 子进程。"""
        info = self.find_agent_by_session(session_id)
        if info is None:
            return False
        return info.gateway.respond_clarify(session_id, request_id, answer)
