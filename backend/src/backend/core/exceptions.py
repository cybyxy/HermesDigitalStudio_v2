"""统一异常层级 — 所有业务异常由此抛出，由 ``error_handlers.py`` 统一转换为 HTTP 响应。

使用方式::

    from backend.core.exceptions import AgentNotFoundError
    raise AgentNotFoundError(agent_id="studio_agent_0")

前端收到的统一错误格式::

    {"detail": "...", "error": "AgentNotFoundError"}
"""

from __future__ import annotations


class StudioError(Exception):
    """所有业务异常的基类。

    :param detail: 人类可读的错误消息（中文或英文均可）
    :param status_code: HTTP 状态码
    """

    def __init__(self, detail: str = "", *, status_code: int = 500) -> None:
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code


class AgentNotFoundError(StudioError):
    """指定的 Agent 不存在。"""

    def __init__(self, agent_id: str = "") -> None:
        detail = f"Agent 不存在: {agent_id}" if agent_id else "Agent 不存在"
        super().__init__(detail, status_code=404)


class AgentAlreadyExistsError(StudioError):
    """同名 Agent 已存在。"""

    def __init__(self, profile: str = "") -> None:
        detail = f"Agent profile '{profile}' 已存在" if profile else "Agent 已存在"
        super().__init__(detail, status_code=409)


class ProfileNotFoundError(StudioError):
    """指定的 Profile 不存在。"""

    def __init__(self, profile: str = "") -> None:
        detail = f"Profile 不存在: {profile}" if profile else "Profile 不存在"
        super().__init__(detail, status_code=404)


class SessionNotFoundError(StudioError):
    """指定的会话不存在。"""

    def __init__(self, session_id: str = "") -> None:
        detail = f"会话不存在: {session_id}" if session_id else "会话不存在"
        super().__init__(detail, status_code=404)


class ConfigError(StudioError):
    """配置读取/写入错误。"""

    def __init__(self, detail: str = "配置操作失败") -> None:
        super().__init__(detail, status_code=500)


class GatewayError(StudioError):
    """Agent 子进程网关通信异常。"""

    def __init__(self, detail: str = "网关服务异常") -> None:
        super().__init__(detail, status_code=503)


class DatabaseError(StudioError):
    """数据库操作异常。"""

    def __init__(self, detail: str = "数据库操作失败") -> None:
        super().__init__(detail, status_code=500)


class ValidationError(StudioError):
    """参数校验失败。"""

    def __init__(self, detail: str = "参数校验失败") -> None:
        super().__init__(detail, status_code=422)


class PlanChainError(StudioError):
    """规划链执行异常。"""

    def __init__(self, detail: str = "规划链执行异常") -> None:
        super().__init__(detail, status_code=409)


class SkillNotFoundError(StudioError):
    """指定的技能不存在。"""

    def __init__(self, skill_path: str = "") -> None:
        detail = f"SKILL.md 未找到: {skill_path}" if skill_path else "SKILL.md 未找到"
        super().__init__(detail, status_code=404)
