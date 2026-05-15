"""Settings 业务逻辑层 — 兼容性重导出模块。

实际实现拆分至：
- backend.services.model_config  — 模型配置 CRUD
- backend.services.config_file   — 配置文件 ~/.hermes/config.yaml 读写
"""

from __future__ import annotations


def __getattr__(name: str):
    # Model config
    if name in ("_provider_row_base_url", "resolve_main_model_base_url",
                "get_models_list_for_ui"):
        import backend.services.model_config as _m
        return getattr(_m, name)
    # Config file
    if name in ("get_settings", "save_settings", "get_env_vars",
                "update_env_var", "delete_env_var", "check_config"):
        import backend.services.config_file as _m
        return getattr(_m, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
