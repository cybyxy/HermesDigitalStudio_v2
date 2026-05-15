"""子代理内存管理：MEMORY.md / USER.md 隔离 + 插件化内存 provider。

借 vendor 的 MemoryStore 或其兼容子类，支持用不同的路径名称。
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict

from backend.vendor_patches._common import _log, _tool_tls, _run_tls, safe_segment

_log = logging.getLogger(__name__)


def subagent_memory_dir(parent_session_id: str, child_session_id: str) -> Path:
    """获取子代理 MEMORY.md / USER.md 的隔离目录。"""
    from hermes_constants import get_hermes_home

    root = get_hermes_home() / "memories" / "subagents"
    return root / safe_segment(parent_session_id) / safe_segment(child_session_id)


class SubagentMemoryStore:
    """MEMORY.md / USER.md under ``base_dir`` (subclasses vendor ``MemoryStore``)."""

    def __new__(cls, base_dir: Path, memory_char_limit: int = 2200, user_char_limit: int = 1375):
        from tools.memory_tool import MemoryStore

        class _Store(MemoryStore):
            def __init__(self, mem_root: Path, mlim: int, ulim: int):
                self._hds_base = Path(mem_root)
                super().__init__(memory_char_limit=mlim, user_char_limit=ulim)

            def _path_for(self, target: str) -> Path:
                if target == "user":
                    return self._hds_base / "USER.md"
                return self._hds_base / "MEMORY.md"

            def load_from_disk(self) -> None:
                self._hds_base.mkdir(parents=True, exist_ok=True)
                self.memory_entries = self._read_file(self._path_for("memory"))
                self.user_entries = self._read_file(self._path_for("user"))
                self.memory_entries = list(dict.fromkeys(self.memory_entries))
                self.user_entries = list(dict.fromkeys(self.user_entries))
                self._system_prompt_snapshot = {
                    "memory": self._render_block("memory", self.memory_entries),
                    "user": self._render_block("user", self.user_entries),
                }

            def save_to_disk(self, target: str) -> None:
                self._hds_base.mkdir(parents=True, exist_ok=True)
                self._write_file(self._path_for(target), self._entries_for(target))

        return _Store(base_dir, memory_char_limit, user_char_limit)


def attach_subagent_memory(child: Any, parent_agent: Any) -> None:
    """Enable curated + plugin memory on a subagent (vendor uses skip_memory=True)."""
    try:
        from hermes_cli.config import load_config as _load_agent_config
        from hermes_constants import get_hermes_home

        _agent_cfg = _load_agent_config()
    except Exception:
        _agent_cfg = {}

    mem_config = _agent_cfg.get("memory", {}) if isinstance(_agent_cfg, dict) else {}
    if not isinstance(mem_config, dict):
        mem_config = {}

    memory_enabled = bool(mem_config.get("memory_enabled", False))
    user_profile_enabled = bool(mem_config.get("user_profile_enabled", False))
    provider_name = str(mem_config.get("provider", "") or "").strip()

    if not (memory_enabled or user_profile_enabled or provider_name):
        return

    parent_sid = getattr(parent_agent, "session_id", None) or "unknown_parent"
    mem_root = subagent_memory_dir(parent_sid, getattr(child, "session_id", "child"))

    child._memory_enabled = memory_enabled
    child._user_profile_enabled = user_profile_enabled
    try:
        child._memory_nudge_interval = int(mem_config.get("nudge_interval", 10))
    except (TypeError, ValueError):
        child._memory_nudge_interval = 10

    if memory_enabled or user_profile_enabled:
        child._memory_store = SubagentMemoryStore(
            mem_root,
            memory_char_limit=int(mem_config.get("memory_char_limit", 2200)),
            user_char_limit=int(mem_config.get("user_char_limit", 1375)),
        )
        child._memory_store.load_from_disk()

    child._memory_manager = None
    if provider_name:
        try:
            from agent.memory_manager import MemoryManager as _MemoryManager
            from plugins.memory import load_memory_provider as _load_mem

            child._memory_manager = _MemoryManager()
            _mp = _load_mem(provider_name)
            if _mp and _mp.is_available():
                child._memory_manager.add_provider(_mp)
            if child._memory_manager.providers:
                _init_kwargs: Dict[str, Any] = {
                    "session_id": child.session_id,
                    "platform": getattr(child, "platform", None) or "cli",
                    "hermes_home": str(get_hermes_home()),
                    "agent_context": "subagent",
                }
                db = getattr(child, "_session_db", None)
                if db:
                    try:
                        _st = db.get_session_title(child.session_id)
                        if _st:
                            _init_kwargs["session_title"] = _st
                    except Exception:
                        pass
                for attr, key in (
                    ("_user_id", "user_id"),
                    ("_user_name", "user_name"),
                    ("_chat_id", "chat_id"),
                    ("_chat_name", "chat_name"),
                    ("_chat_type", "chat_type"),
                    ("_thread_id", "thread_id"),
                    ("_gateway_session_key", "gateway_session_key"),
                ):
                    val = getattr(child, attr, None)
                    if val:
                        _init_kwargs[key] = val
                try:
                    from hermes_cli.profiles import get_active_profile_name

                    _profile = get_active_profile_name()
                    _init_kwargs["agent_identity"] = _profile
                    _init_kwargs["agent_workspace"] = "hermes"
                except Exception:
                    pass
                child._memory_manager.initialize_all(**_init_kwargs)
        except Exception as exc:
            _log.warning("Subagent memory provider init failed: %s", exc)
            child._memory_manager = None

    if child._memory_manager and child.tools is not None:
        _existing_tool_names = {
            t.get("function", {}).get("name")
            for t in child.tools
            if isinstance(t, dict)
        }
        for _schema in child._memory_manager.get_all_tool_schemas():
            _tname = _schema.get("name", "")
            if _tname and _tname in _existing_tool_names:
                continue
            _wrapped = {"type": "function", "function": _schema}
            child.tools.append(_wrapped)
            if _tname:
                child.valid_tool_names.add(_tname)
                _existing_tool_names.add(_tname)

    child._cached_system_prompt = None


def resolve_agent_for_session_search() -> Any:
    """返回当前活跃的 AIAgent（用于 session_search 作用域判断）。"""
    return getattr(_tool_tls, "agent", None) or getattr(_run_tls, "active_agent", None)
