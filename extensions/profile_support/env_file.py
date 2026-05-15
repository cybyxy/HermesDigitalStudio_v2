"""Profile-aware .env file resolution.

Implements resolve_user_env_file() which allows named profiles to use
the root .env file when no profile-specific .env exists.
"""
import os
from pathlib import Path


def resolve_user_env_file(home_path: Path) -> Path:
    """Resolve which .env file to load for home_path (HERMES_HOME).

    Named profiles use .../profiles/<name>/ as HERMES_HOME and usually have
    no local .env; API keys live in get_default_hermes_root()/.env next
    to the shared config.yaml.
    """
    user_env = home_path / ".env"
    if user_env.is_file():
        return user_env
    try:
        from extensions.profile_support.config_path import get_default_hermes_root

        root = get_default_hermes_root().resolve()
        profiles_root = (root / "profiles").resolve()
        home_resolved = home_path.resolve()
        home_resolved.relative_to(profiles_root)
    except (ValueError, OSError):
        return user_env
    root_env = root / ".env"
    return root_env if root_env.is_file() else user_env


def patch_env_loader():
    """Patch hermes_cli.env_loader to use profile-aware .env resolution."""
    import sys

    vendor_env_loader = sys.modules.get("hermes_cli.env_loader")
    if vendor_env_loader is None:
        return

    vendor_env_loader.resolve_user_env_file = resolve_user_env_file
