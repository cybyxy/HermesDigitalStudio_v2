"""Profile 扫描模块 — 启动时扫描、迁移、初始化 Agent。

对应 Spring Boot Service 层 — 所有函数接收 ``mgr`` 参数，不直接导入 agent.py。
"""

from __future__ import annotations

import logging
import re
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from backend.core.config import get_config

if TYPE_CHECKING:
    from backend.gateway.gateway import GatewayManager

_log = logging.getLogger(__name__)

# 旧版 Gateway 曾生成 agent-1、agent-2；现 agent_id 必须与 profile 目录名一致。
_LEGACY_AGENT_ID_RE = re.compile(r"^agent-\d+$")


def _hermes_home_path_for_profile(profile: str) -> str:
    """根据 profile 名称计算对应的 hermes_home 路径。

    default profile 直接使用 HERMES_HOME 根目录，其他 profile 使用 profiles/<name> 子目录。
    """
    base = get_config().hermes_home
    if profile == "default":
        return str(base)
    return str(base / "profiles" / profile)


def _migrate_legacy_runtime_agents(mgr: "GatewayManager") -> None:
    """将仍在运行、但 agentId 为 agent-N 且 profile 为目录名的实例迁成以 profile 为 agent_id。

    同时把 SQLite 里 legacy 主键上的 avatar 合并到 profile 主键（若缺失）。
    每次只迁一条后刷新列表，避免对 ``list()`` 快照迭代时漏迁后续 legacy。
    """
    from backend.services import agent_db as _agent_db

    for _ in range(32):
        moved = False
        for agent_info in list(mgr.list_agents()):
            legacy_id = agent_info.get("agentId") or ""
            profile = (agent_info.get("profile") or "default").strip() or "default"
            if not _LEGACY_AGENT_ID_RE.match(legacy_id) or legacy_id == profile:
                continue

            info = mgr.get_agent(legacy_id)
            if info is None:
                continue

            display_name = agent_info.get("displayName") or f"{profile.capitalize()} Agent"
            gw_home = getattr(info.gateway, "hermes_home", None)
            hermes_home = str(Path(gw_home).expanduser()) if gw_home else _hermes_home_path_for_profile(profile)
            old_avatar = _agent_db.get_avatar(legacy_id)

            if mgr.get_agent(profile):
                _log.info("关闭重复 legacy agent %s（已有 profile=%s）", legacy_id, profile)
                mgr.close_agent(legacy_id)
                _agent_db.delete_agent(legacy_id)
                if old_avatar and _agent_db.get_avatar(profile) is None:
                    _agent_db.set_avatar(profile, old_avatar)
            else:
                _log.info("迁移 legacy agent_id %s → %s", legacy_id, profile)
                mgr.close_agent(legacy_id)
                _agent_db.delete_agent(legacy_id)
                _ensure_agent_avatar(mgr, profile, display_name=display_name, hermes_home=hermes_home)
                if old_avatar:
                    try:
                        _agent_db.set_avatar(profile, old_avatar)
                    except Exception:
                        pass
            moved = True
            break
        if not moved:
            break


def _prune_orphan_legacy_db_rows(mgr: "GatewayManager") -> None:
    """删除 DB 中 agent-* 主键且当前无任何运行中 agent 使用该 id 的行。"""
    from backend.services import agent_db as _agent_db

    active_ids = {a.get("agentId") for a in mgr.list_agents() if a.get("agentId")}
    for db_id in list(_agent_db.list_db_agents().keys()):
        if not _LEGACY_AGENT_ID_RE.match(db_id):
            continue
        if db_id in active_ids:
            continue
        _log.info("删除孤儿 legacy DB 行: %s", db_id)
        _agent_db.delete_agent(db_id)


def _startup_agents(mgr: "GatewayManager") -> None:
    """后端启动时自动调用的初始化函数。

    扫描逻辑：
    1. 清理残留 Agent：运行中的 agent 但对应目录已不存在 → 关闭并从 DB 删除
    2. 同步 DB vs 扫描结果：
       - 扫描有 + DB有 → 保持一致（使用 DB 中的 avatar）
       - 扫描有 + DB无 → 新增 agent，从 DB 读取 avatar（默认 badboy）
       - 扫描无 + DB有 → agent 已关闭，从 DB 删除记录
    3. ~/.hermes/ 始终作为 default profile 启动一个 Agent
    4. ~/.hermes/profiles/ 下的每个子目录启动一个对应 profile 的 Agent
    """
    from backend.services import agent_db as _agent_db

    hermes_home = get_config().hermes_home
    profiles_dir = hermes_home / "profiles"

    # 计算 vendor 根（与 agent.py 中 _HERMES_VENDOR_ROOT 一致）
    _backend_dir = Path(__file__).resolve().parents[3]
    _repo_root = _backend_dir.parent
    _hermes_vendor_root = _repo_root / "vendor" / "hermes-agent"

    try:
        if _hermes_vendor_root.is_dir():
            sys.path.insert(0, str(_hermes_vendor_root))

        # ── 0. 收集扫描到的所有 profile ─────────────────────────────────────────
        valid_profiles: set[str] = {"default"}
        if profiles_dir.is_dir():
            valid_profiles.update(
                entry.name for entry in profiles_dir.iterdir()
                if entry.is_dir() and not entry.name.startswith('.')
            )

        # ── 1. 清理残留 agent（运行中有但扫描已无） ────────────────────────────
        for agent_info in mgr.list_agents():
            profile = agent_info.get("profile", "default")
            if profile not in valid_profiles:
                _log.info("清理残留 agent: %s (profile=%s)", agent_info["agentId"], profile)
                try:
                    mgr.close_agent(agent_info["agentId"])
                    _agent_db.delete_agent(agent_info["agentId"])
                except Exception as e:
                    _log.warning("关闭残留 agent 失败: %s", e)

        # ── 2. 确保 default agent 存在 ─────────────────────────────────────────
        existing_default = [a for a in mgr.list_agents() if a.get("profile") == "default"]
        if not existing_default:
            _ensure_agent_avatar(mgr, "default", hermes_home=str(hermes_home))

        # ── 3. 扫描 profiles/ 目录 ──────────────────────────────────────────────
        if profiles_dir.is_dir():
            for entry in profiles_dir.iterdir():
                if not entry.is_dir():
                    continue
                profile_name = entry.name
                if not profile_name or profile_name.startswith('.') or profile_name == 'default':
                    continue
                display = f"{profile_name.capitalize()} Agent"
                # 检查是否已在运行
                existing = [a for a in mgr.list_agents() if a.get("profile") == profile_name]
                if not existing:
                    _ensure_agent_avatar(
                        mgr, profile_name,
                        display_name=display,
                        hermes_home=str(entry),
                    )

        # 再次迁移（扫描过程中若曾以错误 id 创建，可在此收敛）
        _migrate_legacy_runtime_agents(mgr)
        _prune_orphan_legacy_db_rows(mgr)
    except Exception as e:
        _log.warning("启动 Agent 时出错: %s", e)


def _ensure_agent_avatar(
    mgr: "GatewayManager",
    profile: str,
    display_name: str = "",
    hermes_home: str | None = None,
) -> None:
    """确保 hermes_home 路径对应的 profile 在 DB 有 avatar 记录，然后启动 agent。

    agent_id 直接使用 profile 名称（如 "default"、"chengdu"），而不是自动生成的 "agent-1"。
    """
    from backend.services import agent_db as _agent_db
    from backend.services import session as _session

    # Load per-agent model from DB (if any) to pass as env to subprocess
    model_info = {"model": "", "model_provider": "", "model_base_url": ""}
    try:
        model_info = _agent_db.get_agent_model(profile)
    except Exception:
        pass

    info = mgr.create_agent(
        profile=profile,
        display_name=display_name or f"{profile.capitalize()} Agent",
        hermes_home=hermes_home,
        agent_id=profile,
        model=model_info.get("model") or None,
        model_provider=model_info.get("model_provider") or None,
    )
    _session.ensure_default_session(profile, cols=120)
    if _agent_db.get_avatar(info.agent_id) is None:
        try:
            _agent_db.set_avatar(info.agent_id, "badboy", gender="male")
        except Exception:
            pass
