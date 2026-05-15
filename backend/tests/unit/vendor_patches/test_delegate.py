"""Vendor patch 单元测试 — delegate.py

验证委托 patch 函数存在且可调用。
"""
from __future__ import annotations

import pytest


class TestDelegatePatches:
    def test_patch_delegate_strip_exists(self):
        from backend.vendor_patches.delegate import patch_delegate_strip
        assert callable(patch_delegate_strip)

    def test_patch_build_child_agent_exists(self):
        from backend.vendor_patches.delegate import patch_build_child_agent
        assert callable(patch_build_child_agent)

    def test_patch_run_single_child_exists(self):
        from backend.vendor_patches.delegate import patch_run_single_child
        assert callable(patch_run_single_child)

    def test_all_patches_importable(self):
        """验证所有 delegate patch 可导入且为函数。"""
        from backend.vendor_patches import delegate
        patches = [
            delegate.patch_delegate_strip,
            delegate.patch_build_child_agent,
            delegate.patch_run_single_child,
        ]
        for p in patches:
            assert callable(p), f"{p} is not callable"
