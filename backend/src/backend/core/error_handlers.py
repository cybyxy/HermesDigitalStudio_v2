"""FastAPI 全局异常处理器 — 将所有业务异常转换为统一 JSON 响应格式。

通过 ``register_error_handlers(app)`` 在 ``create_app()`` 中注册。
"""

from __future__ import annotations

import logging
import traceback

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from backend.core.exceptions import StudioError

_log = logging.getLogger(__name__)


def register_error_handlers(app: FastAPI) -> None:
    """向 FastAPI 应用注册全局异常处理器。"""

    @app.exception_handler(StudioError)
    async def _handle_studio_error(request: Request, exc: StudioError) -> JSONResponse:
        """处理所有 StudioError 子类，返回统一错误格式。"""
        _log.warning(
            "StudioError | %s | %s | %s",
            exc.__class__.__name__,
            exc.detail,
            request.url.path,
        )
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "detail": exc.detail,
                "error": exc.__class__.__name__,
            },
        )

    @app.exception_handler(RequestValidationError)
    async def _handle_validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        """处理 Pydantic 请求校验错误，返回 422。"""
        errors = exc.errors()
        detail = errors[0].get("msg", "请求参数校验失败") if errors else "请求参数校验失败"
        return JSONResponse(
            status_code=422,
            content={
                "detail": detail,
                "error": "RequestValidationError",
            },
        )

    @app.exception_handler(Exception)
    async def _handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        """兜底处理未预期的异常，记录完整 traceback，返回 500。"""
        tb = traceback.format_exc()
        _log.error(
            "Unhandled exception | %s | %s\n%s",
            exc.__class__.__name__,
            request.url.path,
            tb,
        )
        return JSONResponse(
            status_code=500,
            content={
                "detail": "Internal server error",
                "error": "InternalError",
            },
        )
