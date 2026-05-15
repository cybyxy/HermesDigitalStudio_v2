"""Health Controller — 健康检查。

用于检测后端服务是否正常运行。
"""
from __future__ import annotations
from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict:
    """返回服务健康状态。"""
    return {"status": "ok"}
