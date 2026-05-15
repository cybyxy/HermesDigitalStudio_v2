"""测试 Agent 服务层（通过 sys.modules 预置 mock）。"""
from __future__ import annotations

import sys
from unittest.mock import MagicMock

import pytest


@pytest.fixture(autouse=True)
def _mock_agent_db():
    mock_db = MagicMock()
    mock_db.get_avatar.return_value = None
    mock_db.get_gender.return_value = "male"
    mock_db.get_office_pose.return_value = (0, 0)
    mock_db.list_agent_sessions.return_value = []
    mock_db.get_personality.return_value = {}
    mock_db.get_agent_model.return_value = None
    mock_db.list_all_sessions.return_value = []

    orig = sys.modules.get("backend.services.agent_db")
    sys.modules["backend.services.agent_db"] = mock_db
    yield
    if orig is not None:
        sys.modules["backend.services.agent_db"] = orig
    else:
        sys.modules.pop("backend.services.agent_db", None)


@pytest.fixture(autouse=True)
def _mock_soul_md():
    mock_sm = MagicMock()
    mock_sm.parse_soul_md.return_value = {
        "displayName": "Tester",
        "identity": "test",
        "style": "", "defaults": "", "avoid": "", "coreTruths": "",
    }
    mock_sm.write_soul_md = MagicMock()

    orig = sys.modules.get("backend.services.soul_md")
    sys.modules["backend.services.soul_md"] = mock_sm
    yield
    if orig is not None:
        sys.modules["backend.services.soul_md"] = orig
    else:
        sys.modules.pop("backend.services.soul_md", None)


class TestListAgents:
    def test_returns_empty_list(self, monkeypatch: pytest.MonkeyPatch):
        from backend.services import agent as agent_service

        mock_mgr = MagicMock()
        mock_mgr.list_agents.return_value = []
        monkeypatch.setattr(agent_service, "_get_manager", lambda: mock_mgr)

        result = agent_service.list_agents()
        assert isinstance(result, list)
        assert len(result) == 0

    def test_returns_enriched_agents(self, monkeypatch: pytest.MonkeyPatch):
        from backend.services import agent as agent_service

        mock_mgr = MagicMock()
        mock_mgr.list_agents.return_value = [
            {"agentId": "test_agent_0", "profile": "tester"}
        ]
        monkeypatch.setattr(agent_service, "_get_manager", lambda: mock_mgr)

        result = agent_service.list_agents()
        assert len(result) > 0


class TestGetAgent:
    @pytest.mark.xfail(
        reason="get_agent() accesses info.gateway (AgentInfo namedtuple); "
               "needs Phase 1-A4 refactor to become testable"
    )
    def test_returns_agent_info(self, monkeypatch: pytest.MonkeyPatch):
        from backend.services import agent as agent_service

        mock_mgr = MagicMock()
        mock_mgr.get_agent.return_value = {
            "agentId": "test_agent_0", "profile": "tester"
        }
        mock_mgr.find_agent_by_session.return_value = None
        monkeypatch.setattr(agent_service, "_get_manager", lambda: mock_mgr)

        result = agent_service.get_agent("test_agent_0")
        assert result is not None


class TestCreateAgent:
    @pytest.mark.xfail(
        reason="create_agent() orchestrates 6+ concerns; needs Phase 1-A4 refactor"
    )
    def test_creates_successfully(self, monkeypatch: pytest.MonkeyPatch):
        from backend.services import agent as agent_service

        mock_mgr = MagicMock()
        mock_mgr.create_agent.return_value = {
            "agentId": "test_agent_0", "profile": "new_agent"
        }
        mock_mgr.get_agent.return_value = {
            "agentId": "test_agent_0", "profile": "new_agent"
        }
        monkeypatch.setattr(agent_service, "_get_manager", lambda: mock_mgr)

        result = agent_service.create_agent(
            profile="new_agent",
            display_name="New Agent",
            identity="Helper",
        )
        assert result is not None
