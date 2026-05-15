"""集成测试 — 健康检查和基础 API 可用性。"""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api.health import router as health_router
from backend.core.error_handlers import register_error_handlers


@pytest.fixture
def test_app() -> FastAPI:
    app = FastAPI()
    register_error_handlers(app)
    app.include_router(health_router)
    return app


@pytest.fixture
def client(test_app: FastAPI) -> TestClient:
    return TestClient(test_app)


class TestHealthEndpoint:
    def test_health_returns_200(self, client: TestClient):
        resp = client.get("/health")
        assert resp.status_code == 200

    def test_health_returns_json(self, client: TestClient):
        resp = client.get("/health")
        assert resp.headers.get("content-type", "").startswith("application/json")


class TestCorsHeaders:
    def test_options_request(self, test_app: FastAPI):
        """确认 FastAPI test client 可以处理 preflight（无需真实 CORS 中间件）。"""
        client = TestClient(test_app)
        resp = client.options("/health")
        # 可能返回 200 或 405，取决于路由配置 — 仅确认不崩溃
        assert resp.status_code in (200, 405)
