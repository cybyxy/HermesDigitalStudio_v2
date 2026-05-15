"""请求验证工具 — 常用参数校验和清理函数。

提供分页参数解析、字符串清洗、ID 格式验证等可复用工具，
减少路由层分散的重复校验逻辑。

使用示例::

    from backend.core.request_validation import parse_pagination, validate_agent_id

    page, size = parse_pagination(request.page, request.size)
    agent_id = validate_agent_id(raw_id)
"""

from __future__ import annotations

from typing import Optional, Tuple

from backend.core import design_tokens as dt


# ── 分页参数 ─────────────────────────────────────────────────────────────────


def parse_pagination(
    page: Optional[int] = None,
    size: Optional[int] = None,
) -> Tuple[int, int]:
    """解析并清理分页参数，返回 (page, size)。"""
    p = dt.clamp_page_number(page or 1)
    s = dt.clamp_page_size(size or dt.PAGE_SIZE_DEFAULT)
    return p, s


def pagination_defaults() -> Tuple[int, int]:
    """返回默认分页参数 (page=1, size=PAGE_SIZE_DEFAULT)。"""
    return 1, dt.PAGE_SIZE_DEFAULT


# ── ID 验证 ──────────────────────────────────────────────────────────────────


def validate_agent_id(raw: Optional[str]) -> str:
    """验证并清理 Agent ID。

    Raises:
        ValueError: 如果 raw 为空或仅含空白字符。
    """
    if not raw or not raw.strip():
        raise ValueError("Agent ID 不能为空")
    return raw.strip()


def validate_session_id(raw: Optional[str]) -> str:
    """验证并清理 Session ID。

    Raises:
        ValueError: 如果 raw 为空或仅含空白字符。
    """
    if not raw or not raw.strip():
        raise ValueError("Session ID 不能为空")
    return raw.strip()


def validate_plan_id(raw: Optional[int]) -> int:
    """验证 Plan ID 为正整数。

    Raises:
        ValueError: 如果 raw 为 None、≤0 或无效类型。
    """
    if raw is None or raw <= 0:
        raise ValueError(f"Plan ID 无效: {raw}")
    return raw


# ── 字符串清洗 ───────────────────────────────────────────────────────────────


def clean_text(raw: Optional[str], max_len: int = dt.MAX_TEXT_LENGTH) -> str:
    """清洗提交文本：去首尾空白、限制长度。

    Returns:
        清洗后的文本，若输入为 None 返回空字符串。
    """
    if raw is None:
        return ""
    text = raw.strip()
    if len(text) > max_len:
        text = text[:max_len]
    return text


def clean_display_name(raw: Optional[str], fallback: str = "") -> str:
    """清洗显示名称：去空白、限制长度。

    Args:
        raw: 原始输入
        fallback: 清理结果为空时的回退值
    """
    if not raw:
        return fallback
    name = raw.strip()
    if len(name) > dt.MAX_SESSION_NAME_LENGTH:
        name = name[:dt.MAX_SESSION_NAME_LENGTH]
    return name if name else fallback


def clean_profile_name(raw: Optional[str]) -> str:
    """清洗 Agent profile 名称。

    Raises:
        ValueError: 清洗后为空或超过最大长度。
    """
    if not raw or not raw.strip():
        raise ValueError("Profile 名称不能为空")
    name = raw.strip()
    if len(name) > dt.MAX_AGENT_PROFILE_LENGTH:
        raise ValueError(f"Profile 名称过长 (max {dt.MAX_AGENT_PROFILE_LENGTH})")
    return name


# ── SQL 注入防护验证 ─────────────────────────────────────────────────────────


_ILLEGAL_KEY_CHARS = set("\"'`;\\")


def validate_identifier(raw: Optional[str], label: str = "identifier") -> str:
    """验证标识符（表名/列名/排序字段）不含危险字符。

    仅允许字母、数字、下划线、连字符。用于动态 SQL 排序/筛选字段名校验。

    Raises:
        ValueError: 含非法字符或为空。
    """
    if not raw or not raw.strip():
        raise ValueError(f"{label} 不能为空")
    s = raw.strip()
    if any(c in _ILLEGAL_KEY_CHARS or c.isspace() for c in s):
        raise ValueError(f"{label} 包含非法字符: {s!r}")
    return s
