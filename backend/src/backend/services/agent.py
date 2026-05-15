"""Agent 业务逻辑层：GatewayManager 生命周期管理、Agent CRUD。

对应 Spring Boot Service 层。

实际实现已拆分至：
- backend.services.soul_md          — SOUL.md 读写
- backend.services.profile_scanner   — profile 目录扫描 / 启动初始化
- backend.services.office_pose       — 办公室位姿持久化
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from backend.gateway.gateway import GatewayManager

_log = logging.getLogger(__name__)

# ``agent.py`` 位于 backend/src/backend/services/ — parents[3] = backend/ 目录，
# parents[4] = monorepo 根（与 gateway.py 中 _REPO_ROOT 一致）。
_BACKEND_DIR = Path(__file__).resolve().parents[3]
_REPO_ROOT = _BACKEND_DIR.parent
_HERMES_VENDOR_ROOT = _REPO_ROOT / "vendor" / "hermes-agent"

# ── 单例 Manager ─────────────────────────────────────────────────────────────

_manager: "GatewayManager | None" = None


def _get_manager() -> "GatewayManager":
    """延迟初始化 GatewayManager 单例，确保整个进程只存在一个实例。"""
    global _manager
    if _manager is None:
        from backend.gateway.gateway import GatewayManager
        from backend.services.profile_scanner import _startup_agents

        _manager = GatewayManager()
        _startup_agents(_manager)
    return _manager


# ── Agent CRUD ────────────────────────────────────────────────────────────────

def list_agents() -> list[dict]:
    """列出所有运行中的 Agent（avatar/gender 从 DB 读取）。"""
    from backend.services import agent_db as _agent_db
    from backend.services import session as _session

    mgr = _get_manager()
    # 长驻进程升级后可能仍残留 agent-N 主键；每次列表前尝试迁成 profile 名
    from backend.services.profile_scanner import _migrate_legacy_runtime_agents

    _migrate_legacy_runtime_agents(mgr)
    agents = mgr.list_agents()
    for a in agents:
        a["avatar"] = _agent_db.get_avatar(a["agentId"]) or "badboy"
        a["gender"] = _agent_db.get_gender(a["agentId"])
        a.update(_agent_db.get_personality(a["agentId"]))
        model_row = _agent_db.get_agent_model(a["agentId"])
        a.update(model_row)
        # 与 get_agent() 一致：前端 AgentInfo 使用 camelCase
        a["modelProvider"] = str(model_row.get("model_provider") or "").strip()
        a["modelBaseUrl"] = str(model_row.get("model_base_url") or "").strip()
        aid = a.get("agentId")
        if not aid:
            continue
        ginfo = mgr.get_agent(str(aid))
        if ginfo is None:
            continue
        sids = _session.list_session_ids_for_agent(str(aid))
        if not sids:
            sid_new = _session.ensure_default_session(str(aid), cols=120)
            sids = [sid_new] if sid_new else []
        if sids:
            a["defaultSessionId"] = sids[0]
        gw_home = getattr(ginfo.gateway, "hermes_home", None)
        if gw_home:
            shome = str(Path(gw_home).expanduser())
        else:
            from backend.services.profile_scanner import _hermes_home_path_for_profile
            shome = _hermes_home_path_for_profile(ginfo.profile)
        sp = Path(shome) / "SOUL.md"
        if sp.is_file():
            try:
                from backend.services.soul_md import parse_soul_md as _parse_soul_md
                soul_dn = str(_parse_soul_md(sp.read_text(encoding="utf-8")).get("displayName") or "").strip()
                if soul_dn:
                    a["displayName"] = soul_dn
            except Exception:
                pass
        # 与前端约定：始终带 officePose，无 DB 记录时为 null，便于首屏按后端坐标/朝向绘制
        a["officePose"] = _agent_db.get_office_pose(str(aid))
        # 模型名：SQLite 中有 per-agent 配置时以 DB 为准；否则回落到该 profile 的 config.yaml
        db_model = str(model_row.get("model") or "").strip()
        if db_model:
            a["model"] = db_model
        else:
            a["model"] = _read_agent_model(shome)
    try:
        from backend.services import gateway_studio_bridge as _gw_bridge

        _gw_bridge.write_studio_bridge_config_file()
    except Exception:
        pass
    return agents


def _read_agent_model(hermes_home: str) -> str:
    """从指定 hermes_home/config.yaml 读取当前模型的简短标识。"""
    import yaml

    cfg_path = Path(hermes_home) / "config.yaml"
    if not cfg_path.is_file():
        return ""
    try:
        cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
        model_cfg = cfg.get("model", {})
        if isinstance(model_cfg, str):
            return model_cfg
        if isinstance(model_cfg, dict):
            # 优先取 default（模型 ID），其次 provider
            return str(model_cfg.get("default") or model_cfg.get("model") or model_cfg.get("provider") or "").strip()
        return ""
    except Exception:
        return ""


# ── Agent detail / CRUD ─────────────────────────────────────────────────────

def get_agent(agent_id: str) -> dict:
    """获取指定 Agent 的完整信息，包括从 SOUL.md 解析出的角色设定。"""
    mgr = _get_manager()
    info = mgr.get_agent(agent_id)
    if info is None:
        raise FileNotFoundError(f"Agent '{agent_id}' 不存在")

    gw_home = getattr(info.gateway, "hermes_home", None)
    if gw_home:
        hermes_home = str(Path(gw_home).expanduser())
    else:
        from backend.services.profile_scanner import _hermes_home_path_for_profile
        hermes_home = _hermes_home_path_for_profile(info.profile)

    soul_path = Path(hermes_home) / "SOUL.md"
    parsed = {
        "displayName": info.display_name,
        "identity": "",
        "style": "",
        "defaults": "",
        "avoid": "",
        "coreTruths": "",
    }

    if soul_path.is_file():
        try:
            from backend.services.soul_md import parse_soul_md as _parse_soul_md
            text = soul_path.read_text(encoding="utf-8")
            parsed = _parse_soul_md(text)
        except Exception:
            pass

    disp = str(parsed.get("displayName", "") or "").strip()
    if not disp:
        disp = str(info.display_name or "").strip()

    # Load per-agent model config from DB
    model_info: dict[str, str] = {"model": "", "model_provider": "", "model_base_url": ""}
    try:
        from backend.services import agent_db as _agent_db
        model_info = _agent_db.get_agent_model(agent_id)
    except Exception:
        pass

    return {
        "agentId": agent_id,
        "profile": info.profile,
        "displayName": disp,
        "alive": info.gateway.is_alive(),
        "identity": parsed["identity"],
        "style": parsed["style"],
        "defaults": parsed["defaults"],
        "avoid": parsed["avoid"],
        "coreTruths": parsed["coreTruths"],
        "avatar": _get_avatar_from_db(agent_id),
        "gender": _get_gender_from_db(agent_id),
        **_get_personality_from_db(agent_id),
        "model": model_info.get("model", ""),
        "modelProvider": model_info.get("model_provider", ""),
        "modelBaseUrl": model_info.get("model_base_url", ""),
    }


def _get_avatar_from_db(agent_id: str) -> str:
    """从数据库查询 Agent 头像，未查到时返回默认头像 "badboy"。"""
    try:
        from backend.services import agent_db as _agent_db
        return _agent_db.get_avatar(agent_id) or "badboy"
    except Exception:
        return "badboy"


def _get_gender_from_db(agent_id: str) -> str:
    """从数据库查询 Agent 性别，未查到时默认返回 "male"。"""
    try:
        from backend.services import agent_db as _agent_db
        return _agent_db.get_gender(agent_id)
    except Exception:
        return "male"


def _get_personality_from_db(agent_id: str) -> dict[str, str]:
    """从数据库查询 Agent 性格设定，返回 personality、catchphrases、memes 三个字段。"""
    try:
        from backend.services import agent_db as _agent_db
        return _agent_db.get_personality(agent_id)
    except Exception:
        return {"personality": "", "catchphrases": "", "memes": ""}


def create_agent(
    profile: str,
    display_name: str,
    identity: str = "",
    style: str = "",
    defaults: str = "",
    avoid: str = "",
    core_truths: str = "",
    avatar: str = "badboy",
    gender: str = "male",
    personality: str = "",
    catchphrases: str = "",
    memes: str = "",
    model: str = "",
    model_provider: str = "",
    model_base_url: str = "",
    backtalk_intensity: int = 0,
) -> dict:
    """创建并启动一个新的 Agent 子进程。

    流程：
    1. 检查 profile 是否已存在（文件系统 + 运行中的 Agent）
    2. 若不存在，调用 GatewayManager.create_agent 启动子进程
    3. 若提供了 displayName，写入对应 profile 的 SOUL.md
    4. 自动为新 Agent 创建一个默认 session
    """
    mgr = _get_manager()
    hermes_home: str | None = None

    # ── 检查 profile 是否已存在 ────────────────────────────────────────────────
    if profile != "default":
        if _HERMES_VENDOR_ROOT.is_dir():
            sys.path.insert(0, str(_HERMES_VENDOR_ROOT))
        try:
            from hermes_cli.profiles import create_profile, profile_exists
        except Exception as e:
            _log.warning("无法导入 profiles 模块: %s", e)
            raise RuntimeError("Profile 支持不可用")

        # 检查文件系统是否存在
        if profile_exists(profile):
            raise FileNotFoundError(f"Profile '{profile}' 已存在")

        # 配置仅 ~/.hermes/config.yaml；不在 profiles/<name>/ 下创建或复制 config.yaml
        profile_dir = create_profile(profile)
        hermes_home = str(profile_dir)

        _log.info("创建 profile %s，路径 %s", profile, hermes_home)
    else:
        # 检查 default agent 是否已存在
        existing = [a for a in mgr.list_agents() if a.get("profile") == "default"]
        if existing:
            raise FileNotFoundError("Default Agent 已存在")

        hermes_home = os.path.expanduser("~/.hermes")

    # ── 创建 Agent ──────────────────────────────────────────────────────────────
    info = mgr.create_agent(
        profile=profile,
        display_name=display_name,
        hermes_home=hermes_home,
        agent_id=profile,
        model=model or None,
        model_provider=model_provider or None,
    )

    # ── 写入 SOUL.md ───────────────────────────────────────────────────────────
    if display_name:
        try:
            from backend.services.soul_md import write_soul_md as _write_soul_md
            _write_soul_md(
                hermes_home,
                display_name,
                identity=identity,
                style=style,
                defaults=defaults,
                avoid=avoid,
                core_truths=core_truths,
            )
        except Exception as e:
            _log.warning("写入 SOUL.md 失败: %s", e)

    # ── 创建默认 session ────────────────────────────────────────────────────────
    from backend.services import session as _session
    _session.ensure_default_session(info.agent_id, cols=120)

    # ── 写入 avatar + gender 到 DB ───────────────────────────────────────────
    try:
        from backend.services import agent_db as _agent_db
        _agent_db.set_avatar(info.agent_id, avatar or "badboy", gender=gender or "male")
    except Exception as e:
        _log.warning("写入 avatar/gender 失败: %s", e)

    # ── 写入 personality 到 DB ──────────────────────────────────────────────
    try:
        from backend.services import agent_db as _agent_db
        _agent_db.upsert_personality(
            info.agent_id,
            personality=personality or "",
            catchphrases=catchphrases or "",
            memes=memes or "",
            backtalk_intensity=backtalk_intensity,
        )
    except Exception as e:
        _log.warning("写入 personality 失败: %s", e)

    # ── 写入 model 到 DB ─────────────────────────────────────────────────────
    try:
        from backend.services import agent_db as _agent_db
        _agent_db.set_agent_model(
            info.agent_id,
            model=model or "",
            model_provider=model_provider or "",
            model_base_url=model_base_url or "",
        )
    except Exception as e:
        _log.warning("写入 model 失败: %s", e)

    return {
        "agentId": info.agent_id,
        "profile": info.profile,
        "displayName": info.display_name,
        "alive": info.gateway.is_alive(),
        "model": model or "",
        "modelProvider": model_provider or "",
        "modelBaseUrl": model_base_url or "",
    }


def close_agent(agent_id: str) -> None:
    """关闭指定 ID 的 Agent 子进程，释放资源，并删除其 profile 目录。

    执行完整的四层记忆清理（S8）：
    - Layer A: 删除 sessions/ 目录（随 profile 目录一起删除）
    - Layer B: DROP TABLE smry/cmap_{agent_id}；删除 agent_sessions 行
    - Layer C: 删除 SOUL.md / MEMORY.md / USER.md / memories/（随 profile 目录一起删除）
    - Layer D: DROP TABLE kgnode/kgedge_{agent_id}；清理向量库
    - Studio: 删除 agent_avatars / agent_personality 行
    """
    import re as _re
    mgr = _get_manager()

    # 获取 agent 的 profile 信息（在关闭前获取，因为关闭后 mgr 可能已丢失）
    profile_path: str | None = None
    try:
        info = mgr.get_agent(agent_id)
        if info is not None:
            gw_home = getattr(info.gateway, "hermes_home", None)
            if gw_home:
                profile_path = str(Path(gw_home).expanduser())
            else:
                from backend.services.profile_scanner import _hermes_home_path_for_profile
                profile_path = _hermes_home_path_for_profile(info.profile)
    except Exception:
        pass

    # 1. 关闭 Gateway 子进程
    mgr.close_agent(agent_id)

    # 2. 清理 per-agent 记忆分表（Layer B + Layer D）
    safe_id = _re.sub(r"\W", "_", agent_id).strip("_") or "unknown"
    _drop_agent_memory_tables(safe_id)

    # 2a. 清理 self_model.json
    try:
        from backend.services.self_model import delete_self_model as _delete_self_model
        _delete_self_model(agent_id)
    except Exception as e:
        _log.warning("清理 self_model.json 失败: %s", e)

    # 3. 清理 Studio DB 中的 Agent 配置记录
    from backend.services import agent_db as _agent_db
    _agent_db.delete_agent(agent_id)

    # 4. 删除 profile 目录（Layer A + Layer C 文件，default agent 不删目录）
    if profile_path:
        profile_dir = Path(profile_path)
        if profile_dir.is_dir() and profile_dir != Path(os.path.expanduser("~/.hermes")):
            import shutil
            try:
                shutil.rmtree(profile_dir)
                _log.info("已删除 profile 目录: %s", profile_dir)
            except Exception as e:
                _log.warning("删除 profile 目录失败: %s: %s", profile_dir, e)


def _drop_agent_memory_tables(safe_id: str) -> None:
    """删除 Agent 的 per-agent 记忆分表。

    清理以下表：
    - smry_{safe_id}（会话摘要缓存）
    - cmap_{safe_id}（压缩映射）
    - kgnode_{safe_id}（知识图谱节点）
    - kgedge_{safe_id}（知识图谱边）
    """
    tables_to_drop = [
        f"smry_{safe_id}",
        f"cmap_{safe_id}",
        f"kgnode_{safe_id}",
        f"kgedge_{safe_id}",
    ]
    try:
        from backend.db.connection import get_connection
        conn = get_connection()
        for table in tables_to_drop:
            try:
                conn.execute(f"DROP TABLE IF EXISTS \"{table}\"")
                _log.info("已删除记忆分表: %s", table)
            except Exception as e:
                _log.warning("删除记忆分表 %s 失败: %s", table, e)
        conn.commit()
        conn.close()
    except Exception as e:
        _log.warning("清理记忆分表失败: %s", e)


def update_agent(agent_id: str, fields: dict) -> dict:
    """更新指定 Agent 的字段。

    支持的字段：displayName, identity, style, defaults, avoid, coreTruths, avatar
    """
    mgr = _get_manager()

    # 找到 agent
    agent_info: dict | None = None
    for a in mgr.list_agents():
        if a.get("agentId") == agent_id or a.get("agent_id") == agent_id:
            agent_info = a
            break
    if not agent_info:
        raise FileNotFoundError(f"Agent '{agent_id}' 不存在")

    info = mgr.get_agent(agent_id)
    if info is None:
        raise FileNotFoundError(f"Agent '{agent_id}' 不存在")

    if fields.get("displayName") is not None:
        dn = str(fields["displayName"]).strip()
        if dn:
            info.display_name = dn

    gw_home = getattr(info.gateway, "hermes_home", None)
    if gw_home:
        hermes_home = str(Path(gw_home).expanduser())
    else:
        # list_agents() 不带 hermesHome；须与 get_agent / 子进程 HERMES_HOME 一致
        from backend.services.profile_scanner import _hermes_home_path_for_profile
        hermes_home = _hermes_home_path_for_profile(info.profile)

    soul_keys = ("displayName", "identity", "style", "defaults", "avoid", "coreTruths")
    if any(k in fields for k in soul_keys):
        try:
            cur = get_agent(agent_id)
            dn = fields.get("displayName", cur.get("displayName") or "")
            display_name = str(dn).strip() if dn is not None else ""
            if not display_name:
                display_name = str(cur.get("displayName") or info.profile).strip() or info.profile

            def _pick(key_api: str, key_cur: str) -> str:
                if key_api in fields and fields[key_api] is not None:
                    return str(fields[key_api])
                v = cur.get(key_cur)
                return v if isinstance(v, str) else ""

            from backend.services.soul_md import write_soul_md as _write_soul_md

            _write_soul_md(
                hermes_home,
                display_name,
                identity=_pick("identity", "identity"),
                style=_pick("style", "style"),
                defaults=_pick("defaults", "defaults"),
                avoid=_pick("avoid", "avoid"),
                core_truths=_pick("coreTruths", "coreTruths"),
            )
        except Exception as e:
            _log.warning("更新 SOUL.md 失败: %s", e)

    if "avatar" in fields and fields["avatar"] is not None:
        try:
            from backend.services import agent_db as _agent_db
            _agent_db.set_avatar(agent_id, fields["avatar"])
        except Exception as e:
            _log.warning("更新 avatar 失败: %s", e)

    if "gender" in fields and fields["gender"] is not None:
        try:
            from backend.services import agent_db as _agent_db
            _agent_db.set_gender(agent_id, fields["gender"])
        except Exception as e:
            _log.warning("更新 gender 失败: %s", e)

    # personality / catchphrases / memes / backtalk_intensity — all optional, all written together
    if any(k in fields for k in ("personality", "catchphrases", "memes", "backtalk_intensity")):
        try:
            from backend.services import agent_db as _agent_db
            cur = _agent_db.get_personality(agent_id)
            _agent_db.upsert_personality(
                agent_id,
                personality=str(fields.get("personality", cur.get("personality") or "") or ""),
                catchphrases=str(fields.get("catchphrases", cur.get("catchphrases") or "") or ""),
                memes=str(fields.get("memes", cur.get("memes") or "") or ""),
                backtalk_intensity=int(fields.get("backtalk_intensity", cur.get("backtalk_intensity") or 0) or 0),
            )
        except Exception as e:
            _log.warning("更新 personality 失败: %s", e)

    # model / modelProvider / modelBaseUrl — write to DB and update subprocess env
    model_changed = any(k in fields for k in ("model", "modelProvider", "modelBaseUrl"))
    if model_changed:
        try:
            from backend.services import agent_db as _agent_db
            cur = _agent_db.get_agent_model(agent_id)
            new_model = str(fields.get("model", cur.get("model") or "") or "").strip()
            new_provider = str(fields.get("modelProvider", cur.get("model_provider") or "") or "").strip()
            new_base_url = str(fields.get("modelBaseUrl", cur.get("model_base_url") or "") or "").strip()
            _agent_db.set_agent_model(agent_id, new_model, new_provider, new_base_url)
            # Update the running subprocess's env vars so the next turn uses the new model
            gw = info.gateway
            if new_model:
                gw.set_env("HERMES_MODEL", new_model)
            if new_provider:
                gw.set_env("HERMES_TUI_PROVIDER", new_provider)
            _log.info("Agent %s model updated: model=%s provider=%s", agent_id, new_model, new_provider)
        except Exception as e:
            _log.warning("更新 model 失败: %s", e)

    out_name = fields.get("displayName")
    if out_name is not None and str(out_name).strip():
        out_display = str(out_name).strip()
    else:
        out_display = str(info.display_name or agent_info.get("displayName", "")).strip()

    # Reload model info to return current state
    final_model_info = {"model": "", "modelProvider": "", "modelBaseUrl": ""}
    try:
        from backend.services import agent_db as _agent_db
        m = _agent_db.get_agent_model(agent_id)
        final_model_info = {
            "model": m.get("model", ""),
            "modelProvider": m.get("model_provider", ""),
            "modelBaseUrl": m.get("model_base_url", ""),
        }
    except Exception:
        pass

    return {
        "agentId": agent_id,
        "profile": agent_info.get("profile", "default"),
        "displayName": out_display,
        "alive": agent_info.get("alive", True),
        **final_model_info,
    }


# ── Agent memory (extracted to agent_memory.py) ──────────────────────────────

from backend.services.agent_memory import get_agent_memory, summarize_session_memory  # noqa: E402


def __getattr__(name: str):
    if name in ("_write_soul_md", "_parse_soul_md"):
        import backend.services.soul_md as _m
        return getattr(_m, name[1:])  # strip leading _
    if name in ("_hermes_home_path_for_profile", "_migrate_legacy_runtime_agents",
                "_prune_orphan_legacy_db_rows", "_startup_agents", "_ensure_agent_avatar"):
        import backend.services.profile_scanner as _m
        return getattr(_m, name)
    if name == "save_office_poses":
        import backend.services.office_pose as _m
        return getattr(_m, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
