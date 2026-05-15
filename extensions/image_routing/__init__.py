"""HERMES_GATEWAY_NATIVE_IMAGES environment variable support.

This extension patches the image routing logic to support the
HERMES_GATEWAY_NATIVE_IMAGES environment variable, which forces native
image content parts for headless/programmatic gateways.
"""
import os


def patch_image_routing():
    """Patch agent.image_routing to support HERMES_GATEWAY_NATIVE_IMAGES.

    When HERMES_GATEWAY_NATIVE_IMAGES is set to "1", "true", or "yes",
    the determine_image_routing_mode function will return "native" for
    headless/programmatic gateways that use JSON-RPC over stdio.
    """
    import sys

    image_routing = sys.modules.get("agent.image_routing")
    if image_routing is None:
        return

    _original_determine = getattr(image_routing, 'determine_image_routing_mode', None)
    if _original_determine is None:
        return

    def patched_determine_image_routing_mode(cfg, provider, model, mode_cfg):
        """Patched version that checks HERMES_GATEWAY_NATIVE_IMAGES env var."""
        gw_native = os.environ.get("HERMES_GATEWAY_NATIVE_IMAGES", "").strip().lower()
        if gw_native in ("1", "true", "yes"):
            return "native"
        return _original_determine(cfg, provider, model, mode_cfg)

    image_routing.determine_image_routing_mode = patched_determine_image_routing_mode
