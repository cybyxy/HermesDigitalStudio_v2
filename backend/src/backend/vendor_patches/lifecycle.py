"""AIAgent 生命周期 monkeypatch：线程追踪、资源防泄、上下文压缩事件。

- ``_patch_aiagent_run_conversation``: 追踪当前运行 run_conversation 的 AIAgent
- ``_patch_invoke_tool``: 追踪当前执行工具调用的 AIAgent
- ``_patch_aiagent_close``: 防止复用中的子代理被 vendor close() 销毁
- ``_patch_compress_context``: 上下文压缩时发出 session.switch JSON-RPC 事件
"""

from __future__ import annotations

import json as _json
import logging
import sys as _sys

from backend.vendor_patches._common import (
    _log,
    _run_tls,
    _tool_tls,
    _reuse_enabled,
)

_log = logging.getLogger(__name__)


def patch_aiagent_run_conversation() -> None:
    """追踪 run_conversation 执行，将当前 AIAgent 存入线程本地存储。"""
    from run_agent import AIAgent

    if getattr(AIAgent.run_conversation, "_hds_wrapped", False):
        return
    orig = AIAgent.run_conversation

    def _wrapped(self, *a, **kw):
        prev = getattr(_run_tls, "active_agent", None)
        _run_tls.active_agent = self
        try:
            return orig(self, *a, **kw)
        finally:
            _run_tls.active_agent = prev

    _wrapped._hds_wrapped = True  # type: ignore[attr-defined]
    AIAgent.run_conversation = _wrapped


def patch_invoke_tool() -> None:
    """追踪工具调用执行，将当前 AIAgent 存入线程本地存储。"""
    from run_agent import AIAgent

    if getattr(AIAgent._invoke_tool, "_hds_wrapped", False):
        return
    orig = AIAgent._invoke_tool

    def _wrapped(self, *a, **kw):
        prev = getattr(_tool_tls, "agent", None)
        _tool_tls.agent = self
        try:
            return orig(self, *a, **kw)
        finally:
            _tool_tls.agent = prev

    _wrapped._hds_wrapped = True  # type: ignore[attr-defined]
    AIAgent._invoke_tool = _wrapped


def patch_aiagent_close() -> None:
    """防止复用池中的子代理被 vendor close() 销毁。

    子代理实例在 delegate_task 完成后会被回收到 _SUBAGENT_POOL，
    vendor 的 close() 在复用模式下会误销毁这些实例，此处拦截跳过。
    """
    from run_agent import AIAgent

    if getattr(AIAgent.close, "_hds_wrapped", False):
        return
    orig = AIAgent.close

    def _wrapped(self) -> None:
        if (
            _reuse_enabled()
            and getattr(self, "_hds_reuse_instance", False)
            and getattr(self, "_delegate_depth", 0) > 0
        ):
            return
        return orig(self)

    _wrapped._hds_wrapped = True  # type: ignore[attr-defined]
    AIAgent.close = _wrapped


def patch_compress_context() -> None:
    """Monkeypatch AIAgent._compress_context 以发出 session.switch event。

    不修改 vendor 代码，通过子进程 bootstrap 中已注入的此模块在运行时动态拦截。
    vendor 的压缩行为完全不变，仅在其完成后附加事件打印。
    """
    from run_agent import AIAgent

    if getattr(AIAgent._compress_context, "_hds_wrapped", False):
        return
    orig = AIAgent._compress_context

    def _wrapped(self, messages, system_message, *,
                 approx_tokens=None, task_id="default", focus_topic=None):
        old_session_id = getattr(self, "session_id", None)
        result = orig(self, messages, system_message,
                      approx_tokens=approx_tokens, task_id=task_id,
                      focus_topic=focus_topic)
        new_session_id = getattr(self, "session_id", None)

        if old_session_id and new_session_id and old_session_id != new_session_id:
            event = _json.dumps({
                "jsonrpc": "2.0",
                "method": "event",
                "params": {
                    "type": "session.switch",
                    "session_id": old_session_id,
                    "payload": {
                        "old_session_id": old_session_id,
                        "new_session_id": new_session_id,
                    }
                }
            }, ensure_ascii=False)
            print(event, file=_sys.stdout, flush=True)

        return result

    _wrapped._hds_wrapped = True  # type: ignore[attr-defined]
    AIAgent._compress_context = _wrapped
    _log.info("hermes_subagent_ext: _compress_context monkeypatched for session.switch event")
