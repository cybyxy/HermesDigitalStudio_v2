"""Profile-aware config path resolution.

Implements resolve_user_config_path() which allows named profiles to share
a root config.yaml while maintaining isolated HERMES_HOME directories.
"""
import os
from pathlib import Path
from typing import Optional


def get_default_hermes_root() -> Path:
    """Return the root Hermes directory for profile-level operations.

    In standard deployments this is ~/.hermes.
    In Docker or custom deployments where HERMES_HOME points outside
    ~/.hermes (e.g. /opt/data), returns HERMES_HOME directly.
    In profile mode where HERMES_HOME is <root>/profiles/<name>,
    returns <root> so that profile list can see all profiles.
    """
    native_home = Path.home() / ".hermes"
    env_home = os.environ.get("HERMES_HOME", "")
    if not env_home:
        return native_home
    env_path = Path(env_home)
    try:
        env_path.resolve().relative_to(native_home.resolve())
        return native_home
    except ValueError:
        pass

    if env_path.parent.name == "profiles":
        return env_path.parent.parent
    return env_path


def get_hermes_home() -> Path:
    """Return the Hermes home directory (default: ~/.hermes)."""
    val = os.environ.get("HERMES_HOME", "").strip()
    return Path(val) if val else Path.home() / ".hermes"


def resolve_user_config_path(home_path: Optional[Path] = None) -> Path:
    """Resolve config.yaml for a Hermes home directory.

    Named profiles use .../profiles/<name>/ as HERMES_HOME but share the
    root get_default_hermes_root() / "config.yaml" instead of storing
    config.yaml under the profile directory.
    """
    hm = Path(home_path) if home_path is not None else get_hermes_home()
    try:
        root = get_default_hermes_root().resolve()
        profiles_root = (root / "profiles").resolve()
        hm.resolve().relative_to(profiles_root)
        return root / "config.yaml"
    except (ValueError, OSError):
        pass
    return hm / "config.yaml"


def get_config_path() -> Path:
    """Return the path to config.yaml under HERMES_HOME.

    This uses resolve_user_config_path to support named profiles.
    """
    return resolve_user_config_path(get_hermes_home())


def patch_hermes_constants():
    """Patch hermes_constants module to use profile-aware config resolution."""
    import sys
    from types import ModuleType

    vendor_hermes_constants = sys.modules.get("hermes_constants")
    if vendor_hermes_constants is None:
        return

    vendor_hermes_constants.resolve_user_config_path = resolve_user_config_path
    vendor_hermes_constants.get_config_path = get_config_path


def patch_hermes_cli_config():
    """Patch hermes_cli.config module to use profile-aware config resolution."""
    import sys

    vendor_config = sys.modules.get("hermes_cli.config")
    if vendor_config is None:
        return

    vendor_config.get_config_path = get_config_path
    vendor_config.get_hermes_home = get_hermes_home
