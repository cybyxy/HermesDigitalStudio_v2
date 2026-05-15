"""只读查询飞书消息网关写入的 Hermes ``state.db`` 会话与消息。

数据与嵌入式 ``gateway.run`` / ``FeishuAdapter`` 一致，库路径为
``{HERMES_HOME}/state.db``（默认 ``~/.hermes/state.db``），与各 Agent
``profiles/studio_agent_*/state.db`` 中的 Studio WebSocket 会话不同。
"""

from __future__ import annotations

import logging
import sqlite3
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from backend.core.config import get_config

_log = logging.getLogger(__name__)

_BACKEND_DIR = Path(__file__).resolve().parents[3]
_REPO_ROOT = _BACKEND_DIR.parent
_HERMES_VENDOR_ROOT = _REPO_ROOT / "vendor" / "hermes-agent"

_ROLES_MAIN = frozenset({"user", "assistant"})


def _ensure_vendor_on_path() -> None:
    v = str(_HERMES_VENDOR_ROOT)
    if v not in sys.path:
        sys.path.insert(0, v)


def gateway_state_db_path() -> Path:
    """与消息网关、``hermes_state.DEFAULT_DB_PATH`` 解析一致的 ``state.db`` 路径。"""
    return get_config().hermes_home / "state.db"


def _json_safe_row(row: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for k, v in row.items():
        if isinstance(v, bytes):
            out[k] = v.decode("utf-8", errors="replace")
        else:
            out[k] = v
    return out


def list_feishu_sessions(*, limit: int = 30, offset: int = 0) -> Dict[str, Any]:
    """返回 ``sessions.source = 'feishu'`` 的会话列表（rich 投影）。"""
    db_path = gateway_state_db_path()
    if not db_path.is_file():
        return {"ok": True, "dbPath": str(db_path), "sessions": [], "hint": "state.db 不存在（尚无网关会话或 HERMES_HOME 不同）"}

    _ensure_vendor_on_path()
    try:
        from hermes_state import SessionDB
    except ImportError as e:
        _log.warning("hermes_state 不可用: %s", e)
        return {"ok": False, "error": "hermes_state_unavailable", "sessions": []}

    limit = max(1, min(int(limit), 200))
    offset = max(0, int(offset))

    db: Any = None
    try:
        db = SessionDB(db_path=db_path)
        rows = db.list_sessions_rich(source="feishu", limit=limit, offset=offset)
        sessions = [_json_safe_row(dict(r)) for r in rows]
        return {"ok": True, "dbPath": str(db_path), "sessions": sessions}
    except sqlite3.OperationalError as e:
        err = str(e).lower()
        if "locked" in err or "busy" in err:
            _log.debug("feishu transcript list locked: %s", e)
            return {
                "ok": False,
                "error": "database_busy",
                "sessions": [],
                "hint": "state.db 暂时被占用，请稍后重试",
            }
        _log.exception("list_feishu_sessions failed")
        return {"ok": False, "error": str(e), "sessions": []}
    except Exception:
        _log.exception("list_feishu_sessions failed")
        return {"ok": False, "error": "query_failed", "sessions": []}
    finally:
        if db is not None:
            try:
                db.close()
            except Exception:
                pass


def _json_safe_message_row(row: Dict[str, Any]) -> Dict[str, Any]:
    """将 ``SessionDB.get_messages`` 单行转为 JSON 安全 dict（保留推理与 tool_calls）。"""
    out: Dict[str, Any] = {}
    for k, v in row.items():
        if k == "tool_calls" and v is not None:
            out[k] = v if isinstance(v, (list, dict)) else v
            continue
        out[k] = _json_safe_row({k: v})[k]
    return out


def get_feishu_session_transcript_rich(session_id: str) -> Dict[str, Any]:
    """返回飞书会话的完整消息行（与网关 ``SessionDB.get_messages`` 一致，含 tool / 推理字段）。"""
    sid = (session_id or "").strip()
    if not sid:
        return {"ok": False, "error": "empty_session_id", "messages": []}

    db_path = gateway_state_db_path()
    if not db_path.is_file():
        return {"ok": False, "error": "no_database", "messages": [], "hint": str(db_path)}

    _ensure_vendor_on_path()
    try:
        from hermes_state import SessionDB
    except ImportError:
        return {"ok": False, "error": "hermes_state_unavailable", "messages": []}

    db: Any = None
    try:
        db = SessionDB(db_path=db_path)
        resolved = db.resolve_resume_session_id(sid)
        meta = db.get_session(resolved)
        if not meta:
            return {"ok": False, "error": "session_not_found", "messages": []}
        if str(meta.get("source") or "").strip().lower() != "feishu":
            return {"ok": False, "error": "not_feishu_session", "messages": []}

        raw = db.get_messages(resolved)
        messages = [_json_safe_message_row(dict(m)) for m in raw]
        return {
            "ok": True,
            "sessionId": sid,
            "resolvedSessionId": resolved,
            "messages": messages,
        }
    except sqlite3.OperationalError as e:
        err = str(e).lower()
        if "locked" in err or "busy" in err:
            return {
                "ok": False,
                "error": "database_busy",
                "messages": [],
                "hint": "state.db 暂时被占用，请稍后重试",
            }
        _log.exception("get_feishu_session_transcript_rich failed")
        return {"ok": False, "error": str(e), "messages": []}
    except Exception:
        _log.exception("get_feishu_session_transcript_rich failed")
        return {"ok": False, "error": "query_failed", "messages": []}
    finally:
        if db is not None:
            try:
                db.close()
            except Exception:
                pass


def get_feishu_session_messages(
    session_id: str,
    *,
    roles_filter: Optional[frozenset[str]] = None,
) -> Dict[str, Any]:
    """返回指定飞书会话的消息列表（经 ``resolve_resume_session_id`` 对齐压缩链）。"""
    sid = (session_id or "").strip()
    if not sid:
        return {"ok": False, "error": "empty_session_id", "messages": []}

    db_path = gateway_state_db_path()
    if not db_path.is_file():
        return {"ok": False, "error": "no_database", "messages": [], "hint": str(db_path)}

    _ensure_vendor_on_path()
    try:
        from hermes_state import SessionDB
    except ImportError:
        return {"ok": False, "error": "hermes_state_unavailable", "messages": []}

    roles = roles_filter if roles_filter is not None else _ROLES_MAIN

    db: Any = None
    try:
        db = SessionDB(db_path=db_path)
        resolved = db.resolve_resume_session_id(sid)
        meta = db.get_session(resolved)
        if not meta:
            return {"ok": False, "error": "session_not_found", "messages": []}
        if str(meta.get("source") or "").strip().lower() != "feishu":
            return {"ok": False, "error": "not_feishu_session", "messages": []}

        raw = db.get_messages(resolved)
        messages: List[Dict[str, Any]] = []
        for m in raw:
            role = str(m.get("role") or "")
            if role not in roles:
                continue
            messages.append(
                {
                    "id": m.get("id"),
                    "role": role,
                    "content": m.get("content"),
                    "timestamp": m.get("timestamp"),
                    "toolName": m.get("tool_name"),
                }
            )
        return {
            "ok": True,
            "sessionId": sid,
            "resolvedSessionId": resolved,
            "messages": messages,
        }
    except sqlite3.OperationalError as e:
        err = str(e).lower()
        if "locked" in err or "busy" in err:
            return {
                "ok": False,
                "error": "database_busy",
                "messages": [],
                "hint": "state.db 暂时被占用，请稍后重试",
            }
        _log.exception("get_feishu_session_messages failed")
        return {"ok": False, "error": str(e), "messages": []}
    except Exception:
        _log.exception("get_feishu_session_messages failed")
        return {"ok": False, "error": "query_failed", "messages": []}
    finally:
        if db is not None:
            try:
                db.close()
            except Exception:
                pass
