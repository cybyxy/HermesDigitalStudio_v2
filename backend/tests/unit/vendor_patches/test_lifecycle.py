"""Vendor patch 单元测试 — lifecycle.py

验证生命周期 patch 函数存在且可调用（非破坏性测试）。
"""
from __future__ import annotations

import pytest


class TestLifecyclePatches:
    def test_patch_aiagent_run_conversation_exists(self):
        """验证 patch 函数存在且可导入。"""
        from backend.vendor_patches.lifecycle import patch_aiagent_run_conversation
        assert callable(patch_aiagent_run_conversation)

    def test_patch_invoke_tool_exists(self):
        from backend.vendor_patches.lifecycle import patch_invoke_tool
        assert callable(patch_invoke_tool)

    def test_patch_aiagent_close_exists(self):
        from backend.vendor_patches.lifecycle import patch_aiagent_close
        assert callable(patch_aiagent_close)

    def test_patch_compress_context_exists(self):
        from backend.vendor_patches.lifecycle import patch_compress_context
        assert callable(patch_compress_context)

    def test_all_patches_importable(self):
        """验证所有 lifecycle patch 可导入且为函数。"""
        from backend.vendor_patches import lifecycle
        patches = [
            lifecycle.patch_aiagent_run_conversation,
            lifecycle.patch_invoke_tool,
            lifecycle.patch_aiagent_close,
            lifecycle.patch_compress_context,
        ]
        for p in patches:
            assert callable(p), f"{p} is not callable"
