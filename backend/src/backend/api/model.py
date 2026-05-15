"""Model Controller — 模型配置管理。

提供模型列表查询与模型分配功能。
"""
from __future__ import annotations
import logging
from typing import Any
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from backend.models.request.model_requests import ModelAssignment
from backend.services.settings import get_models_list_for_ui
from hermes_cli.auth import PROVIDER_REGISTRY
from hermes_cli.config import load_config, save_config, save_env_value
from hermes_cli.models import probe_api_models

router = APIRouter(prefix="/model", tags=["model"])
_log = logging.getLogger(__name__)

# 独立 router，prefix=""，注册到 /api → 路径变成 /api/models
model_crud_router = APIRouter(prefix="", tags=["models"])
_chat_log = logging.getLogger(__name__)


def _api_key_env_var_name(provider_slug: str) -> str:
    return f"{str(provider_slug).strip().upper().replace('-', '_')}_API_KEY"


_VALID_HERMES_TRANSPORTS = frozenset(
    {"chat_completions", "codex_responses", "anthropic_messages", "bedrock_converse"}
)


def _resolve_provider_registry(slug: str) -> tuple[str, Any]:
    """返回 (config 中的 canonical slug, ProviderConfig|None)。"""
    s = (slug or "").strip()
    if not s:
        return "", None
    if s in PROVIDER_REGISTRY:
        return s, PROVIDER_REGISTRY[s]
    sl = s.lower()
    for k, v in PROVIDER_REGISTRY.items():
        if k.lower() == sl:
            return k, v
    return s, None


def _normalize_transport_value(raw: str | None) -> str:
    """Hermes ``transport`` 合法值见 runtime ``_parse_api_mode``；兼容历史 ``openai_chat``。"""
    if not raw or not str(raw).strip():
        return "chat_completions"
    t = str(raw).strip().lower()
    if t in ("openai_chat", "openai", "chat"):
        return "chat_completions"
    if t in _VALID_HERMES_TRANSPORTS:
        return t
    return "chat_completions"


def _infer_default_transport(canonical_slug: str, api_url: str, pcfg: Any) -> str:
    """按厂商 / URL 推断默认 transport（与常见官方 endpoint 一致）。"""
    u = (api_url or "").lower()
    if "/anthropic" in u or (pcfg and getattr(pcfg, "id", "") == "minimax-cn"):
        return "anthropic_messages"
    if pcfg and getattr(pcfg, "id", "") == "anthropic":
        return "anthropic_messages"
    if pcfg and getattr(pcfg, "id", "") in ("openai-codex", "xai"):
        return "codex_responses"
    return "chat_completions"


def merge_providers_hermes_format(
    cfg: dict[str, Any],
    *,
    provider_slug: str,
    display_name: str,
    api_url: str | None,
    default_model: str | None,
    transport: str | None = None,
) -> None:
    """写入 Hermes ``providers.<slug>`` 完整节点（api / name / transport / default_model / key_env）。

    内置厂商（如 ``minimax-cn``、``deepseek``）会从 ``PROVIDER_REGISTRY`` 补全
    ``name``、``key_env``（与 Hermes 文档中的环境变量名一致）及合适的 ``transport``。
    """
    slug = (provider_slug or "").strip()
    if not slug:
        return
    providers = cfg.setdefault("providers", {})
    if not isinstance(providers, dict):
        cfg["providers"] = {}
        providers = cfg["providers"]

    canonical, pcfg = _resolve_provider_registry(slug)
    # 与前端 / 用户选择的 provider 字符串一致，便于与 model.provider、.env 变量对齐
    prov_key = slug

    api_s = str(api_url or "").strip()
    if api_s:
        api_s = api_s.rstrip("/")
        name_s = (display_name or "").strip()
        if not name_s and pcfg is not None:
            name_s = str(getattr(pcfg, "name", "") or "").strip()
        if not name_s:
            name_s = prov_key
        model_s = str(default_model or "").strip()
        if transport is not None and str(transport).strip():
            tr = _normalize_transport_value(transport)
        else:
            tr = _infer_default_transport(canonical or prov_key, api_s, pcfg)
        if pcfg is not None and getattr(pcfg, "api_key_env_vars", None):
            key_env = str(pcfg.api_key_env_vars[0])
        else:
            key_env = _api_key_env_var_name(prov_key)
        providers[prov_key] = {
            "name": name_s,
            "api": api_s,
            "transport": tr,
            "default_model": model_s,
            "key_env": key_env,
        }
        return

    row = providers.get(prov_key)
    if not isinstance(row, dict):
        return
    row = dict(row)
    if default_model is not None and str(default_model).strip():
        row["default_model"] = str(default_model).strip()
    if display_name and str(display_name).strip():
        row["name"] = str(display_name).strip()
    if transport and str(transport).strip():
        row["transport"] = _normalize_transport_value(transport)
    if pcfg is not None and getattr(pcfg, "api_key_env_vars", None) and not row.get("key_env"):
        row["key_env"] = str(pcfg.api_key_env_vars[0])
    providers[prov_key] = row


def apply_providers_entry(
    cfg: dict[str, Any],
    slug: str,
    *,
    display_name: str = "",
    api_url: str | None = None,
    default_model: str | None = None,
    transport: str | None = None,
) -> None:
    """写入 ``providers`` 完整节点（内置与自定义同一套逻辑）。"""
    merge_providers_hermes_format(
        cfg,
        provider_slug=slug,
        display_name=display_name or slug,
        api_url=api_url,
        default_model=default_model,
        transport=transport,
    )


_PROVIDER_LIST_PREFIX = "provider-"


def _slug_from_provider_model_id(model_id: str) -> str | None:
    """解析 ``provider-<slug>`` 列表 id（slug 可含 ``-``）。"""
    mid = (model_id or "").strip()
    if not mid.startswith(_PROVIDER_LIST_PREFIX):
        return None
    s = mid[len(_PROVIDER_LIST_PREFIX) :].strip()
    return s or None


# ─── 共享工具 ─────────────────────────────────────────────────────────────────────

def _build_models_list() -> list[dict[str, Any]]:
    """从配置构建与前端 ModelInfo 对齐的模型列表（与 get_settings.models 同源）。"""
    return get_models_list_for_ui()


# ─── 原有 /model/* 端点 ───────────────────────────────────────────────────────────────

@router.get("/list")
async def list_models() -> dict:
    """列出当前配置的模型信息。"""
    cfg = load_config()
    return {"models": cfg.get("model", {})}


@router.post("/assign")
async def assign_model(body: ModelAssignment) -> dict:
    """分配模型：可设置主模型或辅助任务模型。"""
    cfg = load_config()
    if body.scope == "main":
        cfg["model"] = {"provider": body.provider, "default": body.model}
    elif body.scope == "auxiliary":
        cfg.setdefault("auxiliary", {})[body.task] = {"provider": body.provider, "model": body.model}
    save_config(cfg)
    return {"ok": True}


# ─── /chat/models 端点（前端期望的路径） ─────────────────────────────────────────────

class _PostModelRequest(BaseModel):
    name: str
    provider: str
    modelId: str
    apiBase: str | None = None
    apiKey: str | None = None
    # OpenAI Chat Completions 兼容通道，与 Hermes transport 一致（默认 openai_chat）
    transport: str | None = None
    contextWindow: int | None = None
    isDefault: bool = False
    enabled: bool = True
    description: str | None = None


class _ProbeProviderModelsRequest(BaseModel):
    provider: str
    apiKey: str | None = None
    apiBase: str | None = None


class _PutModelRequest(BaseModel):
    name: str | None = None
    provider: str | None = None
    modelId: str | None = None
    apiBase: str | None = None
    apiKey: str | None = None
    transport: str | None = None
    contextWindow: int | None = None
    isDefault: bool | None = None
    enabled: bool | None = None
    description: str | None = None


@model_crud_router.get("/models")
async def list_crud_models() -> dict:
    """GET /api/models — 返回与前端 ModelInfo 对齐的模型列表。"""
    models = _build_models_list()
    return {"ok": True, "models": models}


@model_crud_router.get("/providers")
async def list_providers() -> dict:
    """GET /api/providers — 返回源码 PROVIDER_REGISTRY 中的所有厂家，供前端 ModelEditForm 下拉列表用。"""
    providers = []
    for pid, pconfig in PROVIDER_REGISTRY.items():
        if pconfig.inference_base_url:
            providers.append({
                "id": pid,
                "name": pconfig.name,
                "inferenceBaseUrl": pconfig.inference_base_url,
                "authType": pconfig.auth_type,
            })
    providers.sort(key=lambda x: x["name"])
    return {"ok": True, "providers": providers}


@model_crud_router.get("/providers/{provider}/envkey")
async def get_provider_envkey(provider: str) -> dict:
    """GET /api/providers/{provider}/envkey — 返回该厂商对应的环境变量名及当前已保存的值。

    与 Hermes ``PROVIDER_REGISTRY`` 同源：优先用注册表的 ``api_key_env_vars`` 首项，
    否则按 ``{PROVIDER}_API_KEY`` 规则回退。
    """
    slug = (provider or "").strip()
    if not slug:
        raise HTTPException(status_code=400, detail="provider is required")

    _, pcfg = _resolve_provider_registry(slug)
    if pcfg is not None and getattr(pcfg, "api_key_env_vars", None):
        key_name = str(pcfg.api_key_env_vars[0])
    else:
        key_name = _api_key_env_var_name(slug)

    env_vars = load_env()
    key_value = env_vars.get(key_name, "")

    return {
        "ok": True,
        "envVarName": key_name,
        "envVarValue": key_value,
        "provider": slug,
    }

@model_crud_router.post("/provider-models")
async def probe_provider_models(body: _ProbeProviderModelsRequest) -> dict:
    """POST /api/provider-models — 调用 hermes_cli.models.probe_api_models 探测该厂商 URL 下的可用模型列表。"""
    result = probe_api_models(
        api_key=body.apiKey,
        base_url=body.apiBase,
        timeout=8.0,
    )
    return {
        "ok": True,
        "models": result.get("models") or [],
        "probedUrl": result.get("probed_url"),
        "resolvedBaseUrl": result.get("resolved_base_url"),
        "suggestedBaseUrl": result.get("suggested_base_url"),
    }


@model_crud_router.post("/models")
async def create_crud_model(body: _PostModelRequest) -> dict:
    """POST /api/models — 只写 ``providers.<slug>``；可选 ``isDefault`` 时同步 ``model`` 主槽位。

    不再写入 ``fallback_providers``（与 Hermes failover 链解耦，端点全部由 providers 表达）。
    """
    cfg = load_config()

    if body.isDefault:
        new_main: dict[str, Any] = {
            "provider": body.provider,
            "default": body.modelId,
        }
        if body.apiBase:
            new_main["base_url"] = body.apiBase
        cfg["model"] = new_main

    apply_providers_entry(
        cfg,
        body.provider,
        display_name=body.name or body.provider,
        api_url=body.apiBase,
        default_model=body.modelId,
        transport=body.transport,
    )
    save_config(cfg)

    # API Key 写入 ~/.hermes/.env（与 providers.<slug>.key_env 一致）
    if body.apiKey:
        save_env_value(_api_key_env_var_name(body.provider), body.apiKey)

    return {"ok": True, "modelId": body.modelId}


@model_crud_router.put("/models/{model_id}")
async def update_crud_model(model_id: str, body: _PutModelRequest) -> dict:
    """PUT /api/models/{model_id} — 只更新 ``providers`` / ``model``，不写 ``fallback_providers``。"""
    cfg = load_config()

    def _env_key_for_slug(slug: str) -> str:
        _, pcfg = _resolve_provider_registry(slug)
        if pcfg is not None and getattr(pcfg, "api_key_env_vars", None):
            return str(pcfg.api_key_env_vars[0])
        return _api_key_env_var_name(slug)

    prov_slug = _slug_from_provider_model_id(model_id)

    if model_id == "main":
        if body.provider or body.apiBase is not None or (body.modelId or "").strip():
            current = cfg.get("model", {})
            if not isinstance(current, dict):
                current = {}
            if body.provider:
                current["provider"] = body.provider
            if body.apiBase is not None:
                current["base_url"] = body.apiBase
            mid = (body.modelId or "").strip()
            if mid:
                current["default"] = mid
            cfg["model"] = current
        curp = cfg.get("model", {})
        if isinstance(curp, dict):
            pslug = str(curp.get("provider") or "").strip()
            if pslug:
                apply_providers_entry(
                    cfg,
                    pslug,
                    display_name=(body.name or "").strip() or pslug,
                    api_url=body.apiBase if body.apiBase is not None else curp.get("base_url"),
                    default_model=str(curp.get("default") or curp.get("model") or ""),
                    transport=body.transport,
                )
    elif prov_slug:
        prow = cfg.get("providers", {}).get(prov_slug) if isinstance(cfg.get("providers"), dict) else None
        api_guess = body.apiBase
        if api_guess is None and isinstance(prow, dict):
            api_guess = prow.get("api") or prow.get("url") or prow.get("base_url")
        model_guess = body.modelId
        if not (model_guess or "").strip() and isinstance(prow, dict):
            model_guess = str(prow.get("default_model") or prow.get("model") or "")
        apply_providers_entry(
            cfg,
            prov_slug,
            display_name=(body.name or "").strip() or prov_slug,
            api_url=api_guess,
            default_model=model_guess,
            transport=body.transport,
        )
        if body.isDefault:
            new_main: dict[str, Any] = {
                "provider": body.provider or prov_slug,
                "default": (body.modelId or "").strip() or str(model_guess or ""),
            }
            if body.apiBase is not None:
                new_main["base_url"] = body.apiBase
            elif isinstance(prow, dict) and (prow.get("api") or prow.get("base_url")):
                new_main["base_url"] = str(prow.get("api") or prow.get("base_url") or "").strip()
            cfg["model"] = new_main
    elif model_id.startswith("fallback-"):
        # 仅兼容旧配置列表展示：同步 ``providers``，不修改 fallback_providers 键
        idx = int(model_id.split("-")[1])
        fb_list: list = cfg.get("fallback_providers", [])
        if 0 <= idx < len(fb_list):
            entry = dict(fb_list[idx]) if isinstance(fb_list[idx], dict) else {}
            slug = str(body.provider or entry.get("provider") or "").strip()
            if slug:
                api_guess = body.apiBase if body.apiBase is not None else entry.get("base_url")
                model_guess = (body.modelId or "").strip() or str(entry.get("model") or "")
                apply_providers_entry(
                    cfg,
                    slug,
                    display_name=(body.name or "").strip() or slug,
                    api_url=api_guess,
                    default_model=model_guess,
                    transport=body.transport,
                )
            if body.isDefault and slug:
                new_main = {
                    "provider": slug,
                    "default": (body.modelId or "").strip() or str(entry.get("model") or ""),
                }
                if body.apiBase is not None:
                    new_main["base_url"] = body.apiBase
                elif entry.get("base_url"):
                    new_main["base_url"] = entry["base_url"]
                cfg["model"] = new_main
    elif body.isDefault and model_id != "main":
        raise HTTPException(
            status_code=400,
            detail="请使用 provider-<slug> 的 modelId 将某端点设为主模型",
        )

    save_config(cfg)

    if body.apiKey:
        key_slug = (body.provider or "").strip()
        if not key_slug and model_id == "main":
            m = cfg.get("model", {})
            if isinstance(m, dict):
                key_slug = str(m.get("provider") or "").strip()
        if not key_slug and prov_slug:
            key_slug = prov_slug
        if not key_slug and model_id.startswith("fallback-"):
            try:
                ix = int(model_id.split("-")[1])
                fl = cfg.get("fallback_providers", [])
                if 0 <= ix < len(fl) and isinstance(fl[ix], dict):
                    key_slug = str(fl[ix].get("provider") or "").strip()
            except (ValueError, IndexError):
                pass
        if key_slug:
            save_env_value(_env_key_for_slug(key_slug), body.apiKey)

    return {"ok": True}


@model_crud_router.delete("/models/{model_id}")
async def delete_crud_model(model_id: str) -> dict:
    """DELETE /api/models/{model_id} — 只删除 ``providers`` 中的节点，不写 ``fallback_providers``。"""
    if model_id == "main":
        raise HTTPException(status_code=400, detail="Cannot delete main model")
    cfg = load_config()
    pmap = cfg.get("providers")
    if not isinstance(pmap, dict):
        pmap = {}
        cfg["providers"] = pmap

    slug = _slug_from_provider_model_id(model_id)
    if slug:
        pmap.pop(slug, None)
        save_config(cfg)
        return {"ok": True}

    if model_id.startswith("fallback-"):
        idx = int(model_id.split("-")[1])
        fb_list: list = cfg.get("fallback_providers", [])
        if 0 <= idx < len(fb_list):
            raw = fb_list[idx]
            rem_slug = ""
            if isinstance(raw, dict):
                rem_slug = str(raw.get("provider") or "").strip()
            elif isinstance(raw, str):
                rem_slug = raw.strip()
            if rem_slug:
                pmap.pop(rem_slug, None)
        save_config(cfg)
        return {"ok": True}

    raise HTTPException(status_code=400, detail="Invalid model id")


# ══════════════════════════════════════════════════════════════════════════
# F5 全局成本统计端点
# ══════════════════════════════════════════════════════════════════════════


@router.get("/cost/stats")
async def global_model_cost_stats(days: int = 7) -> dict:
    """获取所有 Agent 的聚合模型调用成本统计。

    Query params:
    - ``days``: 统计最近 N 天（默认 7）
    """
    from backend.services.model_cost import get_cost_service
    if days < 1 or days > 365:
        days = 7
    return get_cost_service().get_global_stats(period_days=days)
