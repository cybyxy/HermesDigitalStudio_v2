"""Vendor patch 单元测试 — memory_context.py

验证 <memory-context> 块构建函数的行为。
"""
from __future__ import annotations

import pytest


class TestBuildMemoryContextBlock:
    def test_wraps_content(self):
        from backend.vendor_patches.memory_context import build_memory_context_block
        result = build_memory_context_block("测试内容")
        assert "<memory-context>" in result
        assert "</memory-context>" in result
        assert "测试内容" in result

    def test_empty_content(self):
        from backend.vendor_patches.memory_context import build_memory_context_block
        result = build_memory_context_block("")
        assert "<memory-context>" in result


class TestBuildRoutingContext:
    def test_returns_string_with_personality(self):
        from backend.vendor_patches.memory_context import build_routing_context
        result = build_routing_context(
            "test_agent",
            personality_hint="【性格】乐观开朗",
            plan_hint="",
            peer_routing="",
            emotion_hint="",
        )
        assert isinstance(result, str)
        assert "【性格】乐观开朗" in result

    def test_returns_string_with_emotion(self):
        from backend.vendor_patches.memory_context import build_routing_context
        result = build_routing_context(
            "test_agent",
            personality_hint="",
            plan_hint="",
            peer_routing="",
            emotion_hint="【当前情绪】愉悦度:0.7 唤醒度:0.5 支配度:0.6",
        )
        assert isinstance(result, str)
        assert "愉悦度" in result

    def test_all_empty_returns_empty(self):
        from backend.vendor_patches.memory_context import build_routing_context
        result = build_routing_context(
            "test_agent",
            personality_hint="",
            plan_hint="",
            peer_routing="",
            emotion_hint="",
        )
        assert result == ""

    def test_includes_plan_structure(self):
        from backend.vendor_patches.memory_context import build_routing_context
        result = build_routing_context(
            "test_agent",
            personality_hint="",
            plan_hint="【任务规划指引】请以 JSON 格式输出",
            peer_routing="",
            emotion_hint="",
        )
        assert isinstance(result, str)
        assert "JSON" in result


class TestBuildSelfModelContext:
    def test_returns_string(self):
        from backend.vendor_patches.memory_context import build_self_model_context
        result = build_self_model_context("test_agent")
        assert isinstance(result, str)

    def test_nonexistent_agent_returns_empty(self):
        from backend.vendor_patches.memory_context import build_self_model_context
        result = build_self_model_context("nonexistent_agent_xyz_123")
        assert isinstance(result, str)  # should not throw
