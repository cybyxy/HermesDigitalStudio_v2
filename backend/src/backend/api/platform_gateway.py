"""嵌入式 Hermes 消息网关 — REST 控制与状态。"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Query

from backend.core.exceptions import GatewayError
from backend.services import platform_gateway as pgw

router = APIRouter(prefix="/platform-gateway", tags=["platform-gateway"])
_log = logging.getLogger(__name__)


@router.get("/status")
async def gateway_status() -> dict:
    """返回 gateway.pid 与 Studio 嵌入式子进程状态。"""
    return pgw.gateway_runtime_status()


@router.post("/start")
async def gateway_start(force: bool = Query(False, description="若 gateway.pid 已存在仍尝试启动（可能失败）")) -> dict:
    """启动嵌入式 ``gateway.run`` 子进程（不依赖环境变量，用于手动联调）。"""
    try:
        return pgw.start_embedded_gateway(force=force, require_env=False)
    except Exception as e:
        raise GatewayError(str(e)) from e


@router.post("/stop")
async def gateway_stop() -> dict:
    """停止由 Studio 启动的嵌入式网关子进程。"""
    try:
        return pgw.stop_embedded_gateway()
    except Exception as e:
        raise GatewayError(str(e)) from e


@router.post("/restart")
async def gateway_restart() -> dict:
    """重启嵌入式网关（用于 config 变更后手动触发；通道保存接口也会自动调用）。"""
    try:
        return pgw.restart_embedded_gateway_after_channel_change()
    except Exception as e:
        raise GatewayError(str(e)) from e
