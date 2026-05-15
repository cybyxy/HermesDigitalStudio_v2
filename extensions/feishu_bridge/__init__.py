"""Feishu Studio bridge extension.

Provides integration between Feishu gateway and Hermes Digital Studio
for fine-grained reasoning stream emission via HTTP.
"""
from extensions.feishu_bridge.studio_infer_emitter import (
    feishu_studio_prepare_turn,
    feishu_studio_wrap_stream_delta,
    feishu_studio_turn_end,
)

__all__ = [
    "feishu_studio_prepare_turn",
    "feishu_studio_wrap_stream_delta",
    "feishu_studio_turn_end",
]
