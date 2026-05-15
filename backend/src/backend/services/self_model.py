"""SelfModel 读写模块 — Agent 自我模型的持久化文件 I/O。

每个 Agent 在 ``hermes_home/{profile}/self_model.json`` 中保存一份自我模型，
包含偏好、能力自知、行为模式、衍生特质和反思历史。

遵循 ``soul_md.py`` 的 File I/O Service 模式。
"""

from __future__ import annotations

import json
import logging
import shutil
import tempfile
import time
from pathlib import Path
from typing import Any

_log = logging.getLogger(__name__)

# ── 常量 ──────────────────────────────────────────────────────────────────────

SELF_MODEL_FILENAME = "self_model.json"
SELF_MODEL_BACKUP_FILENAME = "self_model.json.bak"
SELF_MODEL_VERSION = 1
FIELD_MAX_CHARS = 5000
HISTORY_MAX_ENTRIES = 50
HISTORY_MAX_AGE_DAYS = 90

_DEFAULT_SELF_MODEL: dict[str, Any] = {
    "version": SELF_MODEL_VERSION,
    "updated_at": 0.0,
    "preferences": "",
    "capabilities": "",
    "behavioral_patterns": "",
    "derived_traits": "",
    "reflection_history": [],
}


# ── 核心读写函数 ──────────────────────────────────────────────────────────────


def read_self_model(hermes_home: str) -> dict[str, Any]:
    """从指定 agent 的 hermes_home 读取 self_model.json。

    若文件不存在或损坏，返回默认空结构。
    """
    path = Path(hermes_home) / SELF_MODEL_FILENAME
    if not path.is_file():
        return dict(_DEFAULT_SELF_MODEL)

    try:
        content = path.read_text(encoding="utf-8")
        data = json.loads(content)
        # 版本兼容：补充缺失字段
        for k, v in _DEFAULT_SELF_MODEL.items():
            data.setdefault(k, v)
        return data
    except (json.JSONDecodeError, ValueError) as e:
        _log.warning("self_model.json corrupted at %s: %s, trying backup", path, e)
        # 尝试从备份恢复
        backup = Path(hermes_home) / SELF_MODEL_BACKUP_FILENAME
        if backup.is_file():
            try:
                content = backup.read_text(encoding="utf-8")
                data = json.loads(content)
                for k, v in _DEFAULT_SELF_MODEL.items():
                    data.setdefault(k, v)
                _log.info("self_model recovered from backup at %s", backup)
                return data
            except (json.JSONDecodeError, ValueError):
                _log.warning("backup also corrupted at %s", backup)
        return dict(_DEFAULT_SELF_MODEL)


def write_self_model(hermes_home: str, data: dict[str, Any]) -> None:
    """原子写入 self_model.json，同时维护备份文件。

    使用临时文件 + rename 模式防止写入中断导致数据损坏。
    """
    path = Path(hermes_home) / SELF_MODEL_FILENAME
    backup = Path(hermes_home) / SELF_MODEL_BACKUP_FILENAME

    data["version"] = SELF_MODEL_VERSION
    data["updated_at"] = time.time()

    # 裁剪字段
    data = _prune_model(data)

    # 写临时文件 → rename 原子替换
    tmp_path = Path(hermes_home) / f".{SELF_MODEL_FILENAME}.tmp"
    try:
        tmp_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        # 备份：复制当前文件（如果存在）到备份
        if path.is_file():
            shutil.copy2(str(path), str(backup))
        # 原子替换
        tmp_path.rename(path)
    except Exception as e:
        _log.error("write_self_model failed for %s: %s", hermes_home, e)
        if tmp_path.exists():
            tmp_path.unlink()
        raise


def get_self_model_for_agent(agent_id: str) -> dict[str, Any]:
    """通过 agent_id 间接定位 hermes_home 并读取 self_model。

    返回默认空结构（不抛异常）。
    """
    hermes_home = _resolve_hermes_home(agent_id)
    if not hermes_home:
        return dict(_DEFAULT_SELF_MODEL)
    return read_self_model(hermes_home)


def append_reflection_entry(
    agent_id: str,
    lesson: str,
    confidence: str = "medium",
) -> None:
    """追加一条反思记录到 reflection_history。"""
    if not lesson or not lesson.strip():
        return
    hermes_home = _resolve_hermes_home(agent_id)
    if not hermes_home:
        return

    data = read_self_model(hermes_home)
    entry = {
        "timestamp": time.time(),
        "lesson": lesson.strip(),
        "confidence": confidence if confidence in ("high", "medium", "low") else "medium",
    }
    history = data.get("reflection_history", [])
    history.append(entry)
    # 裁剪历史
    history = _prune_history(history)
    data["reflection_history"] = history
    write_self_model(hermes_home, data)


def update_self_model_field(agent_id: str, field: str, value: str) -> bool:
    """原子更新指定字段。

    支持的字段: preferences, capabilities, behavioral_patterns, derived_traits
    每个字段最大 FIELD_MAX_CHARS 字符。

    Returns:
        True on success, False if field is invalid.
    """
    valid_fields = {"preferences", "capabilities", "behavioral_patterns", "derived_traits"}
    if field not in valid_fields:
        return False

    hermes_home = _resolve_hermes_home(agent_id)
    if not hermes_home:
        return False

    data = read_self_model(hermes_home)
    # 追加而非覆盖，保留旧内容
    existing = data.get(field, "")
    if existing and existing.strip():
        combined = existing.rstrip("\n") + "\n" + value.strip()
    else:
        combined = value.strip()
    # 裁剪长度
    if len(combined) > FIELD_MAX_CHARS:
        combined = _prune_field(combined)
    data[field] = combined
    write_self_model(hermes_home, data)
    return True


def delete_self_model(agent_id: str) -> None:
    """删除 Agent 的 self_model.json 和备份文件。"""
    hermes_home = _resolve_hermes_home(agent_id)
    if not hermes_home:
        return

    path = Path(hermes_home) / SELF_MODEL_FILENAME
    if path.exists():
        path.unlink()
    backup = Path(hermes_home) / SELF_MODEL_BACKUP_FILENAME
    if backup.exists():
        backup.unlink()


# ── 内部辅助函数 ──────────────────────────────────────────────────────────────


def _resolve_hermes_home(agent_id: str) -> str | None:
    """解析 agent_id 到 hermes_home 目录路径。

    通过 GatewayManager 获取 agent info 推导路径，
    若失败则回退到 profile_scanner 的路径推断。
    """
    try:
        from backend.services.agent import _get_manager

        mgr = _get_manager()
        info = mgr.get_agent(agent_id)
        if info is not None:
            gw_home = getattr(info.gateway, "hermes_home", None)
            if gw_home:
                return str(Path(gw_home).expanduser())
            from backend.services.profile_scanner import _hermes_home_path_for_profile
            return _hermes_home_path_for_profile(info.profile)
    except Exception:
        pass

    # 兜底：从 profile_scanner 直接推断
    try:
        from backend.services.profile_scanner import _hermes_home_path_for_profile
        return _hermes_home_path_for_profile(agent_id)
    except Exception:
        pass

    return None


def _prune_model(data: dict[str, Any]) -> dict[str, Any]:
    """裁剪模型中所有字段到大小限制内。"""
    for field in ("preferences", "capabilities", "behavioral_patterns", "derived_traits"):
        val = data.get(field, "")
        if isinstance(val, str) and len(val) > FIELD_MAX_CHARS:
            data[field] = _prune_field(val)
    history = data.get("reflection_history", [])
    if isinstance(history, list):
        data["reflection_history"] = _prune_history(history)
    return data


def _prune_field(field_value: str) -> str:
    """裁剪字段内容：保留最近添加的条目（从最旧开始删除）。"""
    if not field_value:
        return ""
    if len(field_value) <= FIELD_MAX_CHARS:
        return field_value
    lines = field_value.split("\n")
    while len("\n".join(lines)) > FIELD_MAX_CHARS and lines:
        lines.pop(0)
    return "\n".join(lines)


def _prune_history(history: list[dict]) -> list[dict]:
    """裁剪反思历史：先按年龄删，再按数量删。"""
    cutoff = time.time() - HISTORY_MAX_AGE_DAYS * 86400
    history = [h for h in history if h.get("timestamp", 0) > cutoff]
    return history[-HISTORY_MAX_ENTRIES:]


# ── 导出 ──────────────────────────────────────────────────────────────────────

__all__ = [
    "read_self_model",
    "write_self_model",
    "get_self_model_for_agent",
    "append_reflection_entry",
    "update_self_model_field",
    "delete_self_model",
]
