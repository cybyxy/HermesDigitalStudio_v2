"""设计令牌系统 — 可配置的系统级常量。

集中管理分页、超时、限流等"魔法数字"，避免散落在各模块中。
所有值可通过 ``backend/studio.yaml`` → ``tuning:`` 段配置，
也可通过环境变量覆盖（向后兼容）。

使用方式::

    from backend.core import design_tokens as dt
    page_size = dt.PAGE_SIZE_DEFAULT
    timeout = dt.SSE_TIMEOUT_SECONDS
"""

from __future__ import annotations

# ── 分页 ──────────────────────────────────────────────────────────────────────

PAGE_SIZE_DEFAULT: int = 10
"""默认每页条数。"""

PAGE_SIZE_MIN: int = 1
"""最小每页条数。"""

PAGE_SIZE_MAX: int = 200
"""最大每页条数（防止超大分页拖垮性能）。"""


def clamp_page_size(requested: int) -> int:
    """将请求的 page_size 限制在 [PAGE_SIZE_MIN, PAGE_SIZE_MAX] 范围内。"""
    return max(PAGE_SIZE_MIN, min(requested, PAGE_SIZE_MAX))


def clamp_page_number(requested: int) -> int:
    """确保 page 号 >= 1。"""
    return max(1, requested)


def to_offset(page: int, size: int) -> int:
    """将分页参数转为 SQL OFFSET。"""
    return (clamp_page_number(page) - 1) * clamp_page_size(size)


# ── 超时 ──────────────────────────────────────────────────────────────────────

SSE_TIMEOUT_SECONDS: float = 300.0
"""SSE 流式响应的默认超时（秒）。"""

CHAT_TIMEOUT_SECONDS: float = 600.0
"""聊天请求的默认超时（秒）。"""

PLAN_STEP_TIMEOUT_SECONDS: float = 300.0
"""单步计划任务的默认超时（秒）。"""

ORCHESTRATED_TIMEOUT_SECONDS: float = 900.0
"""多 Agent 编排的默认超时（秒）。"""

DB_BUSY_TIMEOUT_MS: int = 5000
"""SQLite 写锁等待超时（毫秒）。"""

DB_HEALTH_CHECK_INTERVAL_S: int = 120
"""DB 连接健康检查间隔（秒）。"""

# ── 请求限制 ──────────────────────────────────────────────────────────────────

MAX_TEXT_LENGTH: int = 128_000
"""提交 prompt 的最大文本长度（字符数）。"""

MAX_SESSION_NAME_LENGTH: int = 256
"""Session 名称最大长度。"""

MAX_AGENT_PROFILE_LENGTH: int = 64
"""Agent profile 名称最大长度。"""

MAX_CHANNELS_PER_TYPE: int = 10
"""每种消息平台的渠道数量上限。"""

# ── 会话 ──────────────────────────────────────────────────────────────────────

DEFAULT_SESSION_COLS: int = 120
"""新 session 的默认终端列宽。"""

SESSION_CHAIN_MAX_DEPTH: int = 10
"""Session 链查询最大回溯深度。"""

# ── Agent 生命周期 ────────────────────────────────────────────────────────────

AGENT_STARTUP_TIMEOUT_SECONDS: float = 30.0
"""Agent 子进程启动的最大等待时间（秒）。"""

AGENT_SHUTDOWN_TIMEOUT_SECONDS: float = 10.0
"""Agent 子进程关闭的最大等待时间（秒）。"""

# ── 限流 ──────────────────────────────────────────────────────────────────────

RATE_LIMIT_WINDOW_SECONDS: int = 60
"""限流时间窗口（秒）。"""

RATE_LIMIT_MAX_REQUESTS: int = 120
"""限流窗口内最大请求数。"""

# ── 国际化 ────────────────────────────────────────────────────────────────────

DEFAULT_LOCALE: str = "zh"
"""默认语言区域（zh / en）。"""

DEFAULT_TIMEZONE: str = "Asia/Shanghai"
"""默认时区。"""


# ── 配置注入 ──────────────────────────────────────────────────────────────
# 在首次 import 后由 backend.core.config 调用，将 studio.yaml 中的值覆盖到模块常量上。

_OVERRIDDEN = False


def _apply_studio_overrides() -> None:
    """用 studio.yaml 的值覆盖模块级常量（仅在首次调用时执行）。"""
    global _OVERRIDDEN, \
        PAGE_SIZE_DEFAULT, PAGE_SIZE_MIN, PAGE_SIZE_MAX, \
        SSE_TIMEOUT_SECONDS, CHAT_TIMEOUT_SECONDS, PLAN_STEP_TIMEOUT_SECONDS, \
        ORCHESTRATED_TIMEOUT_SECONDS, DB_BUSY_TIMEOUT_MS, DB_HEALTH_CHECK_INTERVAL_S, \
        MAX_TEXT_LENGTH, MAX_SESSION_NAME_LENGTH, MAX_AGENT_PROFILE_LENGTH, \
        MAX_CHANNELS_PER_TYPE, DEFAULT_SESSION_COLS, SESSION_CHAIN_MAX_DEPTH, \
        AGENT_STARTUP_TIMEOUT_SECONDS, AGENT_SHUTDOWN_TIMEOUT_SECONDS, \
        RATE_LIMIT_WINDOW_SECONDS, RATE_LIMIT_MAX_REQUESTS, \
        DEFAULT_LOCALE, DEFAULT_TIMEZONE

    if _OVERRIDDEN:
        return
    _OVERRIDDEN = True

    try:
        from backend.core.config import get_config
        cfg = get_config()

        PAGE_SIZE_DEFAULT = int(cfg.get_tuning("page_size_default"))
        PAGE_SIZE_MIN = int(cfg.get_tuning("page_size_min"))
        PAGE_SIZE_MAX = int(cfg.get_tuning("page_size_max"))
        SSE_TIMEOUT_SECONDS = float(cfg.get_tuning("sse_timeout"))
        CHAT_TIMEOUT_SECONDS = float(cfg.get_tuning("chat_timeout"))
        PLAN_STEP_TIMEOUT_SECONDS = float(cfg.get_tuning("plan_step_timeout"))
        ORCHESTRATED_TIMEOUT_SECONDS = float(cfg.get_tuning("orchestrated_timeout"))
        DB_BUSY_TIMEOUT_MS = int(cfg.get_tuning("db_busy_timeout_ms"))
        DB_HEALTH_CHECK_INTERVAL_S = int(cfg.get_tuning("db_health_check_interval_s"))
        MAX_TEXT_LENGTH = int(cfg.get_tuning("max_text_length"))
        MAX_SESSION_NAME_LENGTH = int(cfg.get_tuning("max_session_name_length"))
        MAX_AGENT_PROFILE_LENGTH = int(cfg.get_tuning("max_agent_profile_length"))
        MAX_CHANNELS_PER_TYPE = int(cfg.get_tuning("max_channels_per_type"))
        DEFAULT_SESSION_COLS = int(cfg.get_tuning("default_session_cols"))
        SESSION_CHAIN_MAX_DEPTH = int(cfg.get_tuning("session_chain_max_depth"))
        AGENT_STARTUP_TIMEOUT_SECONDS = float(cfg.get_tuning("agent_startup_timeout"))
        AGENT_SHUTDOWN_TIMEOUT_SECONDS = float(cfg.get_tuning("agent_shutdown_timeout"))
        RATE_LIMIT_WINDOW_SECONDS = int(cfg.get_tuning("rate_limit_window"))
        RATE_LIMIT_MAX_REQUESTS = int(cfg.get_tuning("rate_limit_max"))
        DEFAULT_LOCALE = cfg.ui_locale
        DEFAULT_TIMEZONE = cfg.ui_timezone
    except Exception:
        pass  # 保持默认值
