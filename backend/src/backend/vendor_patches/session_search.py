"""子代理 session_search 作用域限制。

通过 monkeypatch 将 ``session_search`` 工具的作用域限制为当前子代理的 session，
避免子代理搜索到父代理的对话历史。
"""

from __future__ import annotations

import json
import logging
from typing import Any, Callable, Optional

from backend.vendor_patches.memory import resolve_agent_for_session_search

_log = logging.getLogger(__name__)


def _session_search_current_session_only(
    query: str,
    role_filter: Optional[str],
    limit: int,
    db: Any,
    current_session_id: Optional[str],
) -> str:
    """FTS + summarize, restricted to *current_session_id* messages."""
    import asyncio
    import concurrent.futures

    from model_tools import _run_async
    from tools.session_search_tool import (
        _format_conversation,
        _format_timestamp,
        _get_session_search_max_concurrency,
        _summarize_session,
        _truncate_around_matches,
        tool_error,
    )

    if db is None:
        return tool_error("Session database not available.", success=False)

    if not isinstance(limit, int):
        try:
            limit = int(limit)
        except (TypeError, ValueError):
            limit = 3
    limit = max(1, min(limit, 5))

    if not current_session_id:
        return json.dumps(
            {
                "success": False,
                "error": "Subagent session_search requires a session id.",
            },
            ensure_ascii=False,
        )

    if not query or not query.strip():
        try:
            s = db.get_session(current_session_id) or {}
            return json.dumps(
                {
                    "success": True,
                    "mode": "recent",
                    "scope": "current_session",
                    "results": [
                        {
                            "session_id": current_session_id,
                            "title": s.get("title"),
                            "source": s.get("source", ""),
                            "started_at": s.get("started_at", ""),
                            "last_active": s.get("last_active", ""),
                            "message_count": s.get("message_count", 0),
                            "preview": s.get("preview", ""),
                        }
                    ],
                    "count": 1,
                    "message": "Current subagent session only.",
                },
                ensure_ascii=False,
            )
        except Exception as e:
            return tool_error(f"Failed to load session: {e}", success=False)

    query = query.strip()
    try:
        role_list = None
        if role_filter and role_filter.strip():
            role_list = [r.strip() for r in role_filter.split(",") if r.strip()]

        from tools.session_search_tool import _HIDDEN_SESSION_SOURCES

        raw_results = db.search_messages(
            query=query,
            role_filter=role_list,
            exclude_sources=list(_HIDDEN_SESSION_SOURCES),
            limit=80,
            offset=0,
        )
        filtered = [
            r
            for r in raw_results
            if r.get("session_id") == current_session_id
        ]
        if not filtered:
            return json.dumps(
                {
                    "success": True,
                    "query": query,
                    "scope": "current_session",
                    "results": [],
                    "count": 0,
                    "message": "No matches in the current session.",
                },
                ensure_ascii=False,
            )

        seen: dict = {}
        for result in filtered:
            sid = result["session_id"]
            if sid not in seen:
                seen[sid] = dict(result)
            if len(seen) >= limit:
                break

        tasks = []
        for session_id, match_info in seen.items():
            try:
                messages = db.get_messages_as_conversation(session_id)
                if not messages:
                    continue
                session_meta = db.get_session(session_id) or {}
                conversation_text = _format_conversation(messages)
                conversation_text = _truncate_around_matches(conversation_text, query)
                tasks.append((session_id, match_info, conversation_text, session_meta))
            except Exception as e:
                _log.warning("session_search subagent prep failed: %s", e, exc_info=True)

        async def _summarize_all():
            max_concurrency = min(
                _get_session_search_max_concurrency(), max(1, len(tasks))
            )
            semaphore = asyncio.Semaphore(max_concurrency)

            async def _bounded_summary(text: str, meta: dict):
                async with semaphore:
                    return await _summarize_session(text, query, meta)

            coros = [_bounded_summary(text, meta) for _, _, text, meta in tasks]
            return await asyncio.gather(*coros, return_exceptions=True)

        try:
            results = _run_async(_summarize_all())
        except concurrent.futures.TimeoutError:
            return json.dumps(
                {
                    "success": False,
                    "error": "Session summarization timed out.",
                },
                ensure_ascii=False,
            )

        summaries = []
        for (session_id, match_info, conversation_text, _), result in zip(tasks, results):
            if isinstance(result, Exception):
                result = None
            entry = {
                "session_id": session_id,
                "when": _format_timestamp(match_info.get("session_started")),
                "source": match_info.get("source", "unknown"),
                "model": match_info.get("model"),
            }
            if result:
                entry["summary"] = result
            else:
                preview = (
                    (conversation_text[:500] + "\n…[truncated]")
                    if conversation_text
                    else "No preview available."
                )
                entry["summary"] = f"[Raw preview — summarization unavailable]\n{preview}"
            summaries.append(entry)

        return json.dumps(
            {
                "success": True,
                "query": query,
                "scope": "current_session",
                "results": summaries,
                "count": len(summaries),
                "sessions_searched": len(seen),
            },
            ensure_ascii=False,
        )
    except Exception as e:
        _log.error("session_search (subagent scope) failed: %s", e, exc_info=True)
        return tool_error(f"Search failed: {e}", success=False)


def _wrap_session_search(orig: Callable) -> Callable:
    def _wrapped(
        query: str,
        role_filter: str = None,
        limit: int = 3,
        db=None,
        current_session_id: str = None,
    ) -> str:
        agent = resolve_agent_for_session_search()
        if agent is not None and getattr(agent, "_delegate_depth", 0) > 0:
            return _session_search_current_session_only(
                query, role_filter, limit, db, current_session_id
            )
        return orig(query, role_filter, limit, db, current_session_id)

    return _wrapped


def patch_session_search() -> None:
    """Monkeypatch vendor session_search 工具，限制子代理作用域。"""
    import tools.session_search_tool as sst

    if getattr(sst.session_search, "_hds_wrapped", False):
        return
    orig = sst.session_search
    w = _wrap_session_search(orig)
    w._hds_wrapped = True  # type: ignore[attr-defined]
    sst.session_search = w

    def _handler(args, **kw):
        return w(
            query=args.get("query") or "",
            role_filter=args.get("role_filter"),
            limit=args.get("limit", 3),
            db=kw.get("db"),
            current_session_id=kw.get("current_session_id"),
        )

    entry = sst.registry.get_entry("session_search")
    if entry is not None:
        entry.handler = _handler
