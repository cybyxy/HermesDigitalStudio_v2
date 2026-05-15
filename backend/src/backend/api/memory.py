"""MemOS 记忆管理 API — 记忆状态查询等。"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Query

from backend.services.mem_os_service import mos_search

_log = logging.getLogger(__name__)

router = APIRouter(prefix="/memory", tags=["memory"])


@router.get("/agents/{agent_id}/search")
async def search_vector_memory(
    agent_id: str,
    query: str = Query("", description="搜索查询，空字符串返回所有记忆"),
    top_k: int = Query(10, ge=1, le=50, description="返回结果数"),
) -> dict:
    """在 Agent 的 MemOS 向量库中搜索相关记忆条目。"""
    results = mos_search(agent_id, query=query, top_k=top_k)
    return {"results": results, "count": len(results)}
