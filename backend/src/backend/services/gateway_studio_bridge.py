"""Hermes 消息网关（Feishu 等）→ Studio 前端的细粒度推理流（方案 C）。

- 网关子进程通过 HTTP POST 将事件投递到 ``POST .../internal/gateway-studio-event``。
- 浏览器通过 ``GET .../gateway-bridge/sse`` 订阅，事件形状与 ``SubprocessGateway`` 解包后的
  SSE 行一致：``{type, session_id, payload?}``（见 ``gateway.py::_dispatch_inbound``）。
- ``HERMES_HOME/studio_gateway_bridge.json`` 由 Studio 写入，供网关读取 ``ingest_url``、
  ``secret``、``session_id``（默认 profile Agent 的 Studio 会话 id）。
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import secrets
from pathlib import Path
from typing import Any

from fastapi import HTTPException, Request

from backend.core.config import get_config

_log = logging.getLogger(__name__)

_bridge_secret: str | None = None
_subscribers: list[asyncio.Queue[dict[str, Any] | None]] = []
_sub_lock = asyncio.Lock()


def get_bridge_secret() -> str:
    global _bridge_secret
    if _bridge_secret is None:
        _bridge_secret = secrets.token_urlsafe(32)
    return _bridge_secret


def _hermes_home_main() -> Path:
    return get_config().hermes_home


def bridge_config_path() -> Path:
    return _hermes_home_main() / "studio_gateway_bridge.json"


def write_studio_bridge_config_file() -> None:
    """根据当前 Agents 列表写入 ``studio_gateway_bridge.json``（默认 profile 的 defaultSessionId）。"""
    from backend.services import agent as agent_service

    path = bridge_config_path()
    try:
        agents = agent_service.list_agents()
    except Exception as exc:
        _log.debug("write_studio_bridge_config: list_agents failed: %s", exc)
        return

    default = next((a for a in agents if a.get("profile") == "default"), None)
    sid = (default or {}).get("defaultSessionId")
    if not sid:
        try:
            if path.is_file():
                path.unlink()
        except OSError:
            pass
        return

    port = get_config().port
    ingest = (
        get_config().gateway_ingest_url
        or f"http://127.0.0.1:{port}/api/chat/internal/gateway-studio-event"
    )
    body = {
        "ingest_url": ingest,
        "secret": get_bridge_secret(),
        "session_id": str(sid).strip(),
    }
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(body, ensure_ascii=False, indent=2), encoding="utf-8")
        _log.debug("Wrote %s (session_id=%s)", path, sid[:8] + "…")
    except OSError as exc:
        _log.warning("write studio_gateway_bridge.json failed: %s", exc)


async def publish_gateway_event(event: dict[str, Any]) -> None:
    """将单条事件广播给所有 ``gateway-bridge`` SSE 订阅者。"""
    async with _sub_lock:
        subs = list(_subscribers)
    dead: list[asyncio.Queue[dict[str, Any] | None]] = []
    for q in subs:
        try:
            q.put_nowait(event)
        except asyncio.QueueFull:
            _log.warning("gateway-bridge subscriber queue full, dropping event type=%s", event.get("type"))
        except Exception:
            dead.append(q)
    if dead:
        async with _sub_lock:
            for q in dead:
                if q in _subscribers:
                    _subscribers.remove(q)


# ── 心跳推理事件广播 ────────────────────────────────────────────────────

_heartbeat_subscribers: list[asyncio.Queue[dict[str, Any] | None]] = []
_heartbeat_sub_lock = asyncio.Lock()


async def publish_heartbeat_event(event: dict[str, Any]) -> None:
    """广播心跳推理事件给所有 heartbeat SSE 订阅者。"""
    async with _heartbeat_sub_lock:
        subs = list(_heartbeat_subscribers)
    dead: list[asyncio.Queue[dict[str, Any] | None]] = []
    for q in subs:
        try:
            q.put_nowait(event)
        except asyncio.QueueFull:
            _log.warning("heartbeat subscriber queue full, dropping event")
        except Exception:
            dead.append(q)
    if dead:
        async with _heartbeat_sub_lock:
            for q in dead:
                if q in _heartbeat_subscribers:
                    _heartbeat_subscribers.remove(q)


def sse_heartbeat() -> Any:
    """返回心跳推理事件的 SSE 流。

    浏览器订阅 ``GET /api/chat/heartbeat/sse`` 即可接收实时心跳推理结果。
    """
    from fastapi.responses import StreamingResponse

    async def _gen() -> Any:
        q: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue(maxsize=64)
        async with _heartbeat_sub_lock:
            _heartbeat_subscribers.append(q)
        try:
            while True:
                try:
                    item = await asyncio.wait_for(q.get(), timeout=55.0)
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
                    continue
                if item is None:
                    break
                line = "data: " + json.dumps(item, ensure_ascii=False) + "\n\n"
                yield line
        except asyncio.CancelledError:
            raise
        finally:
            async with _heartbeat_sub_lock:
                if q in _heartbeat_subscribers:
                    _heartbeat_subscribers.remove(q)

    return StreamingResponse(
        _gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )

def sse_gateway_bridge(token: str) -> Any:
    from fastapi.responses import StreamingResponse

    if not token:
        raise HTTPException(status_code=403, detail="invalid token")
    if not secrets.compare_digest(token, get_bridge_secret()):
        raise HTTPException(status_code=403, detail="invalid token")

    async def _gen() -> Any:
        q: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue(maxsize=512)
        async with _sub_lock:
            _subscribers.append(q)
        try:
            while True:
                try:
                    item = await asyncio.wait_for(q.get(), timeout=55.0)
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
                    continue
                if item is None:
                    break
                line = "data: " + json.dumps(item, ensure_ascii=False) + "\n\n"
                yield line
        except asyncio.CancelledError:
            raise
        finally:
            async with _sub_lock:
                if q in _subscribers:
                    _subscribers.remove(q)

    return StreamingResponse(
        _gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


def _header_secret(request: Request) -> str:
    return (
        request.headers.get("x-hermes-studio-gateway-bridge-secret")
        or request.headers.get("X-Hermes-Studio-Gateway-Bridge-Secret")
        or ""
    ).strip()


async def ingest_gateway_studio_event(request: Request) -> dict[str, Any]:
    """网关子进程调用：请求体为扁平事件 ``{type, session_id, payload?}``。"""
    sec = _header_secret(request)
    if not sec or not secrets.compare_digest(sec, get_bridge_secret()):
        raise HTTPException(status_code=401, detail="unauthorized")
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="invalid json") from None
    if not isinstance(body, dict) or not body.get("type"):
        raise HTTPException(status_code=400, detail="missing type")
    await publish_gateway_event(body)
    return {"ok": True}
