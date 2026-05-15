"""Pytest conftest — 全局 fixtures.
"""
from __future__ import annotations

import os
import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def _isolate_config_env(monkeypatch: pytest.MonkeyPatch):
    """每个测试运行在干净的环境变量中。"""
    # 防止本地 ~/.hermes 和 data/ 污染测试
    monkeypatch.setenv("HERMES_HOME", tempfile.mkdtemp(prefix="test_hermes_home_"))
    monkeypatch.setenv("HERMES_STUDIO_DATA_DIR", tempfile.mkdtemp(prefix="test_studio_data_"))
    # 禁用嵌入式消息网关（测试不需要）
    monkeypatch.setenv("HERMES_STUDIO_NO_EMBEDDED_GATEWAY", "1")


@pytest.fixture
def temp_db_path(tmp_path: Path) -> Path:
    """返回一个临时的 SQLite 数据库路径，启动 WAL 模式。"""
    db = tmp_path / "test.db"
    conn = sqlite3.connect(str(db))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.close()
    return db


@pytest.fixture
def temp_db_conn(tmp_path: Path) -> sqlite3.Connection:
    """返回一个已打开并启用 WAL 的临时 SQLite 连接。"""
    db = tmp_path / "test.db"
    conn = sqlite3.connect(str(db))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.row_factory = sqlite3.Row
    return conn


@pytest.fixture
def mock_gateway_manager():
    """返回一个 mock 的 GatewayManager，包含基本桩方法。"""
    mgr = MagicMock()
    mgr.list_agents.return_value = []
    mgr.create_agent.return_value = {"agent_id": "test_agent_0", "profile": "test"}
    mgr.get_agent.return_value = {"agent_id": "test_agent_0", "profile": "test"}
    mgr.close_agent.return_value = None
    mgr.shutdown_all.return_value = None
    mgr.submit_prompt.return_value = {"ok": True}
    mgr.create_session.return_value = {"session_id": "test_session_0"}
    mgr.find_agent_by_session.return_value = "test_agent_0"
    mgr.register_session.return_value = None
    mgr.ensure_default_session.return_value = "test_session_0"
    mgr.session_ids_for_agent.return_value = ["test_session_0"]
    mgr.resume_session.return_value = {"session_id": "test_session_0", "agent_id": "test_agent_0"}
    mgr.get_session_history.return_value = []
    return mgr
