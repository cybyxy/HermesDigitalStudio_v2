"""子代理委托工具 monkeypatch：工具集剥离、实例复用、上下文重建。

- ``_patch_delegate_strip``: 移除子代理的 delegation/clarify/code_execution 工具集
- ``_patch_build_child_agent``: 拦截子代理创建，复用池中的实例
- ``_patch_run_single_child``: 拦截子代理完成，将实例回收到池中
"""

from __future__ import annotations

import logging
import uuid as _uuid
from typing import Any, List, Optional

from backend.vendor_patches._common import (
    _log,
    _reuse_enabled,
    _SUBAGENT_POOL,
)
from backend.vendor_patches.memory import (
    attach_subagent_memory,
)

_log = logging.getLogger(__name__)


# ── delegate_strip ───────────────────────────────────────────────────────────


def patch_delegate_strip() -> None:
    """移除子代理不可用的工具集，并注入自定义 strip 逻辑。"""
    import tools.delegate_tool as dt

    blocked = frozenset({"delegate_task", "clarify", "send_message", "execute_code"})
    dt.DELEGATE_BLOCKED_TOOLS = blocked

    def _strip_blocked_tools(toolsets: List[str]) -> List[str]:
        blocked_toolset_names = {
            "delegation",
            "clarify",
            "code_execution",
        }
        return [t for t in toolsets if t not in blocked_toolset_names]

    dt._strip_blocked_tools = _strip_blocked_tools


# ── 子代理重用 ──────────────────────────────────────────────────────────────


def _rehydrate_pooled_subagent(
    child: Any,
    *,
    task_index: int,
    goal: str,
    context: Optional[str],
    toolsets: Optional[List[str]],
    model: Optional[str],
    max_iterations: int,
    task_count: int,
    parent_agent: Any,
    role: str,
) -> None:
    """Update a pooled subagent for a new delegate_task invocation."""
    from tools.delegate_tool import (
        _build_child_progress_callback,
        _build_child_system_prompt,
        _get_max_spawn_depth,
        _get_orchestrator_enabled,
        _normalize_role,
        _resolve_workspace_hint,
    )

    child_depth = getattr(parent_agent, "_delegate_depth", 0) + 1
    max_spawn = _get_max_spawn_depth()
    orchestrator_ok = _get_orchestrator_enabled() and child_depth < max_spawn
    effective_role = (
        role if (role == "orchestrator" and orchestrator_ok) else "leaf"
    )
    subagent_id = f"sa-{task_index}-{_uuid.uuid4().hex[:8]}"
    parent_subagent_id = getattr(parent_agent, "_subagent_id", None)
    tui_depth = max(0, child_depth - 1)
    workspace_hint = _resolve_workspace_hint(parent_agent)
    child_prompt = _build_child_system_prompt(
        goal,
        context,
        workspace_path=workspace_hint,
        role=effective_role,
        max_spawn_depth=max_spawn,
        child_depth=child_depth,
    )
    effective_model_for_cb = model or getattr(parent_agent, "model", None)
    child_toolsets = list(child.enabled_toolsets or [])
    child_progress_cb = _build_child_progress_callback(
        task_index,
        goal,
        parent_agent,
        task_count,
        subagent_id=subagent_id,
        parent_id=parent_subagent_id,
        depth=tui_depth,
        model=effective_model_for_cb,
        toolsets=child_toolsets,
    )
    child_thinking_cb = None
    if child_progress_cb:

        def _child_thinking(text: str) -> None:
            if not text:
                return
            try:
                child_progress_cb("_thinking", text)
            except Exception:
                pass

        child_thinking_cb = _child_thinking

    child.ephemeral_system_prompt = child_prompt
    child.tool_progress_callback = child_progress_cb
    child.thinking_callback = child_thinking_cb
    child.max_iterations = max_iterations
    child._delegate_depth = child_depth
    child._delegate_role = effective_role
    child._subagent_id = subagent_id
    child._parent_subagent_id = parent_subagent_id
    child._subagent_goal = goal
    child._interrupt_requested = False
    child._interrupt_message = None
    child._cached_system_prompt = None
    try:
        from tools.todo_tool import TodoStore

        child._todo_store = TodoStore()
    except Exception:
        pass
    if getattr(child, "_memory_store", None):
        try:
            child._memory_store.load_from_disk()
        except Exception:
            pass
    try:
        child.reset_session_state()
    except Exception:
        pass

    if child_progress_cb:
        try:
            child_progress_cb("subagent.spawn_requested", preview=goal)
        except Exception:
            pass

    if hasattr(parent_agent, "_active_children"):
        lock = getattr(parent_agent, "_active_children_lock", None)
        try:
            if lock:
                with lock:
                    if child not in parent_agent._active_children:
                        parent_agent._active_children.append(child)
            elif child not in parent_agent._active_children:
                parent_agent._active_children.append(child)
        except Exception:
            pass


def patch_build_child_agent() -> None:
    """拦截 ``_build_child_agent``：优先从复用池取实例子代理。"""
    import inspect

    import tools.delegate_tool as dt

    if getattr(dt._build_child_agent, "_hds_wrapped", False):
        return
    orig = dt._build_child_agent
    sig = inspect.signature(orig)

    def _wrapped(*a, **kw):
        bound = sig.bind(*a, **kw)
        bound.apply_defaults()
        p = bound.arguments
        parent_agent = p["parent_agent"]
        task_index = int(p["task_index"])
        key = (getattr(parent_agent, "session_id", None) or "", task_index)

        if _reuse_enabled() and key in _SUBAGENT_POOL:
            child = _SUBAGENT_POOL.pop(key)
            _rehydrate_pooled_subagent(
                child,
                task_index=task_index,
                goal=p["goal"],
                context=p.get("context"),
                toolsets=p.get("toolsets"),
                model=p.get("model"),
                max_iterations=int(p.get("max_iterations") or 50),
                task_count=int(p.get("task_count") or 1),
                parent_agent=parent_agent,
                role=str(p.get("role") or "leaf"),
            )
            setattr(child, "_hds_reuse_instance", True)
            setattr(child, "_hds_reuse_pool_key", key)
            attach_subagent_memory(child, parent_agent)
            return child

        child = orig(*a, **kw)
        setattr(child, "_hds_reuse_instance", _reuse_enabled())
        setattr(child, "_hds_reuse_pool_key", key)
        attach_subagent_memory(child, parent_agent)
        return child

    _wrapped._hds_wrapped = True  # type: ignore[attr-defined]
    dt._build_child_agent = _wrapped


def patch_run_single_child() -> None:
    """拦截 ``_run_single_child``：子代理运行结束后回收到复用池。"""
    import tools.delegate_tool as dt

    if getattr(dt._run_single_child, "_hds_wrapped", False):
        return
    orig = dt._run_single_child

    def _wrapped(*a, **kw):
        child = kw.get("child") if "child" in kw else (a[2] if len(a) > 2 else None)
        task_index = kw.get("task_index") if "task_index" in kw else (a[0] if a else 0)
        parent_agent = kw.get("parent_agent") if "parent_agent" in kw else (
            a[3] if len(a) > 3 else None
        )
        try:
            return orig(*a, **kw)
        finally:
            if (
                _reuse_enabled()
                and child is not None
                and getattr(child, "_hds_reuse_instance", False)
            ):
                key = getattr(child, "_hds_reuse_pool_key", None)
                if key is not None:
                    _SUBAGENT_POOL[key] = child

    _wrapped._hds_wrapped = True  # type: ignore[attr-defined]
    dt._run_single_child = _wrapped
