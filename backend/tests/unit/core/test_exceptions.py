"""测试所有 StudioError 子类的 status_code 和 detail。"""
from __future__ import annotations

import pytest

from backend.core.exceptions import (
    AgentAlreadyExistsError,
    AgentNotFoundError,
    ConfigError,
    DatabaseError,
    GatewayError,
    PlanChainError,
    ProfileNotFoundError,
    SessionNotFoundError,
    SkillNotFoundError,
    StudioError,
    ValidationError,
)


class TestStudioError:
    """StudioError 基类测试。"""

    def test_default_status_code_is_500(self):
        err = StudioError("something wrong")
        assert err.status_code == 500
        assert err.detail == "something wrong"
        assert str(err) == "something wrong"

    def test_custom_status_code(self):
        err = StudioError("custom", status_code=418)
        assert err.status_code == 418

    def test_empty_detail(self):
        err = StudioError()
        assert err.detail == ""


class TestAgentNotFoundError:
    def test_with_agent_id(self):
        err = AgentNotFoundError(agent_id="studio_agent_0")
        assert err.status_code == 404
        assert "studio_agent_0" in err.detail

    def test_without_agent_id(self):
        err = AgentNotFoundError()
        assert err.status_code == 404
        assert "不存在" in err.detail


class TestAgentAlreadyExistsError:
    def test_with_profile(self):
        err = AgentAlreadyExistsError(profile="coder")
        assert err.status_code == 409
        assert "coder" in err.detail

    def test_without_profile(self):
        err = AgentAlreadyExistsError()
        assert err.status_code == 409
        assert "已存在" in err.detail


class TestProfileNotFoundError:
    def test_profile_not_found(self):
        err = ProfileNotFoundError(profile="unknown")
        assert err.status_code == 404
        assert "unknown" in err.detail


class TestSessionNotFoundError:
    def test_session_not_found(self):
        err = SessionNotFoundError(session_id="sess_123")
        assert err.status_code == 404
        assert "sess_123" in err.detail

    def test_empty_session_id(self):
        err = SessionNotFoundError()
        assert err.status_code == 404


class TestConfigError:
    def test_default(self):
        err = ConfigError()
        assert err.status_code == 500

    def test_custom(self):
        err = ConfigError("YAML parse error")
        assert err.detail == "YAML parse error"


class TestGatewayError:
    def test_default(self):
        err = GatewayError()
        assert err.status_code == 503

    def test_custom(self):
        err = GatewayError("process died")
        assert err.detail == "process died"


class TestDatabaseError:
    def test_default(self):
        err = DatabaseError()
        assert err.status_code == 500


class TestValidationError:
    def test_default(self):
        err = ValidationError()
        assert err.status_code == 422

    def test_custom(self):
        err = ValidationError("name is required")
        assert err.detail == "name is required"


class TestPlanChainError:
    def test_default(self):
        err = PlanChainError()
        assert err.status_code == 409

    def test_custom(self):
        err = PlanChainError("step 3 timeout")
        assert err.detail == "step 3 timeout"


class TestSkillNotFoundError:
    def test_with_path(self):
        err = SkillNotFoundError(skill_path="my-skill/SKILL.md")
        assert err.status_code == 404
        assert "my-skill/SKILL.md" in err.detail

    def test_without_path(self):
        err = SkillNotFoundError()
        assert err.status_code == 404
        assert "未找到" in err.detail


class TestExceptionInheritance:
    """确保所有 StudioError 子类可以被 StudioError 捕获。"""

    @pytest.mark.parametrize("exc_class", [
        AgentNotFoundError,
        AgentAlreadyExistsError,
        ProfileNotFoundError,
        SessionNotFoundError,
        ConfigError,
        GatewayError,
        DatabaseError,
        ValidationError,
        PlanChainError,
        SkillNotFoundError,
    ])
    def test_is_studio_error(self, exc_class):
        err = exc_class()
        assert isinstance(err, StudioError)
        assert isinstance(err, Exception)

    def test_can_catch_all(self):
        """try/except StudioError 应能捕获所有子类。"""
        caught = []
        for exc_class in [
            AgentNotFoundError("a"),
            ConfigError("b"),
            GatewayError("c"),
        ]:
            try:
                raise exc_class
            except StudioError:
                caught.append(True)
        assert len(caught) == 3
