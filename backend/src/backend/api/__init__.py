"""API 模块：REST 路由层（对应 Spring Boot @RestController）。

路由文件（直接从 api/ 目录导入）：
- health, model, env, settings, agent, chat, plan, skill
"""

from backend.api.health import router as health_router
from backend.api.model import router as model_router, model_crud_router
from backend.api.env import router as env_router
from backend.api.settings import router as settings_router
from backend.api.agent import router as agent_router
from backend.api.chat import router as chat_router
from backend.api.plan import router as plan_router
from backend.api.skill import router as skill_router
from backend.api.channels import router as channel_router
from backend.api.platform_gateway import router as platform_gateway_router
from backend.api.stt import router as stt_router
from backend.api.media import router as media_router
from backend.api.memory import router as memory_router
from backend.api.mind import router as mind_router

__all__ = [
    "health_router",
    "model_router",
    "model_crud_router",
    "env_router",
    "settings_router",
    "agent_router",
    "chat_router",
    "plan_router",
    "skill_router",
    "channel_router",
    "platform_gateway_router",
    "stt_router",
    "media_router",
    "memory_router",
    "mind_router",
]
