"""测试全局异常处理器返回正确的 HTTP 响应。"""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.core.error_handlers import register_error_handlers
from backend.core.exceptions import (
    AgentNotFoundError,
    ConfigError,
    GatewayError,
    SessionNotFoundError,
    ValidationError,
)


@pytest.fixture
def error_test_app() -> FastAPI:
    """创建一个只注册了异常处理器的最小 FastAPI 应用。"""
    app = FastAPI()
    register_error_handlers(app)

    @app.get("/raise/{exc_name}")
    def raise_exception(exc_name: str):
        exc_map = {
            "agent_not_found": AgentNotFoundError("a0"),
            "session_not_found": SessionNotFoundError("s0"),
            "config": ConfigError("bad config"),
            "gateway": GatewayError("timeout"),
            "validation": ValidationError("missing field"),
            "runtime": Exception("boom"),
        }
        raise exc_map[exc_name]

    return app


@pytest.fixture
def error_client(error_test_app: FastAPI) -> TestClient:
    # raise_server_exceptions=False 让异常处理器正常工作
    return TestClient(error_test_app, raise_server_exceptions=False)


class TestErrorHandlers:
    def test_agent_not_found_returns_404(self, error_client: TestClient):
        resp = error_client.get("/raise/agent_not_found")
        assert resp.status_code == 404
        data = resp.json()
        assert data["error"] == "AgentNotFoundError"
        assert "a0" in data["detail"]

    def test_session_not_found_returns_404(self, error_client: TestClient):
        resp = error_client.get("/raise/session_not_found")
        assert resp.status_code == 404
        assert resp.json()["error"] == "SessionNotFoundError"

    def test_config_error_returns_500(self, error_client: TestClient):
        resp = error_client.get("/raise/config")
        assert resp.status_code == 500
        assert resp.json()["error"] == "ConfigError"

    def test_gateway_error_returns_503(self, error_client: TestClient):
        resp = error_client.get("/raise/gateway")
        assert resp.status_code == 503
        assert resp.json()["error"] == "GatewayError"

    def test_validation_error_returns_422(self, error_client: TestClient):
        resp = error_client.get("/raise/validation")
        assert resp.status_code == 422
        assert resp.json()["error"] == "ValidationError"

    def test_unhandled_exception_returns_500(self, error_client: TestClient):
        resp = error_client.get("/raise/runtime")
        assert resp.status_code == 500
        data = resp.json()
        assert data["error"] == "InternalError"
