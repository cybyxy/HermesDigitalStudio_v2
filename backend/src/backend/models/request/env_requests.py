"""环境变量路由的 Pydantic 请求模型。"""

from __future__ import annotations

from pydantic import BaseModel


class EnvVarUpdate(BaseModel):
    """更新（设置）环境变量的请求体。"""
    key: str = ""
    value: str = ""


class EnvVarDelete(BaseModel):
    """删除环境变量的请求体。"""
    key: str = ""
