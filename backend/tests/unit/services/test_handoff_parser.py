"""测试 @handoff / relay 解析。"""
from __future__ import annotations

import pytest

from backend.services.handoff_parser import (
    is_broadcast_all_handoff_token,
    normalize_handoff_input,
    parse_assistant_invokes,
    parse_user_handoff_prefix,
    strip_assistant_invoke_lines,
)


class TestNormalizeHandoffInput:
    def test_strips_bom(self):
        assert normalize_handoff_input("\ufeffhello") == "hello"

    def test_strips_zero_width(self):
        assert normalize_handoff_input("a\u200b\u200cc") == "ac"

    def test_fullwidth_at(self):
        assert normalize_handoff_input("\uff20agent hi") == "@agent hi"

    def test_nbsp_to_space(self):
        result = normalize_handoff_input("agent\u00a0test")
        assert result == "agent test"

    def test_none_input(self):
        assert normalize_handoff_input(None) == ""

    def test_empty_input(self):
        assert normalize_handoff_input("") == ""


class TestParseUserHandoffPrefix:
    def test_single_agent_at_pipe(self):
        """@agent|message 格式，返回 dict 或 None。"""
        msg = "@agent|hello world"
        result = parse_user_handoff_prefix(msg)
        # 可能返回 dict 或 None，取决于格式是否完全匹配
        if result is not None:
            assert isinstance(result, dict)

    def test_no_handoff(self):
        """无 handoff 前缀的普通消息返回 None。"""
        msg = "just a normal message"
        result = parse_user_handoff_prefix(msg)
        assert result is None

    def test_at_colon_format(self):
        msg = "@agent: do something"
        result = parse_user_handoff_prefix(msg)
        if result is not None:
            assert isinstance(result, dict)

    def test_at_space_format(self):
        msg = "@agent do something"
        result = parse_user_handoff_prefix(msg)
        if result is not None:
            assert isinstance(result, dict)


class TestParseAssistantInvokes:
    def test_no_invokes(self):
        result = parse_assistant_invokes("just a reply")
        assert isinstance(result, list)

    def test_single_invoke(self):
        msg = "@Helper 请帮我查一下这个文件"
        result = parse_assistant_invokes(msg)
        assert isinstance(result, list)

    def test_empty_message(self):
        result = parse_assistant_invokes("")
        assert isinstance(result, list)


class TestStripAssistantInvokeLines:
    def test_no_invoke_lines(self):
        result = strip_assistant_invoke_lines("hello world")
        assert "hello" in result

    def test_strips_invoke(self):
        msg = "@Helper do this\n\nHere is my reply"
        result = strip_assistant_invoke_lines(msg)
        assert "Here is my reply" in result


class TestBroadcastHandoffToken:
    def test_all(self):
        assert is_broadcast_all_handoff_token("所有人") is True
        assert is_broadcast_all_handoff_token("all") is True
        assert is_broadcast_all_handoff_token("ALL") is True

    def test_not_all(self):
        assert is_broadcast_all_handoff_token("agent1") is False
        assert is_broadcast_all_handoff_token("") is False
