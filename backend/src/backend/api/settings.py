"""Settings Controller — 对应 Spring Boot @RestController.

仅处理 HTTP 请求/响应、参数校验，调用 service/settings.py 完成业务逻辑。
"""

from __future__ import annotations

import logging

from fastapi import APIRouter

from backend.models.request.settings_requests import SettingsSaveRequest
from backend.services import settings as settings_service

router = APIRouter(prefix="/settings", tags=["settings"])
_log = logging.getLogger(__name__)


@router.get("")
async def get_settings() -> dict:
    """读取完整配置供设置页面展示。"""
    return settings_service.get_settings()


@router.put("")
async def save_settings(body: SettingsSaveRequest) -> dict:
    """保存完整配置。"""
    return settings_service.save_settings(body)


@router.get("/env-vars")
async def get_env_vars() -> dict:
    """读取所有环境变量。"""
    return settings_service.get_env_vars()


@router.put("/env-vars")
async def update_env_var(key: str, value: str) -> dict:
    """更新指定环境变量。"""
    return settings_service.update_env_var(key, value)


@router.delete("/env-vars")
async def delete_env_var(key: str) -> dict:
    """删除指定环境变量。"""
    return settings_service.delete_env_var(key)


@router.get("/check")
async def check_config() -> dict:
    """检查配置状态。"""
    return settings_service.check_config()
