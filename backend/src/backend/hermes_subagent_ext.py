"""Backward-compatible re-export shim for backend.hermes_subagent_ext.

All patches are now defined in separate modules under the vendor_patches/ package:
- _common       → vendor_patches._common
- memory        → vendor_patches.memory
- session_search→ vendor_patches.session_search
- delegate      → vendor_patches.delegate
- lifecycle     → vendor_patches.lifecycle

This file exists purely for backward compatibility with existing import paths.
New code should import from::

    from backend.vendor_patches import apply_runtime_patches
"""

from backend.vendor_patches import apply_runtime_patches as _apply_runtime_patches

apply_runtime_patches = _apply_runtime_patches

__all__ = ["apply_runtime_patches"]
