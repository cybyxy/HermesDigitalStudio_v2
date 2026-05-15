"""Session 业务逻辑层：协调 GatewayManager 子进程会话 与 AgentSessionDAO DB 会话。

对应 Spring Boot Service 层，承上（GatewayManager）启下（AgentSessionDAO）。
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from backend.gateway.gateway import GatewayManager

from backend.services.agent import _get_manager


# ── 高层 Session API ─────────────────────────────────────────────────────────

def ensure_default_session(agent_id: str, cols: int = 120) -> str | None:
    """确保指定 Agent 有一个活跃的默认会话。

    优先从 DB 恢复最近活跃的 session；若子进程中不存在则创建新 session。
    内部自动处理 DB 持久化。
    """
    mgr = _get_manager()
    try:
        return mgr.ensure_default_session(agent_id, cols=cols)
    except Exception as e:
        _log.warning("ensure_default_session(%s): %s", agent_id, e)
        return None


def list_session_ids_for_agent(agent_id: str) -> list[str]:
    """返回当前内存中映射到该 agent 的所有 session id（排序后）。"""
    mgr = _get_manager()
    return mgr.session_ids_for_agent(agent_id)


def register_session(agent_id: str, session_id: str, parent_session_id: str | None = None, session_key: str | None = None) -> None:
    """将会话注册到 DB（供外部显式注册时调用）。"""
    from backend.services import agent_db as _agent_db
    _agent_db.register_agent_session(agent_id, session_id, parent_session_id, session_key)


def submit_prompt(
    session_id: str,
    text: str,
    attachments: list[str] | None = None,
) -> str | None:
    """向指定会话提交用户输入，返回所属 Agent 的 agent_id。"""
    mgr = _get_manager()
    return mgr.submit_prompt(session_id, text, attachments=attachments)


def interrupt_session(session_id: str) -> bool:
    """中断指定会话的模型推理。"""
    mgr = _get_manager()
    return mgr.interrupt(session_id)


def close_session(session_id: str) -> bool:
    """关闭指定会话（同时从内存映射中移除）。"""
    mgr = _get_manager()
    return mgr.close_session(session_id)


def get_active_session(agent_id: str) -> str | None:
    """获取 agent 当前活跃的 session_id（从 DB 查询）。"""
    from backend.services import agent_db as _agent_db
    return _agent_db.get_active_agent_session(agent_id)


def list_agent_sessions(agent_id: str) -> list[dict]:
    """列出 agent 所有会话（从 DB 查询）。"""
    from backend.services import agent_db as _agent_db
    return _agent_db.list_agent_sessions(agent_id)


def set_active_session(agent_id: str, session_id: str) -> None:
    """将指定 session 标记为该 agent 的活跃会话。"""
    from backend.services import agent_db as _agent_db
    _agent_db.set_active_agent_session(agent_id, session_id)


def get_parent_session(session_id: str) -> str | None:
    """获取指定 session 的父 session ID。"""
    from backend.services import agent_db as _agent_db
    return _agent_db.get_parent_session(session_id)


def get_session_chain(session_id: str, max_depth: int = 10) -> list[str]:
    """获取 session 的完整续接链。"""
    from backend.services import agent_db as _agent_db
    return _agent_db.get_session_chain(session_id, max_depth=max_depth)


def touch_session(agent_id: str, session_id: str) -> None:
    """更新 session 的 last_used_at。"""
    from backend.services import agent_db as _agent_db
    _agent_db.touch_agent_session(agent_id, session_id)
