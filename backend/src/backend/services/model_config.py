"""模型配置 CRUD 模块 — 构造前端 ModelInfo 列表。

对应 Spring Boot Service 层。
"""

from __future__ import annotations

import logging
from typing import Any

from hermes_cli.config import load_config, load_env

_log = logging.getLogger(__name__)


def _provider_row_base_url(nested: dict[str, Any]) -> str:
    """Hermes ``providers.<slug>`` 可为 ``api`` / ``url`` / ``base_url``（与 runtime_provider 一致）。"""
    return str(
        nested.get("api") or nested.get("url") or nested.get("base_url") or ""
    ).strip()


def resolve_main_model_base_url(
    main_model_cfg: Any,
    providers_cfg: Any,
    main_provider: str,
) -> str:
    """主模型的 API Base：优先 model.base_url，否则回退 providers.<provider> 的 api/url/base_url。"""
    u = ""
    if isinstance(main_model_cfg, dict):
        u = str(main_model_cfg.get("base_url") or "").strip()
    if u:
        return u
    if main_provider and isinstance(providers_cfg, dict):
        nested = providers_cfg.get(main_provider)
        if isinstance(nested, dict):
            return _provider_row_base_url(nested)
    return ""


def get_models_list_for_ui(
    cfg: dict[str, Any] | None = None,
    env_vars: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    """构造与前端 ModelInfo 对齐的模型列表。

    主模型字段与 Hermes 运行时同源：``hermes_cli.runtime_provider._get_model_config()``
    （含 ``model``→``default`` 别名、本地 base_url 自动探测等）。
    ``base_url`` 在规范化结果中仍为空时，再回退 ``providers.<provider>.base_url``。
    """
    from hermes_cli.runtime_provider import _get_model_config

    if cfg is None:
        cfg = load_config()
    if env_vars is None:
        env_vars = load_env()

    providers_cfg = cfg.get("providers", {})
    fallback_providers = cfg.get("fallback_providers", [])

    norm = _get_model_config()
    main_provider = str(norm.get("provider") or "").strip()
    main_name = str(norm.get("default") or norm.get("name") or "").strip()
    main_base_from_norm = str(norm.get("base_url") or "").strip()
    if main_base_from_norm:
        main_base_url = main_base_from_norm
    else:
        main_base_url = resolve_main_model_base_url(cfg.get("model", {}), providers_cfg, main_provider)

    main_api_key = ""
    if main_provider:
        key_name = f"{str(main_provider).upper().replace('-', '_')}_API_KEY"
        main_api_key = env_vars.get(key_name, "")

    models: list[dict[str, Any]] = [{
        "id": "main",
        "provider": main_provider,
        "model": main_name,
        "name": main_name,
        "apiKey": main_api_key,
        "baseUrl": main_base_url,
        "isDefault": True,
    }]

    for i, fb_raw in enumerate(fallback_providers):
        if isinstance(fb_raw, dict):
            fb_slug = str(fb_raw.get("provider") or "").strip()
            fb_model = str(fb_raw.get("model") or "").strip()
            fb_base_url = str(fb_raw.get("base_url") or "").strip()
        else:
            fb_slug = str(fb_raw or "").strip()
            fb_model = ""
            fb_base_url = ""
        if isinstance(providers_cfg, dict) and fb_slug and not fb_base_url:
            ent = providers_cfg.get(fb_slug)
            if isinstance(ent, dict):
                fb_base_url = _provider_row_base_url(ent)
        fb_disp = ""
        if isinstance(providers_cfg, dict) and fb_slug:
            ent = providers_cfg.get(fb_slug)
            if isinstance(ent, dict):
                fb_disp = str(ent.get("name") or "").strip()
        fb_key_name = f"{fb_slug.upper().replace('-', '_')}_API_KEY" if fb_slug else ""
        fb_api_key = env_vars.get(fb_key_name, "") if fb_key_name else ""
        models.append({
            "id": f"fallback-{i}",
            "provider": fb_slug,
            "model": fb_model,
            "name": fb_disp or fb_model or fb_slug,
            "apiKey": fb_api_key,
            "baseUrl": fb_base_url,
            "isDefault": False,
        })

    # 其余厂商端点仅来自 ``providers``（Studio 添加模型不再写 fallback_providers）
    seen_provider = {str(m.get("provider") or "").strip().lower() for m in models if m.get("provider")}
    if isinstance(providers_cfg, dict):
        for pslug in sorted(providers_cfg.keys()):
            pl = str(pslug).strip().lower()
            if not pl or pl in seen_provider:
                continue
            ent = providers_cfg[pslug]
            if not isinstance(ent, dict):
                continue
            row_url = _provider_row_base_url(ent)
            disp = str(ent.get("name") or "").strip() or str(pslug).strip()
            dm = str(ent.get("default_model") or ent.get("model") or "").strip()
            key_env = str(ent.get("key_env") or "").strip()
            pk = env_vars.get(key_env, "") if key_env else ""
            if not pk:
                pk = env_vars.get(f"{pl.upper().replace('-', '_')}_API_KEY", "")
            models.append({
                "id": f"provider-{pslug}",
                "provider": str(pslug).strip(),
                "model": dm,
                "name": disp,
                "apiKey": pk,
                "baseUrl": row_url,
                "isDefault": False,
            })
            seen_provider.add(pl)

    return models
