"""Env Controller — 环境变量管理。

提供环境变量的读取、更新、删除功能。
"""
from __future__ import annotations
import logging
from fastapi import APIRouter
from backend.models.request.env_requests import EnvVarUpdate, EnvVarDelete
from backend.services import settings as settings_service

router = APIRouter(prefix="/env", tags=["env"])
_log = logging.getLogger(__name__)


@router.get("")
async def get_env() -> dict:
    """读取所有环境变量。"""
    return settings_service.get_env_vars()


@router.put("")
async def update_env(body: EnvVarUpdate) -> dict:
    """更新指定环境变量的值。"""
    return settings_service.update_env_var(body.key, body.value)


@router.delete("")
async def delete_env(body: EnvVarDelete) -> dict:
    """删除指定的环境变量。"""
    return settings_service.delete_env_var(body.key)
