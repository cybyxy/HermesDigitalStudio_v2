"""测试 Chat 服务层（通过 sys.modules 预置 mock）。"""
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
    mock_db.list_all_sessions.return_value = []
    mock_db.get_personality.return_value = {}
    mock_db.get_agent_model.return_value = None
    mock_db.set_active_agent_session.return_value = None

    orig = sys.modules.get("backend.services.agent_db")
    sys.modules["backend.services.agent_db"] = mock_db
    yield
    if orig is not None:
        sys.modules["backend.services.agent_db"] = orig
    else:
        sys.modules.pop("backend.services.agent_db", None)


class TestSessionCreation:
    @pytest.mark.xfail(
        reason="create_session() accesses info.gateway.create_session_with_key; "
               "needs Phase 1-A2 GatewayManager refactor"
    )
    def test_create_session(self, monkeypatch: pytest.MonkeyPatch):
        from backend.services import chat as chat_service

        mock_mgr = MagicMock()
        mock_mgr.create_session.return_value = {"sessionId": "sess_test_0"}
        mock_mgr.register_session.return_value = None

        monkeypatch.setattr("backend.services.agent._get_manager", lambda: mock_mgr)

        result = chat_service.create_session("test_agent_0", cols=80)
        assert isinstance(result, dict)


class TestGetLastActiveSession:
    def test_no_sessions(self):
        from backend.services import chat as chat_service

        result = chat_service.get_last_active_session()
        assert result["session"] is None
        assert result["restored"] is False
