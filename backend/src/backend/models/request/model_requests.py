"""模型路由的 Pydantic 请求模型。"""

from __future__ import annotations

from pydantic import BaseModel


class ModelAssignment(BaseModel):
    """设置模型分配的请求体。"""
    scope: str = ""    # "main" | "auxiliary"，主模型或辅助模型
    provider: str = ""  # 模型提供方名称
    model: str = ""     # 模型名称
    task: str = ""      # 辅助任务名称（scope=auxiliary 时填写）
