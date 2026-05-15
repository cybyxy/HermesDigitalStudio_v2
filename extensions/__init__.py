"""Hermes Agent Extensions.

This module provides monkey-patches and extensions to implement vendor-specific
functionality without modifying upstream source code.

Call `apply_all_patches()` at application startup to enable all extensions.
"""
import logging

logger = logging.getLogger(__name__)


def apply_profile_support_patches():
    """Apply Named Profiles support patches.

    - Patches hermes_constants to use profile-aware config resolution
    - Patches hermes_cli.config to use profile-aware config resolution
    - Patches hermes_cli.env_loader to use profile-aware .env resolution
    """
    try:
        from extensions.profile_support import config_path, env_file
        config_path.patch_hermes_constants()
        config_path.patch_hermes_cli_config()
        env_file.patch_env_loader()
        logger.debug("profile_support patches applied")
    except Exception as exc:
        logger.warning("Failed to apply profile_support patches: %s", exc)


def apply_image_routing_patches():
    """Apply HERMES_GATEWAY_NATIVE_IMAGES support.

    Patches agent.image_routing to check HERMES_GATEWAY_NATIVE_IMAGES
    environment variable.
    """
    try:
        from extensions.image_routing import patch_image_routing
        patch_image_routing()
        logger.debug("image_routing patches applied")
    except Exception as exc:
        logger.warning("Failed to apply image_routing patches: %s", exc)


def apply_feishu_bridge_patches():
    """Apply Feishu Studio bridge patches.

    Patches gateway.run to support Feishu Studio bridge integration
    and adds model.default/provider/base_url to cache busting keys.
    """
    try:
        from extensions.feishu_bridge import patch_gateway_run
        patch_gateway_run()
        logger.debug("feishu_bridge patches applied")
    except Exception as exc:
        logger.warning("Failed to apply feishu_bridge patches: %s", exc)


def apply_timestamp_patches():
    """Apply timestamp support to hermes_state.

    Patches Database.get_messages_as_conversation to include
    timestamp field in returned messages.
    """
    try:
        from extensions.timestamp import patch_hermes_state
        patch_hermes_state()
        logger.debug("timestamp patches applied")
    except Exception as exc:
        logger.warning("Failed to apply timestamp patches: %s", exc)


def apply_all_patches():
    """Apply all extension patches.

    Call this at application startup to enable all vendor-specific
    functionality implemented through monkey-patching.

    Note: Order matters - profile_support should be applied first
    as other patches may depend on get_config_path().
    """
    apply_profile_support_patches()
    apply_image_routing_patches()
    apply_feishu_bridge_patches()
    apply_timestamp_patches()
    logger.info("All extension patches applied")


__all__ = [
    "apply_all_patches",
    "apply_profile_support_patches",
    "apply_image_routing_patches",
    "apply_feishu_bridge_patches",
    "apply_timestamp_patches",
]
