"""Channel 业务逻辑层：通过 hermes_cli.config 读写 ~/.hermes/config.yaml。

对应 Spring Boot Service 层。
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

_log = logging.getLogger(__name__)

# vendor ``gateway/run.py`` 在「有启用平台但零连接且未汇总到 retryable 列表」时写入的兜底文案
_GENERIC_GATEWAY_EXIT_ALL_FAILED = "all configured messaging platforms failed to connect"


def _humanize_gateway_exit_reason(exit_reason: str) -> str:
    """把网关英文兜底 ``exit_reason`` 扩展为可操作的说明（不改 vendor）。"""
    er = (exit_reason or "").strip()
    if er.lower() == _GENERIC_GATEWAY_EXIT_ALL_FAILED.lower():
        return (
            f"{er} — 网关未把各平台失败明细写入 gateway_state.json。"
            "嵌入式网关：请在运行 Studio（uvicorn）的同一终端、INFO 级别日志中搜索 “[hermes-gateway]” 与 “Connecting to feishu”；"
            "独立 hermes gateway：请看该进程自己的终端。"
            "并确认 lark-oapi、飞书事件订阅/WebSocket、HERMES_HOME 与 config 一致。"
        )
    return er


class HermesConfigManagedError(Exception):
    """Hermes 为托管安装，save_config 不会写盘。"""


class ChannelPersistError(Exception):
    """通道已调用 save_config，但读盘校验未看到 platforms 条目。"""


# 写入 platforms.<p>.extra，Hermes 网关会忽略未知键；Studio 用于绑定 UI Agent
_STUDIO_AGENT_EXTRA_KEY = "studio_agent_id"

# hermes-agent 位于 vendor/hermes-agent，从 backend/src/backend/ 向外走 3 层 parents
_BACKEND_DIR = Path(__file__).resolve().parents[3]
_REPO_ROOT = _BACKEND_DIR.parent
_HERMES_VENDOR_ROOT = _REPO_ROOT / "vendor" / "hermes-agent"


def _ensure_hermes_agent_on_path() -> None:
    """把 hermes-agent 顶层目录加入 sys.path，使其可 import hermes_cli.config。"""
    vendor_root = str(_HERMES_VENDOR_ROOT)
    if vendor_root not in sys.path:
        sys.path.insert(0, vendor_root)


def _platforms_from_config(cfg: Dict[str, Any]) -> Dict[str, Any]:
    """从完整 config 中提取 platforms 子字典（兼容不存在 / null / 非 dict）。"""
    if not isinstance(cfg, dict):
        return {}
    p = cfg.get("platforms")
    return p if isinstance(p, dict) else {}


def _ensure_mutable_platforms(cfg: Dict[str, Any]) -> Dict[str, Any]:
    """保证 ``cfg[\"platforms\"]`` 为可写的 dict（修复 YAML 里 ``platforms:`` 为空或 null 的情况）。"""
    if not isinstance(cfg, dict):
        raise TypeError("config must be a dict")
    p = cfg.get("platforms")
    if not isinstance(p, dict):
        p = {}
        cfg["platforms"] = p
    return p


def _invalidate_hermes_config_caches() -> None:
    """写入 config.yaml 后清 hermes_cli 的 mtime 缓存，避免同进程内读到旧 platforms。"""
    try:
        import hermes_cli.config as hc

        hc._LOAD_CONFIG_CACHE.clear()
        hc._RAW_CONFIG_CACHE.clear()
    except Exception:
        _log.debug("invalidate hermes config caches skipped", exc_info=True)


def _assert_config_writable() -> None:
    """托管模式下 hermes_cli.save_config 会直接 return，通道会「假成功」不落盘。"""
    from hermes_cli.config import is_managed

    if is_managed():
        raise HermesConfigManagedError(
            "当前 Hermes 为包管理器托管安装（HERMES_MANAGED 或 ~/.hermes/.managed），"
            "无法通过 Studio 写入 config.yaml。请用手动编辑或包管理器提供的方式配置 platforms。"
        )


def _verify_platform_saved(platform: str) -> None:
    """保存后读盘校验 ``platforms.<platform>`` 是否存在（发现静默写失败）。"""
    import yaml

    from hermes_cli.config import get_config_path

    path = get_config_path()
    try:
        text = path.read_text(encoding="utf-8")
        raw = yaml.safe_load(text) or {}
    except Exception as e:
        _log.error("写入后无法读取 %s: %s", path, e)
        raise ChannelPersistError(f"无法读取配置文件 {path} 以校验通道是否已保存") from e

    if not isinstance(raw, dict):
        raise ChannelPersistError(f"{path} 内容不是 YAML 映射，通道未保存")
    pl = raw.get("platforms")
    if not isinstance(pl, dict) or platform not in pl:
        _log.error("校验失败: %s 中缺少 platforms.%s，磁盘内容可能未更新", path, platform)
        raise ChannelPersistError(
            f"通道未写入 {path}（platforms 仍为空或缺少 {platform}）。"
            "请检查磁盘权限、是否多进程同时改同一文件，或 config 中 platforms 是否为合法 YAML 映射。"
        )


def _safe_read_gateway_runtime_status() -> Optional[Dict[str, Any]]:
    """读取 ``~/.hermes`` 旁网关写入的 runtime 状态 JSON（无文件或异常则 None）。"""
    _ensure_hermes_agent_on_path()
    try:
        from gateway.status import read_runtime_status

        raw = read_runtime_status()
        return raw if isinstance(raw, dict) else None
    except Exception:
        _log.debug("read_runtime_status unavailable", exc_info=True)
        return None


def _ui_connection_status(platform: str, enabled: bool, runtime: Optional[Dict[str, Any]]) -> str:
    """映射网关 ``platforms.<name>.state`` → 前端 ``connected`` | ``disconnected`` | ``error``。"""
    if not enabled:
        return "disconnected"
    if not runtime:
        return "disconnected"

    gw = str(runtime.get("gateway_state") or "").strip().lower()
    plats = runtime.get("platforms")
    if not isinstance(plats, dict):
        plats = {}

    # 网关进程已报告整体启动失败，且未写入各平台 state 时，用「错误」比「未连接」更贴切
    if enabled and gw == "startup_failed" and not plats:
        return "error"

    info = plats.get(platform)
    if not isinstance(info, dict):
        return "disconnected"
    state = str(info.get("state") or "").strip().lower()
    if state == "connected":
        return "connected"
    if state == "fatal":
        return "error"
    if info.get("error_message") or info.get("error_code"):
        return "error"
    return "disconnected"


def _connection_status_detail(
    platform: str,
    enabled: bool,
    runtime: Optional[Dict[str, Any]],
    ui_status: str,
) -> Optional[str]:
    """为前端 ``status=error`` 提供可读说明（来自 ``gateway_state.json``，默认不进 Studio 日志）。"""
    if ui_status != "error":
        return None
    if not runtime:
        return "无法读取网关运行状态（请确认 Studio 与消息网关使用同一 HERMES_HOME）。"
    gw_raw = str(runtime.get("gateway_state") or "").strip()
    gw = gw_raw.lower()
    plats = runtime.get("platforms")
    if not isinstance(plats, dict):
        plats = {}

    if enabled and gw == "startup_failed" and not plats:
        er = str(runtime.get("exit_reason") or "").strip()
        if not er:
            return "消息网关启动失败，请查看运行 Hermes 消息网关进程的终端输出。"
        return _humanize_gateway_exit_reason(er)

    info = plats.get(platform)
    if isinstance(info, dict):
        em = str(info.get("error_message") or "").strip()
        ec = str(info.get("error_code") or "").strip()
        st = str(info.get("state") or "").strip().lower()
        if ec and em:
            return f"{ec}: {em}"
        if em:
            return em
        if ec:
            return ec
        if st == "fatal":
            return "致命错误（详见 Hermes 消息网关日志）。"

    if gw_raw:
        return f"网关状态: {gw_raw}"
    return "连接异常（详见 Hermes 消息网关日志）。"


def _agent_id_from_entry(entry: Dict[str, Any]) -> str:
    ex = entry.get("extra")
    if isinstance(ex, dict):
        return str(ex.get(_STUDIO_AGENT_EXTRA_KEY) or "").strip()
    return ""


def _sync_extra_credentials_from_token_fields(platform: str, entry: Dict[str, Any]) -> None:
    """把 UI 的 token / api_key 填进 Hermes 各平台适配器实际读取的 ``extra`` 键。

    vendor ``gateway.run`` 按平台构造 Adapter（如 ``FeishuAdapter``），多数非 Bot-Token
    平台从 ``PlatformConfig.extra`` 取 app_secret / client_secret 等；用户在表单里习惯
    把密钥写在「Bot Token」一栏，此处按平台映射，避免仅写 YAML 却不连平台。
    """
    if not isinstance(entry, dict):
        return
    extra = entry.get("extra")
    if not isinstance(extra, dict):
        extra = {}
        entry["extra"] = extra
    token = str(entry.get("token") or "").strip()
    api_key = str(entry.get("api_key") or "").strip()
    p = (platform or "").strip().lower()

    def _set_if(key: str, value: str, *, empty_means_skip: bool = True) -> None:
        if not value and empty_means_skip:
            return
        cur = str(extra.get(key) or "").strip()
        if not cur:
            extra[key] = value

    if p == "feishu":
        _set_if("app_secret", token)
    elif p == "dingtalk":
        _set_if("client_secret", token)
        _set_if("client_id", api_key)
    elif p == "wecom":
        _set_if("secret", token)
    elif p == "qqbot":
        _set_if("client_secret", token)
    elif p == "yuanbao":
        _set_if("app_secret", token)


def _notify_gateway_platform_updated() -> None:
    """持久化 config 后触发嵌入式网关重载，使各平台 ``adapter.connect()`` 使用新配置。"""
    try:
        from backend.services import platform_gateway as _pgw

        result = _pgw.restart_embedded_gateway_after_channel_change()
        if result.get("restarted"):
            _log.info("通道配置已保存，已重启嵌入式 Hermes 消息网关: %s", result)
        elif result.get("reason") == "external_gateway_running":
            _log.info("通道配置已保存: %s", result.get("hint", ""))
        else:
            _log.debug("通道配置保存后的网关动作: %s", result)
    except Exception:
        _log.exception("通道保存后重启消息网关失败（配置已写入磁盘）")


def _ensure_agent_unique_per_channel(
    platforms: Dict[str, Any],
    platform: str,
    agent_id: str,
) -> None:
    """同一 Agent 只能绑定一个通道（一个 platform 配置）；否则抛 ValueError。"""
    aid = (agent_id or "").strip()
    if not aid:
        return
    for plat, raw in platforms.items():
        if plat == platform:
            continue
        if not isinstance(raw, dict):
            continue
        home = raw.get("home_channel")
        if not isinstance(home, dict):
            continue
        if _agent_id_from_entry(raw) == aid:
            ch_name = home.get("name", plat)
            raise ValueError(f"该 Agent 已绑定通道「{ch_name}」（{plat}），请先解除后再绑定")


def _platform_to_channel_info(
    platform: str,
    cfg_entry: Dict[str, Any],
    *,
    runtime: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    """把单个 platform 的 config 条目规范化为前端 ChannelInfo 格式。

    Returns None 如果该 platform 根本没有配置（未启用、且无 home_channel）。
    """
    if not isinstance(cfg_entry, dict):
        return None

    home = cfg_entry.get("home_channel")
    if not isinstance(home, dict):
        # 未配置 home_channel 的 platform 视为"未创建通道"
        return None

    aid = _agent_id_from_entry(cfg_entry)
    extra = cfg_entry.get("extra", {})
    if not isinstance(extra, dict):
        extra = {}

    en = bool(cfg_entry.get("enabled", False))
    rt = runtime if runtime is not None else _safe_read_gateway_runtime_status()
    status = _ui_connection_status(platform, en, rt)
    detail = _connection_status_detail(platform, en, rt, status)

    out: Dict[str, Any] = {
        "id": f"{platform}:{home.get('chat_id', '')}",
        "name": home.get("name", platform),
        "platform": platform,
        "enabled": en,
        "chatId": home.get("chat_id", ""),
        "replyToMode": cfg_entry.get("reply_to_mode", "first"),
        "token": cfg_entry.get("token", ""),
        "extra": extra,
        "guild": None,
        "channelType": None,
        "lastMessageAt": None,
        "status": status,
        **({"agentId": aid} if aid else {}),
    }
    if detail:
        out["statusDetail"] = detail
    return out


def list_channels() -> List[Dict[str, Any]]:
    """返回所有已配置了 home_channel 的平台通道列表。

    对应 config.yaml 中 platforms.<platform>.home_channel 有值的所有条目。
    """
    _ensure_hermes_agent_on_path()
    from hermes_cli.config import load_config

    cfg = load_config()
    platforms = _platforms_from_config(cfg)
    runtime = _safe_read_gateway_runtime_status()

    channels = []
    err_hints: List[str] = []
    for platform, entry in platforms.items():
        ch = _platform_to_channel_info(platform, entry, runtime=runtime)
        if ch is not None:
            channels.append(ch)
            if ch.get("status") == "error":
                sd = str(ch.get("statusDetail") or "").strip()
                if sd:
                    err_hints.append(f"{platform}: {sd}")

    if err_hints:
        _log.warning("通道连接异常（gateway_state.json）: %s", " | ".join(err_hints))

    return channels


def get_channel(platform: str) -> Optional[Dict[str, Any]]:
    """返回指定平台的通道信息。"""
    _ensure_hermes_agent_on_path()
    from hermes_cli.config import load_config

    cfg = load_config()
    platforms = _platforms_from_config(cfg)

    entry = platforms.get(platform)
    if entry is None:
        return None
    return _platform_to_channel_info(platform, entry)


def upsert_channel(
    platform: str,
    name: str,
    chat_id: str,
    token: str = "",
    api_key: str = "",
    enabled: bool = True,
    reply_to_mode: str = "first",
    extra: Optional[Dict[str, Any]] = None,
    agent_id: Optional[str] = None,
) -> Dict[str, Any]:
    """创建或更新指定平台的 home_channel，并持久化到 config.yaml。"""
    _ensure_hermes_agent_on_path()
    from hermes_cli.config import load_config, save_config

    _assert_config_writable()
    cfg = load_config()
    platforms = _ensure_mutable_platforms(cfg)

    # 保留原有 token（如果未传），只更新明确提供的字段
    existing: Dict[str, Any] = platforms.get(platform, {})

    merged_extra: Dict[str, Any] = {}
    if isinstance(existing.get("extra"), dict):
        merged_extra.update(existing["extra"])
    if extra is not None:
        merged_extra.update(extra)
    if agent_id is not None:
        if str(agent_id).strip():
            _ensure_agent_unique_per_channel(platforms, platform, str(agent_id).strip())
            merged_extra[_STUDIO_AGENT_EXTRA_KEY] = str(agent_id).strip()
        else:
            merged_extra.pop(_STUDIO_AGENT_EXTRA_KEY, None)

    platforms[platform] = {
        "enabled": enabled,
        "token": token if token else existing.get("token", ""),
        "api_key": api_key if api_key else existing.get("api_key", ""),
        "home_channel": {
            "platform": platform,
            "chat_id": chat_id,
            "name": name,
        },
        "reply_to_mode": reply_to_mode,
        "extra": merged_extra,
    }
    _sync_extra_credentials_from_token_fields(platform, platforms[platform])

    save_config(cfg)
    _invalidate_hermes_config_caches()
    _verify_platform_saved(platform)
    _notify_gateway_platform_updated()

    return _platform_to_channel_info(platform, platforms[platform]) or {}


def delete_channel(platform: str) -> bool:
    """删除指定平台的 home_channel 配置（保留 platform 条目本身，仅清除 home_channel）。"""
    _ensure_hermes_agent_on_path()
    from hermes_cli.config import load_config, save_config

    _assert_config_writable()
    cfg = load_config()
    platforms = _ensure_mutable_platforms(cfg)

    if platform not in platforms:
        return False

    # 保留 enabled/token 等，仅删除 home_channel
    entry = platforms[platform]
    if isinstance(entry, dict):
        entry.pop("home_channel", None)

    save_config(cfg)
    _invalidate_hermes_config_caches()
    _verify_platform_saved(platform)
    _notify_gateway_platform_updated()
    return True


def patch_channel(platform: str, patch: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """部分更新指定平台的 home_channel 配置（只写传入的字段）。"""
    _ensure_hermes_agent_on_path()
    from hermes_cli.config import load_config, save_config

    _assert_config_writable()
    cfg = load_config()
    platforms = _ensure_mutable_platforms(cfg)

    if platform not in platforms:
        return None

    existing: Dict[str, Any] = platforms[platform]

    patch = dict(patch)

    # 先合并 extra 补丁，再处理 agent_id（避免 extra 整块覆盖掉 studio_agent_id）
    if "extra" in patch:
        new_ex = patch.pop("extra")
        base = dict(existing.get("extra") or {}) if isinstance(existing.get("extra"), dict) else {}
        if isinstance(new_ex, dict):
            base.update(new_ex)
        existing["extra"] = base

    if "agent_id" in patch:
        aid_raw = patch.pop("agent_id")
        ex = dict(existing.get("extra") or {}) if isinstance(existing.get("extra"), dict) else {}
        if aid_raw is None or (isinstance(aid_raw, str) and not str(aid_raw).strip()):
            ex.pop(_STUDIO_AGENT_EXTRA_KEY, None)
        else:
            aid = str(aid_raw).strip()
            _ensure_agent_unique_per_channel(platforms, platform, aid)
            ex[_STUDIO_AGENT_EXTRA_KEY] = aid
        existing["extra"] = ex

    # 处理 home_channel 的子字段
    home = dict(existing.get("home_channel", {}))
    for field in ("name", "chat_id", "platform"):
        if field in patch:
            home[field] = patch[field]
    if home:
        home["platform"] = platform  # 确保 platform 字段正确
        existing["home_channel"] = home

    # 其他顶级字段（不含 extra，已处理）
    for field in ("enabled", "token", "api_key", "reply_to_mode"):
        if field in patch:
            existing[field] = patch[field]

    platforms[platform] = existing
    _sync_extra_credentials_from_token_fields(platform, existing)

    save_config(cfg)
    _invalidate_hermes_config_caches()
    _verify_platform_saved(platform)
    _notify_gateway_platform_updated()

    return _platform_to_channel_info(platform, platforms[platform])
