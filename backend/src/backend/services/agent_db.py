"""Agent SQLite persistence (delegated to DAO layer).

所有操作委托给 ``backend.db.agent`` 中的 DAO 类。
保留本文件仅用于向后兼容。
"""

from __future__ import annotations

import logging

from backend.core.config import get_config
from backend.db.agent import AgentAvatarDAO, AgentPersonalityDAO, AgentSessionDAO
from backend.db.connection import ensure_schema

_log = logging.getLogger(__name__)

# ── 兼容层：路径解析 ──────────────────────────────────────────────────

_DATA_DIR = get_config().studio_data_dir


def ensure_agent_db_schema() -> None:
    """确保数据库 schema 已初始化。委托给 DAO 层。"""
    ensure_schema()


# ── Avatar ────────────────────────────────────────────────────────────────────

def get_avatar(agent_id: str) -> str | None:
    return AgentAvatarDAO.get_avatar(agent_id)


def get_gender(agent_id: str) -> str:
    return AgentAvatarDAO.get_gender(agent_id)


def set_avatar(agent_id: str, avatar: str, gender: str | None = None) -> None:
    AgentAvatarDAO.set_avatar(agent_id, avatar, gender)


def set_gender(agent_id: str, gender: str) -> None:
    AgentAvatarDAO.set_gender(agent_id, gender)


def delete_agent(agent_id: str) -> None:
    AgentAvatarDAO.delete_agent(agent_id)


def get_office_pose(agent_id: str) -> dict[str, float | str] | None:
    return AgentAvatarDAO.get_office_pose(agent_id)


def upsert_office_poses(poses: dict[str, dict]) -> None:
    AgentAvatarDAO.upsert_office_poses(poses)


def list_db_agents() -> dict[str, str]:
    return AgentAvatarDAO.list_agents()


def list_db_agents_with_gender() -> dict[str, tuple[str, str]]:
    return AgentAvatarDAO.list_agents_with_gender()


# ── Personality ────────────────────────────────────────────────────────────────

def get_personality(agent_id: str) -> dict[str, str]:
    return AgentPersonalityDAO.get_personality(agent_id)


def upsert_personality(agent_id: str, personality: str = "", catchphrases: str = "", memes: str = "", backtalk_intensity: int = 0) -> None:
    AgentPersonalityDAO.upsert_personality(agent_id, personality, catchphrases, memes, backtalk_intensity)


# ── Agent model ──────────────────────────────────────────────────────────────

def get_agent_model(agent_id: str) -> dict[str, str]:
    return AgentAvatarDAO.get_agent_model(agent_id)


def set_agent_model(
    agent_id: str,
    model: str = "",
    model_provider: str = "",
    model_base_url: str = "",
) -> None:
    AgentAvatarDAO.set_agent_model(agent_id, model, model_provider, model_base_url)


# ── Session ───────────────────────────────────────────────────────────────────

def register_agent_session(agent_id: str, session_id: str, parent_session_id: str | None = None, session_key: str | None = None) -> None:
    """注册/更新 agent 的 session 记录。

    Args:
        agent_id: Agent ID
        session_id: Session ID (8-char hex)
        parent_session_id: 若不为空，表示该 session 是从另一个 session 压缩/续接而来的
        session_key: SessionDB 主键 (date-based format)，对应 state.db 和磁盘文件名
    """
    AgentSessionDAO.register_session(agent_id, session_id, parent_session_id, session_key)


def get_active_agent_session(agent_id: str) -> str | None:
    """获取 agent 当前活跃的 session_id。"""
    return AgentSessionDAO.get_active_session(agent_id)


def list_agent_sessions(agent_id: str) -> list[dict]:
    """列出 agent 所有 session。"""
    return AgentSessionDAO.list_agent_sessions(agent_id)


def list_all_sessions() -> list[dict]:
    """列出所有 session（按最后活跃时间倒序）。"""
    return AgentSessionDAO.list_all_sessions()


def touch_agent_session(agent_id: str, session_id: str) -> None:
    """更新 session 的 last_used_at。"""
    AgentSessionDAO.touch_session(agent_id, session_id)


def set_active_agent_session(agent_id: str, session_id: str) -> None:
    """将指定 session 标记为活跃。"""
    AgentSessionDAO.set_active_session(agent_id, session_id)


def get_parent_session(session_id: str) -> str | None:
    """获取指定 session 的父 session ID（用于压缩上下文后新 session 续接）。"""
    return AgentSessionDAO.get_parent_session(session_id)


def get_session_chain(session_id: str, max_depth: int = 10) -> list[str]:
    """获取 session 的完整续接链（从最老到最新）。"""
    return AgentSessionDAO.get_session_chain(session_id, max_depth)
