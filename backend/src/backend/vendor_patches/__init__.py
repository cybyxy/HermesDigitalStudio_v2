"""Vendor monkeypatch 模块。

对 ``vendor/hermes-agent`` 运行时补丁的分模块实现：
- ``_common``        — 共享状态和工具函数
- ``memory``         — 子代理内存隔离（MEMORY.md + 插件 provider）
- ``session_search`` — session_search 作用域限制
- ``delegate``       — delegate 工具集剥离 + 子代理实例复用
- ``lifecycle``      — AIAgent 生命周期追踪 + 上下文压缩事件
- ``memory_context`` — 四层记忆运行时注入管道（<memory-context> 构建）

所有补丁通过 ``apply_runtime_patches()`` 统一应用。
"""

import logging

from backend.vendor_patches._common import _ext_enabled
import backend.vendor_patches._common as _cmn

_log = logging.getLogger(__name__)

from backend.vendor_patches.memory import (
    SubagentMemoryStore,
    attach_subagent_memory,
    subagent_memory_dir,
    resolve_agent_for_session_search,
)
from backend.vendor_patches.session_search import patch_session_search
from backend.vendor_patches.delegate import (
    patch_delegate_strip,
    patch_build_child_agent,
    patch_run_single_child,
)
from backend.vendor_patches.lifecycle import (
    patch_aiagent_run_conversation,
    patch_invoke_tool,
    patch_aiagent_close,
    patch_compress_context,
)
from backend.vendor_patches.memory_context import (
    build_session_startup_context,
    build_routing_context,
    build_memory_context_block,
    build_self_model_context,
    build_memory_delta_context,
    build_turn_memory_context,
    extract_entities,
    is_first_turn_for_session,
    reset_session_tracker,
    record_session_mtimes,
    cleanup_session_mtime,
)
from backend.vendor_patches.self_reflection import (
    trigger_reflection,
    check_reflection_eligibility,
)


def apply_runtime_patches() -> None:
    """Idempotent: safe to call more than once."""
    if _cmn._PATCHED:
        return
    if not _ext_enabled():
        _log.debug("hermes_subagent_ext disabled (HERMES_HDS_SUBAGENT_EXT_DISABLE)")
        _cmn._PATCHED = True
        return
    try:
        patch_delegate_strip()
        patch_build_child_agent()
        patch_run_single_child()
        patch_aiagent_run_conversation()
        patch_invoke_tool()
        patch_session_search()
        patch_aiagent_close()
        patch_compress_context()
        _log.info("hermes_subagent_ext: runtime patches applied")
    except Exception:
        _log.exception(
            "hermes_subagent_ext: patch failed; gateway continues without full patches"
        )
    finally:
        _cmn._PATCHED = True


__all__ = [
    "apply_runtime_patches",
    "SubagentMemoryStore",
    "attach_subagent_memory",
    "subagent_memory_dir",
    "resolve_agent_for_session_search",
    "patch_session_search",
    "patch_delegate_strip",
    "patch_build_child_agent",
    "patch_run_single_child",
    "patch_aiagent_run_conversation",
    "patch_invoke_tool",
    "patch_aiagent_close",
    "patch_compress_context",
    "build_session_startup_context",
    "build_routing_context",
    "build_memory_context_block",
    "build_memory_delta_context",
    "build_turn_memory_context",
    "extract_entities",
    "is_first_turn_for_session",
    "reset_session_tracker",
    "record_session_mtimes",
    "cleanup_session_mtime",
]
