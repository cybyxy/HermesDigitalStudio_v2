"""结构化日志 — JSON 格式 + 请求关联 ID。

通过 contextvars 在异步请求上下文中传播 ``request_id``，
所有日志自动附加 ``request_id`` 字段，便于追踪完整请求链路。

用法::

    import backend.core.logging as logging
    from backend.core.logging import get_logger

    _log = get_logger(__name__)
    _log.info("处理请求", extra={"session_id": "abc"})
"""

from __future__ import annotations

import json
import logging as _stdlib_logging
import sys
import time
import uuid
from contextvars import ContextVar
from typing import Any

_request_id: ContextVar[str] = ContextVar("request_id", default="")

# ── JSON 格式化器 ─────────────────────────────────────────────────────────────

class _JsonFormatter(_stdlib_logging.Formatter):
    """将日志记录格式化为单行 JSON。

    输出字段：
    - timestamp: ISO 8601 毫秒精度
    - level: 日志级别
    - logger: 记录器名称
    - message: 日志消息
    - request_id: 请求关联 ID（若存在）
    - 通过 extra 传递的其他字段
    """

    def format(self, record: _stdlib_logging.LogRecord) -> str:
        ts = time.time()
        obj: dict[str, Any] = {
            "ts": f"{time.strftime('%Y-%m-%dT%H:%M:%S', time.localtime(ts))}.{int((ts % 1) * 1000):03d}",
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }

        rid = _request_id.get("")
        if rid:
            obj["req_id"] = rid

        # 附加 extra 中传递的任意字段
        for key in ("session_id", "agent_id", "plan_id", "error", "detail"):
            val = getattr(record, key, None)
            if val is not None:
                obj[key] = val

        if record.exc_info and record.exc_info[1]:
            obj["exc"] = str(record.exc_info[1])

        return json.dumps(obj, ensure_ascii=False, default=str)


# ── Logger 工厂 ────────────────────────────────────────────────────────────────

def get_logger(name: str) -> _stdlib_logging.Logger:
    """获取配置了 JSON 格式的 logger 实例。"""
    log = _stdlib_logging.getLogger(name)
    return log


# ── 标记是否已初始化（避免重复调用） ────────────────────────────────────────────

_setup_done = False


def setup(structured: bool = True) -> None:
    """初始化 backend.* 结构化日志配置（幂等）。

    - structured=True: backend.* 输出 JSON 格式到 stderr（生产模式）
    - structured=False: backend.* 输出可读纯文本（开发模式）

    不影响 uvicorn / hermes 等第三方 logger，仅配置 ``backend`` namespace。
    """
    global _setup_done
    if _setup_done:
        return
    _setup_done = True

    backend_log = _stdlib_logging.getLogger("backend")
    backend_log.handlers.clear()
    backend_log.setLevel(_stdlib_logging.INFO)
    backend_log.propagate = False

    if structured:
        handler = _stdlib_logging.StreamHandler(sys.stderr)
        handler.setFormatter(_JsonFormatter())
    else:
        handler = _stdlib_logging.StreamHandler(sys.stderr)
        handler.setFormatter(_stdlib_logging.Formatter(
            "%(levelname)s %(name)s: %(message)s"
        ))
    backend_log.addHandler(handler)


# ── 请求 ID 管理 ──────────────────────────────────────────────────────────────

def set_request_id(rid: str) -> None:
    """设置当前请求上下文的关联 ID。"""
    _request_id.set(rid)


def get_request_id() -> str:
    """获取当前请求上下文的关联 ID。"""
    return _request_id.get() or ""


def generate_request_id() -> str:
    """生成短请求 ID（8 位 hex）。"""
    return uuid.uuid4().hex[:8]
