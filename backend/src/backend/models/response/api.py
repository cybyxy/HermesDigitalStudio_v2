"""标准 API 响应模型。

定义整个系统使用的统一响应格式：

- ApiResponse[T]: 通用成功/错误响应包装
- PaginatedData[T]: 分页数据容器
- 工厂函数: success() / created() / paginated() / error()

使用示例::

    from backend.models.response import success, paginated

    return success({"agentId": "alice"})
    return paginated(items, page=1, size=10, total=42)
"""

from __future__ import annotations

import time
from typing import Any, Generic, List, Optional, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")

# ── 分页模型 ──────────────────────────────────────────────────────────────────


class PaginationMeta(BaseModel):
    """分页元信息。"""

    page: int = Field(1, ge=1, description="当前页码 (1-based)")
    size: int = Field(10, ge=1, le=200, description="每页条数")
    total: int = Field(0, ge=0, description="总条数")
    pages: int = Field(0, ge=0, description="总页数")


class PaginatedData(BaseModel, Generic[T]):
    """分页数据容器。"""

    list: List[T] = Field(default_factory=list, description="当前页数据列表")
    pagination: PaginationMeta = Field(default_factory=PaginationMeta)


# ── 字段错误 ──────────────────────────────────────────────────────────────────


class FieldError(BaseModel):
    """单个字段验证错误。"""

    field: str = Field("", description="出错字段名")
    msg: str = Field("", description="错误描述")


# ── 统一响应包装 ──────────────────────────────────────────────────────────────


class ApiResponse(BaseModel, Generic[T]):
    """标准 API 响应包装。

    成功: {"code": 200, "message": "success", "data": {...}, "timestamp": ...}
    错误: {"code": 4xx, "message": "...", "data": null, "errors": [...], "timestamp": ...}
    """

    code: int = Field(200, ge=100, le=599, description="业务状态码")
    message: str = Field("success", description="提示信息")
    data: Optional[T] = Field(None, description="业务数据")
    timestamp: int = Field(
        default_factory=lambda: int(time.time() * 1000),
        description="响应时间戳 (ms)",
    )
    errors: Optional[List[FieldError]] = Field(None, description="字段级错误")


# ── 快捷工厂函数 ──────────────────────────────────────────────────────────────


def success(data: Any = None) -> dict:
    """构建成功响应 (HTTP 200)。"""
    return ApiResponse(code=200, message="success", data=data).model_dump()


def created(data: Any = None) -> dict:
    """构建创建成功响应 (HTTP 201)。"""
    return ApiResponse(code=201, message="created", data=data).model_dump()


def paginated(
    items: list,
    page: int = 1,
    size: int = 10,
    total: int = 0,
) -> dict:
    """构建分页响应。"""
    pages = max(1, (total + size - 1) // size) if total > 0 else 0
    meta = PaginationMeta(page=page, size=size, total=total, pages=pages)
    return ApiResponse(
        code=200,
        message="success",
        data=PaginatedData(list=items, pagination=meta).model_dump(),
    ).model_dump()


def error(
    code: int = 400,
    message: str = "请求错误",
    errors: Optional[List[FieldError]] = None,
) -> dict:
    """构建错误响应。"""
    return ApiResponse(
        code=code,
        message=message,
        data=None,
        errors=errors or [],
    ).model_dump()
