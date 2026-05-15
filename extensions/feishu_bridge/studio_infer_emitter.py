"""Feishu 网关回合 → Hermes Digital Studio 的细粒度推理流（HTTP ingest）。

读取 ``HERMES_HOME/studio_gateway_bridge.json``（由 Studio 写入），将
``message.start`` / ``reasoning.delta`` / ``message.complete`` 投递到
``ingest_url``，与 ``tui_gateway`` 解包后的 SSE 事件形状一致。
"""

from __future__ import annotations

import json
import logging
import os
import threading
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)

_turn_armed = False
_cfg_cache: tuple[float, dict[str, Any]] | None = None


def _hermes_home() -> Path:
    return Path(os.environ.get("HERMES_HOME", str(Path.home() / ".hermes"))).expanduser()


def _load_bridge_cfg() -> Optional[dict[str, Any]]:
    global _cfg_cache
    path = _hermes_home() / "studio_gateway_bridge.json"
    try:
        st = path.stat().st_mtime
    except OSError:
        return None
    if _cfg_cache and _cfg_cache[0] == st:
        return _cfg_cache[1]
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.debug("studio_infer_emitter: read bridge json failed: %s", exc)
        return None
    if not isinstance(raw, dict):
        return None
    _cfg_cache = (st, raw)
    return raw


def _emit_http(event: dict[str, Any]) -> None:
    cfg = _load_bridge_cfg()
    if not cfg:
        return
    url = str(cfg.get("ingest_url") or "").strip()
    secret = str(cfg.get("secret") or "").strip()
    if not url or not secret:
        return

    def _run() -> None:
        try:
            body = json.dumps(event, ensure_ascii=False).encode("utf-8")
            req = urllib.request.Request(
                url,
                data=body,
                headers={
                    "Content-Type": "application/json",
                    "X-Hermes-Studio-Gateway-Bridge-Secret": secret,
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=4.0) as resp:
                resp.read(256)
        except urllib.error.HTTPError as exc:
            logger.debug("studio_infer_emitter HTTP %s: %s", exc.code, exc.reason)
        except Exception as exc:
            logger.debug("studio_infer_emitter post failed: %s", exc)

    threading.Thread(target=_run, daemon=True, name="studio-bridge-emit").start()


def _emit_flat(event_type: str, session_id: str, payload: Optional[dict[str, Any]] = None) -> None:
    ev: dict[str, Any] = {"type": event_type, "session_id": session_id}
    if payload is not None:
        ev["payload"] = payload
    _emit_http(ev)


def feishu_studio_prepare_turn(*, gateway_session_id: str, session_key: str) -> bool:
    """若已配置 Studio 桥，则发送 ``message.start`` 并进入本回合桥接状态。"""
    global _turn_armed
    cfg = _load_bridge_cfg()
    if not cfg:
        return False
    sid = str(cfg.get("session_id") or "").strip()
    if not sid:
        return False
    _turn_armed = True
    _emit_flat(
        "message.start",
        sid,
        {
            "gateway_session_id": gateway_session_id,
            "gateway_session_key": session_key or "",
        },
    )
    return True


def feishu_studio_wrap_stream_delta(inner: Optional[Callable[[str], None]]) -> Callable[[str], None]:
    """包装 ``stream_delta_callback``：在写平台的同时向 Studio 推 ``reasoning.delta``。"""

    def _wrapped(text: str) -> None:
        if inner is not None:
            try:
                inner(text)
            except Exception:
                pass
        if not _turn_armed or not text:
            return
        cfg = _load_bridge_cfg()
        if not cfg:
            return
        sid = str(cfg.get("session_id") or "").strip()
        if not sid:
            return
        _emit_flat("reasoning.delta", sid, {"text": text})

    return _wrapped


def feishu_studio_turn_end(result: Optional[dict[str, Any]], err: Optional[BaseException]) -> None:
    """回合结束：发送 ``message.complete`` 并清除桥接状态。"""
    global _turn_armed
    if not _turn_armed:
        return
    _turn_armed = False
    cfg = _load_bridge_cfg()
    if not cfg:
        return
    sid = str(cfg.get("session_id") or "").strip()
    if not sid:
        return
    if err is not None:
        _emit_flat(
            "message.complete",
            sid,
            {
                "status": "error",
                "text": "",
                "error": str(err),
            },
        )
        return
    r = result or {}
    text = str(r.get("final_response") or "")
    err_msg = str(r.get("error") or "")
    status = "complete"
    if r.get("failed") or err_msg:
        status = "error"
        if not text.strip():
            text = err_msg or "错误"
    _emit_flat(
        "message.complete",
        sid,
        {
            "status": status,
            "text": text,
            "error": err_msg if status == "error" else "",
        },
    )


def patch_gateway_run():
    """Patch gateway.run to support Feishu Studio bridge integration."""
    import sys

    gateway_run = sys.modules.get("gateway.run")
    if gateway_run is None:
        return

    _original_cache_keys = (
        ("model", "context_length"),
        ("model", "default"),
        ("model", "provider"),
        ("model", "base_url"),
        ("compression", "enabled"),
        ("compression", "threshold"),
        ("compression", "target_ratio"),
        ("compression", "protect_last_n"),
    )

    gateway_run.GatewayRunner._CACHE_BUSTING_CONFIG_KEYS = _original_cache_keys
