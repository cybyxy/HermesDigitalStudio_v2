"""API 响应包装中间件 — 将所有 JSON 响应包装为统一格式。

Middleware should run AFTER error handlers so that exceptions are already converted
to JSON responses before we wrap them.
"""

from __future__ import annotations

import json
import logging

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response, StreamingResponse

_log = logging.getLogger(__name__)

# URL prefixes to skip wrapping (don't touch SSE, WebSocket, static files)
_SKIP_URL_PREFIXES = (
    "/api/chat/sse",
    "/api/chat/orchestrated/stream",
    "/api/chat/gateway-bridge/sse",
    "/api/chat/heartbeat/sse",
    "/api/stt",
    "/api/media",
    "/assets",
)

# Content types that indicate streaming or non-JSON responses
_SKIP_CONTENT_TYPES = (
    "text/event-stream",
    "application/octet-stream",
    "multipart",
)

# Response wrapper keys (used to detect already-wrapped responses)
_WRAPPER_KEYS = {"code", "message", "data", "timestamp"}


def _looks_already_wrapped(body: dict) -> bool:
    """Check if a response body already uses the unified format."""
    return _WRAPPER_KEYS.issubset(body.keys())


class ApiResponseMiddleware(BaseHTTPMiddleware):
    """Wraps all JSON API responses in the unified format."""

    async def dispatch(self, request: Request, call_next):
        # Skip SSE / streaming endpoints completely
        path = request.url.path
        if any(path.startswith(prefix) for prefix in _SKIP_URL_PREFIXES):
            return await call_next(request)

        response: Response = await call_next(request)

        # Skip streaming responses
        if isinstance(response, StreamingResponse):
            return response

        # Skip non-JSON content types
        content_type = response.headers.get("content-type", "")
        if any(skip in content_type for skip in _SKIP_CONTENT_TYPES):
            return response

        # Only wrap JSON responses
        if "application/json" not in content_type:
            return response

        try:
            original_body: bytes = response.body  # type: ignore[attr-defined]
            if not original_body:
                return response

            body_str = original_body.decode("utf-8")
            original = json.loads(body_str)
        except (json.JSONDecodeError, UnicodeDecodeError, AttributeError):
            return response

        # Don't double-wrap
        if isinstance(original, dict) and _looks_already_wrapped(original):
            return response

        # Build unified wrapper
        import time

        status_code = response.status_code
        is_success = 200 <= status_code < 300

        if is_success:
            # 成功响应: 把整个原始 JSON 作为 data
            wrapped = {
                "code": status_code,
                "message": "success",
                "data": original,
                "timestamp": int(time.time() * 1000),
            }
        else:
            # 错误响应: 原始内容通常包含 detail 等
            error_message = "请求错误"
            if isinstance(original, dict):
                error_message = str(original.get("detail", original.get("message", error_message)))

            wrapped = {
                "code": status_code,
                "message": error_message,
                "data": None,
                "timestamp": int(time.time() * 1000),
            }

        wrapped_bytes = json.dumps(wrapped, ensure_ascii=False).encode("utf-8")
        return Response(
            content=wrapped_bytes,
            status_code=status_code,
            headers=dict(response.headers),
            media_type="application/json",
        )


def _patch_http_exception():
    """Monkey-patch FastAPI's HTTPException handler to produce unified error format.

    This ensures even framework-raised exceptions (validation errors, 404s, etc.)
    produce the standard response format.
    """
    import time
    from fastapi import FastAPI
    from fastapi.exceptions import RequestValidationError
    from starlette.exceptions import HTTPException as StarletteHTTPException
    from starlette.responses import JSONResponse

    # Can't import FastAPI here without creating circular deps.
    # The register function is called from main.py after app creation.


def register_api_response_middleware(app):
    """Register the middleware and error handlers for unified responses."""
    from fastapi.exceptions import RequestValidationError
    from starlette.exceptions import HTTPException as StarletteHTTPException
    from starlette.responses import JSONResponse
    import time

    app.add_middleware(ApiResponseMiddleware)

    # Override error handlers for consistent format
    async def unified_http_exception_handler(request: Request, exc: StarletteHTTPException):
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "code": exc.status_code,
                "message": str(exc.detail) if exc.detail else "请求错误",
                "data": None,
                "timestamp": int(time.time() * 1000),
            },
        )

    async def unified_validation_exception_handler(request: Request, exc: RequestValidationError):
        errors = []
        for e in exc.errors():
            field = " -> ".join(str(loc) for loc in e.get("loc", []))
            errors.append({"field": field, "msg": e.get("msg", "验证错误")})
        return JSONResponse(
            status_code=422,
            content={
                "code": 422,
                "message": "参数验证失败",
                "data": None,
                "timestamp": int(time.time() * 1000),
                "errors": errors,
            },
        )

    app.add_exception_handler(StarletteHTTPException, unified_http_exception_handler)
    app.add_exception_handler(RequestValidationError, unified_validation_exception_handler)
