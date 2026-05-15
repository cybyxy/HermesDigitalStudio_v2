"""测试 StudioConfig 配置解析。"""
from __future__ import annotations

from pathlib import Path

import pytest

from backend.core.config import StudioConfig


class TestStudioConfig:
    """StudioConfig 默认值测试（在 _isolate_config_env fixture 保护下）。"""

    def test_hermes_home_default(self):
        cfg = StudioConfig()
        home = cfg.hermes_home
        assert home.is_dir()
        assert home.name.startswith("test_hermes_home_")

    def test_hermes_home_from_env(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
        monkeypatch.setenv("HERMES_HOME", str(tmp_path / "my_hermes"))
        cfg = StudioConfig()
        assert cfg.hermes_home == tmp_path / "my_hermes"

    def test_studio_data_dir_from_env(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
        data = tmp_path / "custom_data"
        monkeypatch.setenv("HERMES_STUDIO_DATA_DIR", str(data))
        cfg = StudioConfig()
        assert cfg.studio_data_dir == data
        assert data.is_dir()

    def test_db_path(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
        data = tmp_path / "mydata"
        monkeypatch.setenv("HERMES_STUDIO_DATA_DIR", str(data))
        cfg = StudioConfig()
        assert cfg.db_path == data / "HermesDigitalStudio.db"

    def test_port_default(self):
        cfg = StudioConfig()
        assert cfg.port == 9120

    def test_port_from_env(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("STUDIO_BACKEND_PORT", raising=False)
        monkeypatch.setenv("PORT", "8080")
        cfg = StudioConfig()
        assert cfg.port == 8080

    def test_port_from_studio_env(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("PORT", raising=False)
        monkeypatch.setenv("STUDIO_BACKEND_PORT", "9999")
        cfg = StudioConfig()
        assert cfg.port == 9999

    def test_port_priority(self, monkeypatch: pytest.MonkeyPatch):
        """PORT 优先于 STUDIO_BACKEND_PORT（`PORT or STUDIO_BACKEND_PORT`）。"""
        monkeypatch.setenv("PORT", "8080")
        monkeypatch.setenv("STUDIO_BACKEND_PORT", "9999")
        cfg = StudioConfig()
        assert cfg.port == 8080

    def test_gateway_ingest_url_default(self):
        cfg = StudioConfig()
        assert cfg.gateway_ingest_url == ""

    def test_gateway_ingest_url_custom(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("HERMES_STUDIO_GATEWAY_INGEST_URL", "http://example.com/ingest")
        cfg = StudioConfig()
        assert cfg.gateway_ingest_url == "http://example.com/ingest"

    def test_no_embedded_gateway_disabled(self, monkeypatch: pytest.MonkeyPatch):
        """未设置 HERMES_STUDIO_NO_EMBEDDED_GATEWAY 时应为 False。"""
        monkeypatch.delenv("HERMES_STUDIO_NO_EMBEDDED_GATEWAY", raising=False)
        cfg = StudioConfig()
        assert cfg.no_embedded_gateway is False

    @pytest.mark.parametrize("val", ["1", "true", "yes", "on", "TRUE", "YES"])
    def test_no_embedded_gateway_enabled(self, monkeypatch: pytest.MonkeyPatch, val: str):
        monkeypatch.setenv("HERMES_STUDIO_NO_EMBEDDED_GATEWAY", val)
        cfg = StudioConfig()
        assert cfg.no_embedded_gateway is True

    def test_no_embedded_gateway_zero_disabled(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("HERMES_STUDIO_NO_EMBEDDED_GATEWAY", "0")
        cfg = StudioConfig()
        assert cfg.no_embedded_gateway is False

    def test_gateway_python_default(self):
        cfg = StudioConfig()
        assert cfg.gateway_python == ""

    def test_frozen_instance(self):
        cfg = StudioConfig()
        with pytest.raises(Exception):
            cfg.port = 1234  # type: ignore[misc]
