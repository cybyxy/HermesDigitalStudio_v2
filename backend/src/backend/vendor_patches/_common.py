"""Vendor monkeypatch 共享常量和工具函数。

所有 vendor_patches 子模块共享的状态和辅助函数集中于此。
"""

from __future__ import annotations

import logging
import os
import threading
from typing import Any, Dict, Tuple

_log = logging.getLogger("backend.vendor_patches")

# ── 全局状态 ────────────────────────────────────────────────────────────────

_PATCHED = False
"""所有补丁是否已应用（apply_runtime_patches 幂等性标记）。"""

_run_tls = threading.local()
"""线程本地存储：当前正在运行 run_conversation 的 AIAgent 实例。"""

_tool_tls = threading.local()
"""线程本地存储：当前正在执行工具调用的 AIAgent 实例。"""

# (parent_session_id, task_index) -> AIAgent（子代理实例复用池）
_SUBAGENT_POOL: Dict[Tuple[str, int], Any] = {}


# ── 工具函数 ────────────────────────────────────────────────────────────────


def _truthy(name: str, default: bool = False) -> bool:
    """解析 Boolean 类型环境变量。"""
    raw = (os.environ.get(name) or "").strip().lower()
    if not raw:
        return default
    return raw in ("1", "true", "yes", "on")


def _reuse_enabled() -> bool:
    """子代理实例复用是否启用（HERMES_HDS_SUBAGENT_REUSE）。"""
    return _truthy("HERMES_HDS_SUBAGENT_REUSE", False)


def _ext_enabled() -> bool:
    """整个扩展是否禁用（HERMES_HDS_SUBAGENT_EXT_DISABLE）。"""
    return not _truthy("HERMES_HDS_SUBAGENT_EXT_DISABLE", False)


def safe_segment(s: str) -> str:
    """将字符串转换为文件路径安全段（仅保留字母数字、连字符和下划线）。"""
    return "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in (s or ""))[:120]
