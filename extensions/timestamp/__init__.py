"""Timestamp support extension for hermes_state.

This extension patches the Database.get_messages_as_conversation method
to include timestamp field in returned messages.
"""
from typing import Any, Dict, List


def patch_hermes_state():
    """Patch hermes_state.Database to include timestamp in get_messages_as_conversation."""
    import sys

    hermes_state = sys.modules.get("hermes_state")
    if hermes_state is None:
        return

    Database = getattr(hermes_state, "Database", None)
    if Database is None:
        return

    _original_method = getattr(Database, "get_messages_as_conversation", None)
    if _original_method is None:
        return

    def patched_get_messages_as_conversation(
        self, session_id: str, include_ancestors: bool = False
    ) -> List[Dict[str, Any]]:
        """Patched version that includes timestamp field in returned messages."""
        session_ids = [session_id]
        if include_ancestors:
            session_ids = self._session_lineage_root_to_tip(session_id)

        with self._lock:
            placeholders = ",".join("?" for _ in session_ids)
            rows = self._conn.execute(
                "SELECT role, content, tool_call_id, tool_calls, tool_name, timestamp, "
                "reasoning, reasoning_content, reasoning_details, codex_reasoning_items, "
                "codex_message_items "
                f"FROM messages WHERE session_id IN ({placeholders}) ORDER BY timestamp, id",
                tuple(session_ids),
            ).fetchall()

        messages = []
        for row in rows:
            content = row["content"]
            if row["role"] in {"user", "assistant"} and isinstance(content, str):
                content = sanitize_context(content).strip()
            msg: Dict[str, Any] = {"role": row["role"], "content": content}
            ts = row["timestamp"]
            if ts is not None:
                msg["timestamp"] = float(ts)
            if row["tool_call_id"]:
                msg["tool_call_id"] = row["tool_call_id"]
            if row["tool_calls"]:
                msg["tool_calls"] = row["tool_calls"]
            if row["tool_name"]:
                msg["tool_name"] = row["tool_name"]
            if row["reasoning"]:
                msg["reasoning"] = row["reasoning"]
            if row["reasoning_content"]:
                msg["reasoning_content"] = row["reasoning_content"]
            if row["reasoning_details"]:
                msg["reasoning_details"] = row["reasoning_details"]
            if row["codex_reasoning_items"]:
                msg["codex_reasoning_items"] = row["codex_reasoning_items"]
            if row["codex_message_items"]:
                msg["codex_message_items"] = row["codex_message_items"]
            messages.append(msg)
        return messages

    Database.get_messages_as_conversation = patched_get_messages_as_conversation


def sanitize_context(text: str) -> str:
    """Placeholder - actual implementation imported from hermes_state."""
    import sys
    from hermes_state import sanitize_context as _sanitize
    return _sanitize(text)
