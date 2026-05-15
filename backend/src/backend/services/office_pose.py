"""办公室位姿持久化模块。

将前端"办公室"场景中的人物位置与朝向写入 SQLite。
"""

from __future__ import annotations

import logging

_log = logging.getLogger(__name__)


def save_office_poses(poses: dict[str, dict]) -> None:
    """持久化办公室人物位姿；仅写入当前 Gateway 中仍存在的 agent_id。"""
    if not poses:
        return

    from backend.services.agent import _get_manager
    from backend.services import agent_db as _agent_db

    mgr = _get_manager()
    active = {str(a.get("agentId")) for a in mgr.list_agents() if a.get("agentId")}
    filtered = {k: v for k, v in poses.items() if k in active}
    if filtered:
        _agent_db.upsert_office_poses(filtered)
