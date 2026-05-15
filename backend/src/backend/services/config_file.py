"""配置文件 ~/.hermes/config.yaml 读写模块。

对应 Spring Boot Service 层 — 完整配置的读取、保存、环境变量管理。
"""

from __future__ import annotations

import logging
from typing import Any

from hermes_cli.config import (
    DEFAULT_CONFIG,
    load_config,
    save_config,
    load_env,
    save_env_value,
    remove_env_value,
    get_config_path,
)
from backend.services.model_config import get_models_list_for_ui

_log = logging.getLogger(__name__)


# ── 读取配置 ────────────────────────────────────────────────────────────────

def get_settings() -> dict[str, Any]:
    """读取完整配置供设置页面展示（GET /api/settings 的业务逻辑）。

    包含 camelCase -> snake_case 转换及敏感信息脱敏。
    """
    cfg = load_config()
    env_vars = load_env()
    config_exists = get_config_path().exists()

    # ── Models（与 GET /api/models 同源：_get_model_config）──────────────────
    models = get_models_list_for_ui(cfg, env_vars)

    # ── 各子配置（公用默认值） ──────────────────────────────────────────────
    def _cfg(key: str) -> dict:
        """获取配置项，若不存在则使用 DEFAULT_CONFIG 中的默认值。"""
        return cfg.get(key, DEFAULT_CONFIG.get(key, {}))

    def _str(cfg: dict, snake_key: str, default: str = "") -> str:
        """读取字符串配置，带默认值。"""
        return cfg.get(snake_key, default)

    def _int(cfg: dict, snake_key: str, default: int = 0) -> int:
        """读取整数配置，带默认值。"""
        return cfg.get(snake_key, default)

    def _bool(cfg: dict, snake_key: str, default: bool = False) -> bool:
        """读取布尔配置，带默认值。"""
        return bool(cfg.get(snake_key, default))

    # ── Helper: auxiliary 子配置 ──────────────────────────────────────────
    def _aux(aux_key: str, sub_key: str) -> dict:
        """读取 auxiliary 子配置中指定键的值。"""
        return cfg.get("auxiliary", {}).get(aux_key, {}).get(sub_key, "")

    return {
        "models": models,
        "agent": {
            "maxTurns": _int(_cfg("agent"), "max_turns", 90),
            "gatewayTimeout": _int(_cfg("agent"), "gateway_timeout", 1800),
            "apiMaxRetries": _int(_cfg("agent"), "api_max_retries", 3),
            "toolUseEnforcement": _str(_cfg("agent"), "tool_use_enforcement", "auto"),
            "imageInputMode": _str(_cfg("agent"), "image_input_mode", "auto"),
        },
        "terminal": {
            "backend": _str(_cfg("terminal"), "backend", "local"),
            "cwd": _str(_cfg("terminal"), "cwd", "."),
            "timeout": _int(_cfg("terminal"), "timeout", 180),
            "persistentShell": _bool(_cfg("terminal"), "persistent_shell", True),
            "dockerImage": _str(_cfg("terminal"), "docker_image", "nikolaik/python-nodejs:python3.11-nodejs20"),
            "containerCpu": _int(_cfg("terminal"), "container_cpu", 1),
            "containerMemory": _int(_cfg("terminal"), "container_memory", 5120),
        },
        "tts": {
            "enabled": _bool(_cfg("tts"), "enabled", True),
            "provider": _str(_cfg("tts"), "provider", "edge"),
            "edgeVoice": _cfg("tts").get("edge", {}).get("voice", "en-US-AriaNeural"),
            "elevenlabsVoiceId": _cfg("tts").get("elevenlabs", {}).get("voice_id", "pNInz6obpgDQGcFmaJgB"),
        },
        "stt": {
            "enabled": _bool(_cfg("stt"), "enabled", True),
            "provider": _str(_cfg("stt"), "provider", "local"),
            "model": _cfg("stt").get("local", {}).get("model", "base") if isinstance(_cfg("stt").get("local"), dict) else "base",
        },
        "display": {
            "personality": _str(_cfg("display"), "personality", "kawaii"),
            "compact": _bool(_cfg("display"), "compact", False),
            "showReasoning": _bool(_cfg("display"), "show_reasoning", False),
            "streaming": _bool(_cfg("display"), "streaming", False),
            "finalResponseMarkdown": _str(_cfg("display"), "final_response_markdown", "strip"),
        },
        "security": {
            "allowPrivateUrls": _bool(_cfg("security"), "allow_private_urls", False),
            "redactSecrets": _bool(_cfg("security"), "redact_secrets", False),
            "tirithEnabled": _bool(_cfg("security"), "tirith_enabled", True),
        },
        "toolsets": cfg.get("toolsets", DEFAULT_CONFIG.get("toolsets", ["hermes-cli"])),
        "auxiliaryVision": {
            "provider": _aux("vision", "provider"),
            "model": _aux("vision", "model"),
            "baseUrl": _aux("vision", "base_url"),
            "apiKey": _aux("vision", "api_key"),
            "timeout": _int(_cfg("auxiliary").get("vision", {}), "timeout", 120),
            "extraBody": _cfg("auxiliary").get("vision", {}).get("extra_body", {}),
            "downloadTimeout": _int(_cfg("auxiliary").get("vision", {}), "download_timeout", 30),
        },
        "auxiliaryWebExtract": {
            "provider": _aux("web_extract", "provider"),
            "model": _aux("web_extract", "model"),
            "baseUrl": _aux("web_extract", "base_url"),
            "apiKey": _aux("web_extract", "api_key"),
            "timeout": _int(_cfg("auxiliary").get("web_extract", {}), "timeout", 360),
            "extraBody": _cfg("auxiliary").get("web_extract", {}).get("extra_body", {}),
        },
        "auxiliaryCompression": {
            "provider": _aux("compression", "provider"),
            "model": _aux("compression", "model"),
            "baseUrl": _aux("compression", "base_url"),
            "apiKey": _aux("compression", "api_key"),
            "timeout": _int(_cfg("auxiliary").get("compression", {}), "timeout", 120),
            "extraBody": _cfg("auxiliary").get("compression", {}).get("extra_body", {}),
        },
        "auxiliarySessionSearch": {
            "provider": _aux("session_search", "provider"),
            "model": _aux("session_search", "model"),
            "baseUrl": _aux("session_search", "base_url"),
            "apiKey": _aux("session_search", "api_key"),
            "timeout": _int(_cfg("auxiliary").get("session_search", {}), "timeout", 30),
            "extraBody": _cfg("auxiliary").get("session_search", {}).get("extra_body", {}),
            "maxConcurrency": _int(_cfg("auxiliary").get("session_search", {}), "max_concurrency", 3),
        },
        "auxiliarySkillsHub": {
            "provider": _aux("skills_hub", "provider"),
            "model": _aux("skills_hub", "model"),
            "baseUrl": _aux("skills_hub", "base_url"),
            "apiKey": _aux("skills_hub", "api_key"),
            "timeout": _int(_cfg("auxiliary").get("skills_hub", {}), "timeout", 30),
            "extraBody": _cfg("auxiliary").get("skills_hub", {}).get("extra_body", {}),
        },
        "auxiliaryApproval": {
            "provider": _aux("approval", "provider"),
            "model": _aux("approval", "model"),
            "baseUrl": _aux("approval", "base_url"),
            "apiKey": _aux("approval", "api_key"),
            "timeout": _int(_cfg("auxiliary").get("approval", {}), "timeout", 30),
            "extraBody": _cfg("auxiliary").get("approval", {}).get("extra_body", {}),
        },
        "auxiliaryMcp": {
            "provider": _aux("mcp", "provider"),
            "model": _aux("mcp", "model"),
            "baseUrl": _aux("mcp", "base_url"),
            "apiKey": _aux("mcp", "api_key"),
            "timeout": _int(_cfg("auxiliary").get("mcp", {}), "timeout", 30),
            "extraBody": _cfg("auxiliary").get("mcp", {}).get("extra_body", {}),
        },
        "auxiliaryTitleGeneration": {
            "provider": _aux("title_generation", "provider"),
            "model": _aux("title_generation", "model"),
            "baseUrl": _aux("title_generation", "base_url"),
            "apiKey": _aux("title_generation", "api_key"),
            "timeout": _int(_cfg("auxiliary").get("title_generation", {}), "timeout", 30),
            "extraBody": _cfg("auxiliary").get("title_generation", {}).get("extra_body", {}),
        },
        "auxiliaryCurator": {
            "provider": _aux("curator", "provider"),
            "model": _aux("curator", "model"),
            "baseUrl": _aux("curator", "base_url"),
            "apiKey": _aux("curator", "api_key"),
            "timeout": _int(_cfg("auxiliary").get("curator", {}), "timeout", 600),
            "extraBody": _cfg("auxiliary").get("curator", {}).get("extra_body", {}),
        },
        "browser": {
            "inactivityTimeout": _int(_cfg("browser"), "inactivity_timeout", 120),
            "commandTimeout": _int(_cfg("browser"), "command_timeout", 30),
            "recordSessions": _bool(_cfg("browser"), "record_sessions", False),
            "allowPrivateUrls": _bool(_cfg("browser"), "allow_private_urls", False),
            "autoLocalForPrivateUrls": _bool(_cfg("browser"), "auto_local_for_private_urls", True),
            "cdpUrl": _str(_cfg("browser"), "cdp_url", ""),
            "dialogPolicy": _str(_cfg("browser"), "dialog_policy", "must_respond"),
            "dialogTimeoutS": _int(_cfg("browser"), "dialog_timeout_s", 300),
            "camofox": {
                "managedPersistence": _bool(_cfg("browser").get("camofox", {}), "managed_persistence", False),
            },
        },
        "delegation": {
            "model": _str(_cfg("delegation"), "model", ""),
            "provider": _str(_cfg("delegation"), "provider", ""),
            "baseUrl": _str(_cfg("delegation"), "base_url", ""),
            "apiKey": _str(_cfg("delegation"), "api_key", ""),
            "inheritMcpToolsets": _bool(_cfg("delegation"), "inherit_mcp_toolsets", True),
            "maxIterations": _int(_cfg("delegation"), "max_iterations", 50),
            "childTimeoutSeconds": _int(_cfg("delegation"), "child_timeout_seconds", 600),
            "reasoningEffort": _str(_cfg("delegation"), "reasoning_effort", ""),
            "maxConcurrentChildren": _int(_cfg("delegation"), "max_concurrent_children", 3),
            "maxSpawnDepth": _int(_cfg("delegation"), "max_spawn_depth", 1),
            "orchestratorEnabled": _bool(_cfg("delegation"), "orchestrator_enabled", True),
            "subagentAutoApprove": _bool(_cfg("delegation"), "subagent_auto_approve", False),
        },
        "discord": {
            "requireMention": _bool(_cfg("discord"), "require_mention", True),
            "freeResponseChannels": _str(_cfg("discord"), "free_response_channels", ""),
            "allowedChannels": _str(_cfg("discord"), "allowed_channels", ""),
            "autoThread": _bool(_cfg("discord"), "auto_thread", True),
            "reactions": _bool(_cfg("discord"), "reactions", True),
            "channelPrompts": _cfg("discord").get("channel_prompts", {}),
            "serverActions": _str(_cfg("discord"), "server_actions", ""),
        },
        "telegram": {
            "reactions": _bool(_cfg("telegram"), "reactions", False),
            "channelPrompts": _cfg("telegram").get("channel_prompts", {}),
        },
        "slack": {
            "channelPrompts": _cfg("slack").get("channel_prompts", {}),
        },
        "mattermost": {
            "channelPrompts": _cfg("mattermost").get("channel_prompts", {}),
        },
        "sessions": {
            "autoPrune": _bool(_cfg("sessions"), "auto_prune", False),
            "retentionDays": _int(_cfg("sessions"), "retention_days", 90),
            "vacuumAfterPrune": _bool(_cfg("sessions"), "vacuum_after_prune", True),
            "minIntervalHours": _int(_cfg("sessions"), "min_interval_hours", 24),
        },
        "logging": {
            "level": _str(_cfg("logging"), "level", "INFO"),
            "maxSizeMb": _int(_cfg("logging"), "max_size_mb", 5),
            "backupCount": _int(_cfg("logging"), "backup_count", 3),
        },
        "memory": {
            "memoryEnabled": _bool(_cfg("memory"), "memory_enabled", True),
            "userProfileEnabled": _bool(_cfg("memory"), "user_profile_enabled", True),
            "memoryCharLimit": _int(_cfg("memory"), "memory_char_limit", 2200),
            "userCharLimit": _int(_cfg("memory"), "user_char_limit", 1375),
            "provider": _str(_cfg("memory"), "provider", ""),
        },
        "voice": {
            "recordKey": _str(_cfg("voice"), "record_key", "ctrl+b"),
            "maxRecordingSeconds": _int(_cfg("voice"), "max_recording_seconds", 120),
            "autoTts": _bool(_cfg("voice"), "auto_tts", False),
            "beepEnabled": _bool(_cfg("voice"), "beep_enabled", True),
            "silenceThreshold": _int(_cfg("voice"), "silence_threshold", 200),
            "silenceDuration": _cfg("voice").get("silence_duration", 3.0),
        },
        "context": {
            "engine": _str(_cfg("context"), "engine", "compressor"),
        },
        "checkpoints": {
            "enabled": _bool(_cfg("checkpoints"), "enabled", True),
            "maxSnapshots": _int(_cfg("checkpoints"), "max_snapshots", 50),
            "autoPrune": _bool(_cfg("checkpoints"), "auto_prune", False),
            "retentionDays": _int(_cfg("checkpoints"), "retention_days", 7),
            "deleteOrphans": _bool(_cfg("checkpoints"), "delete_orphans", True),
            "minIntervalHours": _int(_cfg("checkpoints"), "min_interval_hours", 24),
        },
        "cron": {
            "wrapResponse": _bool(_cfg("cron"), "wrap_response", True),
            "maxParallelJobs": _cfg("cron").get("max_parallel_jobs"),
        },
        "skills": {
            "externalDirs": _cfg("skills").get("external_dirs", []),
            "templateVars": _bool(_cfg("skills"), "template_vars", True),
            "inlineShell": _bool(_cfg("skills"), "inline_shell", False),
            "inlineShellTimeout": _int(_cfg("skills"), "inline_shell_timeout", 10),
            "guardAgentCreated": _bool(_cfg("skills"), "guard_agent_created", False),
        },
        "approvals": {
            "mode": _str(_cfg("approvals"), "mode", "manual"),
            "timeout": _int(_cfg("approvals"), "timeout", 60),
            "cronMode": _str(_cfg("approvals"), "cron_mode", "deny"),
            "mcpReloadConfirm": _bool(_cfg("approvals"), "mcp_reload_confirm", True),
        },
        "modelCatalog": {
            "enabled": _bool(_cfg("model_catalog"), "enabled", True),
            "url": _str(_cfg("model_catalog"), "url", "https://hermes-agent.nousresearch.com/docs/api/model-catalog.json"),
            "ttlHours": _int(_cfg("model_catalog"), "ttl_hours", 24),
            "providers": _cfg("model_catalog").get("providers", {}),
        },
        "network": {
            "forceIpv4": _bool(_cfg("network"), "force_ipv4", False),
        },
        "commandAllowlist": cfg.get("command_allowlist", DEFAULT_CONFIG.get("command_allowlist", [])),
        "quickCommands": cfg.get("quick_commands", DEFAULT_CONFIG.get("quick_commands", {})),
        "hooks": {
            "hooks": _cfg("hooks") if isinstance(_cfg("hooks"), dict) else {},
            "hooksAutoAccept": _bool(cfg, "hooks_auto_accept", False),
        },
        "personalities": _cfg("personalities") if isinstance(_cfg("personalities"), dict) else {},
        "codeExecution": {
            "mode": _str(_cfg("code_execution"), "mode", "project"),
        },
        "sessionReset": {
            "mode": _str(_cfg("session_reset"), "mode", "both"),
            "idleMinutes": _int(_cfg("session_reset"), "idle_minutes", 1440),
            "atHour": _int(_cfg("session_reset"), "at_hour", 4),
        },
        "toolOutput": {
            "maxBytes": _int(_cfg("tool_output"), "max_bytes", 50000),
            "maxLines": _int(_cfg("tool_output"), "max_lines", 2000),
            "maxLineLength": _int(_cfg("tool_output"), "max_line_length", 2000),
        },
        "compression": {
            "enabled": _bool(_cfg("compression"), "enabled", True),
            "threshold": _cfg("compression").get("threshold", 0.5),
            "targetRatio": _cfg("compression").get("target_ratio", 0.2),
            "protectLastN": _int(_cfg("compression"), "protect_last_n", 20),
            "hygieneHardMessageLimit": _int(_cfg("compression"), "hygiene_hard_message_limit", 400),
        },
        "humanDelay": {
            "mode": _str(_cfg("human_delay"), "mode", "off"),
            "minMs": _int(_cfg("human_delay"), "min_ms", 800),
            "maxMs": _int(_cfg("human_delay"), "max_ms", 2500),
        },
        "dashboard": {
            "theme": _str(_cfg("dashboard"), "theme", "default"),
        },
        "privacy": {
            "redactPii": _bool(_cfg("privacy"), "redact_pii", False),
        },
        "honcho": _cfg("honcho") if isinstance(_cfg("honcho"), dict) else {},
        "timezone": _str(cfg, "timezone", ""),
        "onboarding": {
            "seen": _cfg("onboarding").get("seen", {}) if isinstance(_cfg("onboarding"), dict) else {},
        },
        "updates": {
            "preUpdateBackup": _bool(_cfg("updates"), "pre_update_backup", False),
            "backupKeep": _int(_cfg("updates"), "backup_keep", 5),
        },
        "bedrock": {
            "region": _str(_cfg("bedrock"), "region", ""),
            "discovery": {
                "enabled": _bool(_cfg("bedrock").get("discovery", {}), "enabled", True),
                "providerFilter": _cfg("bedrock").get("discovery", {}).get("provider_filter", []),
                "refreshInterval": _int(_cfg("bedrock").get("discovery", {}), "refresh_interval", 3600),
            },
            "guardrail": {
                "guardrailIdentifier": _str(_cfg("bedrock").get("guardrail", {}), "guardrail_identifier", ""),
                "guardrailVersion": _str(_cfg("bedrock").get("guardrail", {}), "guardrail_version", ""),
                "streamProcessingMode": _str(_cfg("bedrock").get("guardrail", {}), "stream_processing_mode", "async"),
                "trace": _str(_cfg("bedrock").get("guardrail", {}), "trace", "disabled"),
            },
        },
        "openrouter": {
            "responseCache": _bool(_cfg("openrouter"), "response_cache", True),
            "responseCacheTtl": _int(_cfg("openrouter"), "response_cache_ttl", 300),
        },
        "toolLoopGuardrails": {
            "warningsEnabled": _bool(_cfg("tool_loop_guardrails"), "warnings_enabled", True),
            "hardStopEnabled": _bool(_cfg("tool_loop_guardrails"), "hard_stop_enabled", False),
            "warnAfter": _cfg("tool_loop_guardrails").get("warn_after", {}),
            "hardStopAfter": _cfg("tool_loop_guardrails").get("hard_stop_after", {}),
        },
        "fileReadMaxChars": _cfg("file_read_max_chars"),
        "promptCaching": {
            "cacheTtl": _str(_cfg("prompt_caching"), "cache_ttl", "5m"),
        },
        "whatsapp": _cfg("whatsapp") if isinstance(_cfg("whatsapp"), dict) else {},
        "configExists": config_exists,
    }


# ── 保存配置 ────────────────────────────────────────────────────────────────

def save_settings(body: Any) -> dict[str, str]:
    """保存完整配置（PUT /api/settings 的业务逻辑）。

    包含 camelCase -> snake_case 转换及环境变量分离存储。
    """
    cfg = load_config()

    # ── Models ──────────────────────────────────────────────────────────────
    default_model = None
    fallback_providers = []

    for m in body.models:
        if m.isDefault:
            default_model = m
        elif m.provider and m.name:
            fallback_providers.append(m.provider)

    if default_model:
        cfg["model"] = {
            "provider": default_model.provider,
            "default": default_model.name,
            "base_url": default_model.baseUrl,
        }
        if default_model.apiKey:
            key_name = f"{default_model.provider.upper().replace('-', '_')}_API_KEY"
            save_env_value(key_name, default_model.apiKey)

    if fallback_providers:
        cfg["fallback_providers"] = fallback_providers
    else:
        cfg.pop("fallback_providers", None)

    # ── Agent ──────────────────────────────────────────────────────────────
    cfg["agent"] = {
        "max_turns": body.agent.maxTurns,
        "gateway_timeout": body.agent.gatewayTimeout,
        "api_max_retries": body.agent.apiMaxRetries,
        "tool_use_enforcement": body.agent.toolUseEnforcement,
        "image_input_mode": body.agent.imageInputMode,
    }

    # ── Terminal ───────────────────────────────────────────────────────────
    cfg["terminal"] = {
        "backend": body.terminal.backend,
        "cwd": body.terminal.cwd,
        "timeout": body.terminal.timeout,
        "persistent_shell": body.terminal.persistentShell,
        "docker_image": body.terminal.dockerImage,
        "container_cpu": body.terminal.containerCpu,
        "container_memory": body.terminal.containerMemory,
    }

    # ── TTS ────────────────────────────────────────────────────────────────
    cfg["tts"] = {
        "enabled": body.tts.enabled,
        "provider": body.tts.provider,
        "edge": {"voice": body.tts.edgeVoice},
        "elevenlabs": {"voice_id": body.tts.elevenlabsVoiceId},
    }

    # ── STT ───────────────────────────────────────────────────────────────
    cfg["stt"] = {
        "enabled": body.stt.enabled,
        "provider": body.stt.provider,
        "local": {"model": body.stt.model},
    }

    # ── Display ────────────────────────────────────────────────────────────
    cfg["display"] = {
        "personality": body.display.personality,
        "compact": body.display.compact,
        "show_reasoning": body.display.showReasoning,
        "streaming": body.display.streaming,
        "final_response_markdown": body.display.finalResponseMarkdown,
    }

    # ── Security ───────────────────────────────────────────────────────────
    cfg["security"] = {
        "allow_private_urls": body.security.allowPrivateUrls,
        "redact_secrets": body.security.redactSecrets,
        "tirith_enabled": body.security.tirithEnabled,
    }

    # ── Toolsets ───────────────────────────────────────────────────────────
    cfg["toolsets"] = body.toolsets

    # ── Auxiliary ──────────────────────────────────────────────────────────
    def _save_aux(body_field, cfg_key: str, api_key_name: str | None = None) -> None:
        if body_field is not None:
            cfg.setdefault("auxiliary", {})[cfg_key] = {
                "provider": body_field.provider,
                "model": body_field.model,
                "base_url": body_field.baseUrl,
                "api_key": body_field.apiKey,
                "timeout": body_field.timeout,
                "extra_body": body_field.extraBody,
            }
            if api_key_name and body_field.apiKey:
                save_env_value(api_key_name, body_field.apiKey)

    _save_aux(body.auxiliaryVision, "vision", "AUXILIARY_VISION_API_KEY")
    _save_aux(body.auxiliaryWebExtract, "web_extract", "AUXILIARY_WEB_EXTRACT_API_KEY")
    _save_aux(body.auxiliaryCompression, "compression")
    _save_aux(body.auxiliarySessionSearch, "session_search")
    _save_aux(body.auxiliarySkillsHub, "skills_hub")
    _save_aux(body.auxiliaryApproval, "approval")
    _save_aux(body.auxiliaryMcp, "mcp")
    _save_aux(body.auxiliaryTitleGeneration, "title_generation")
    _save_aux(body.auxiliaryCurator, "curator")

    # ── Browser ────────────────────────────────────────────────────────────
    if body.browser is not None:
        cfg["browser"] = {
            "inactivity_timeout": body.browser.inactivityTimeout,
            "command_timeout": body.browser.commandTimeout,
            "record_sessions": body.browser.recordSessions,
            "allow_private_urls": body.browser.allowPrivateUrls,
            "auto_local_for_private_urls": body.browser.autoLocalForPrivateUrls,
            "cdp_url": body.browser.cdpUrl,
            "dialog_policy": body.browser.dialogPolicy,
            "dialog_timeout_s": body.browser.dialogTimeoutS,
            "camofox": {
                "managed_persistence": body.browser.camofox.managedPersistence,
            },
        }

    # ── Delegation ─────────────────────────────────────────────────────────
    if body.delegation is not None:
        cfg["delegation"] = {
            "model": body.delegation.model,
            "provider": body.delegation.provider,
            "base_url": body.delegation.baseUrl,
            "api_key": body.delegation.apiKey,
            "inherit_mcp_toolsets": body.delegation.inheritMcpToolsets,
            "max_iterations": body.delegation.maxIterations,
            "child_timeout_seconds": body.delegation.childTimeoutSeconds,
            "reasoning_effort": body.delegation.reasoningEffort,
            "max_concurrent_children": body.delegation.maxConcurrentChildren,
            "max_spawn_depth": body.delegation.maxSpawnDepth,
            "orchestrator_enabled": body.delegation.orchestratorEnabled,
            "subagent_auto_approve": body.delegation.subagentAutoApprove,
        }
        if body.delegation.apiKey:
            save_env_value("DELEGATION_API_KEY", body.delegation.apiKey)

    # ── Discord ─────────────────────────────────────────────────────────────
    if body.discord is not None:
        cfg["discord"] = {
            "require_mention": body.discord.requireMention,
            "free_response_channels": body.discord.freeResponseChannels,
            "allowed_channels": body.discord.allowedChannels,
            "auto_thread": body.discord.autoThread,
            "reactions": body.discord.reactions,
            "channel_prompts": body.discord.channelPrompts,
            "server_actions": body.discord.serverActions,
        }

    # ── Telegram ────────────────────────────────────────────────────────────
    if body.telegram is not None:
        cfg["telegram"] = {
            "reactions": body.telegram.reactions,
            "channel_prompts": body.telegram.channelPrompts,
        }

    # ── Slack ──────────────────────────────────────────────────────────────
    if body.slack is not None:
        cfg["slack"] = {"channel_prompts": body.slack.channelPrompts}

    # ── Mattermost ──────────────────────────────────────────────────────────
    if body.mattermost is not None:
        cfg["mattermost"] = {"channel_prompts": body.mattermost.channelPrompts}

    # ── Sessions ───────────────────────────────────────────────────────────
    if body.sessions is not None:
        cfg["sessions"] = {
            "auto_prune": body.sessions.autoPrune,
            "retention_days": body.sessions.retentionDays,
            "vacuum_after_prune": body.sessions.vacuumAfterPrune,
            "min_interval_hours": body.sessions.minIntervalHours,
        }

    # ── Logging ─────────────────────────────────────────────────────────────
    if body.logging is not None:
        cfg["logging"] = {
            "level": body.logging.level,
            "max_size_mb": body.logging.maxSizeMb,
            "backup_count": body.logging.backupCount,
        }

    # ── Memory ─────────────────────────────────────────────────────────────
    if body.memory is not None:
        cfg["memory"] = {
            "memory_enabled": body.memory.memoryEnabled,
            "user_profile_enabled": body.memory.userProfileEnabled,
            "memory_char_limit": body.memory.memoryCharLimit,
            "user_char_limit": body.memory.userCharLimit,
            "provider": body.memory.provider,
        }

    # ── Voice ───────────────────────────────────────────────────────────────
    if body.voice is not None:
        cfg["voice"] = {
            "record_key": body.voice.recordKey,
            "max_recording_seconds": body.voice.maxRecordingSeconds,
            "auto_tts": body.voice.autoTts,
            "beep_enabled": body.voice.beepEnabled,
            "silence_threshold": body.voice.silenceThreshold,
            "silence_duration": body.voice.silenceDuration,
        }

    # ── Context ─────────────────────────────────────────────────────────────
    if body.context is not None:
        cfg["context"] = {"engine": body.context.engine}

    # ── Checkpoints ─────────────────────────────────────────────────────────
    if body.checkpoints is not None:
        cfg["checkpoints"] = {
            "enabled": body.checkpoints.enabled,
            "max_snapshots": body.checkpoints.maxSnapshots,
            "auto_prune": body.checkpoints.autoPrune,
            "retention_days": body.checkpoints.retentionDays,
            "delete_orphans": body.checkpoints.deleteOrphans,
            "min_interval_hours": body.checkpoints.minIntervalHours,
        }

    # ── Cron ────────────────────────────────────────────────────────────────
    if body.cron is not None:
        cfg["cron"] = {
            "wrap_response": body.cron.wrapResponse,
            "max_parallel_jobs": body.cron.maxParallelJobs,
        }

    # ── Skills ──────────────────────────────────────────────────────────────
    if body.skills is not None:
        cfg["skills"] = {
            "external_dirs": body.skills.externalDirs,
            "template_vars": body.skills.templateVars,
            "inline_shell": body.skills.inlineShell,
            "inline_shell_timeout": body.skills.inlineShellTimeout,
            "guard_agent_created": body.skills.guardAgentCreated,
        }

    # ── Approvals ───────────────────────────────────────────────────────────
    if body.approvals is not None:
        cfg["approvals"] = {
            "mode": body.approvals.mode,
            "timeout": body.approvals.timeout,
            "cron_mode": body.approvals.cronMode,
            "mcp_reload_confirm": body.approvals.mcpReloadConfirm,
        }

    # ── Model Catalog ────────────────────────────────────────────────────────
    if body.modelCatalog is not None:
        cfg["model_catalog"] = {
            "enabled": body.modelCatalog.enabled,
            "url": body.modelCatalog.url,
            "ttl_hours": body.modelCatalog.ttlHours,
            "providers": body.modelCatalog.providers,
        }

    # ── Network ─────────────────────────────────────────────────────────────
    if body.network is not None:
        cfg["network"] = {"force_ipv4": body.network.forceIpv4}

    # ── Command Allowlist ────────────────────────────────────────────────────
    if body.commandAllowlist is not None:
        cfg["command_allowlist"] = body.commandAllowlist

    # ── Quick Commands ──────────────────────────────────────────────────────
    if body.quickCommands is not None:
        cfg["quick_commands"] = body.quickCommands

    # ── Hooks ───────────────────────────────────────────────────────────────
    if body.hooks is not None:
        cfg["hooks"] = body.hooks.hooks
        cfg["hooks_auto_accept"] = body.hooks.hooksAutoAccept

    # ── Personalities ───────────────────────────────────────────────────────
    if body.personalities is not None:
        cfg["personalities"] = body.personalities

    # ── Code Execution ─────────────────────────────────────────────────────
    if body.codeExecution is not None:
        cfg["code_execution"] = {"mode": body.codeExecution.mode}

    # ── Session Reset ──────────────────────────────────────────────────────
    if body.sessionReset is not None:
        cfg["session_reset"] = {
            "mode": body.sessionReset.mode,
            "idle_minutes": body.sessionReset.idleMinutes,
            "at_hour": body.sessionReset.atHour,
        }

    # ── Tool Output ─────────────────────────────────────────────────────────
    if body.toolOutput is not None:
        cfg["tool_output"] = {
            "max_bytes": body.toolOutput.maxBytes,
            "max_lines": body.toolOutput.maxLines,
            "max_line_length": body.toolOutput.maxLineLength,
        }

    # ── Compression ─────────────────────────────────────────────────────────
    if body.compression is not None:
        cfg["compression"] = {
            "enabled": body.compression.enabled,
            "threshold": body.compression.threshold,
            "target_ratio": body.compression.targetRatio,
            "protect_last_n": body.compression.protectLastN,
            "hygiene_hard_message_limit": body.compression.hygieneHardMessageLimit,
        }

    # ── Human Delay ─────────────────────────────────────────────────────────
    if body.humanDelay is not None:
        cfg["human_delay"] = {
            "mode": body.humanDelay.mode,
            "min_ms": body.humanDelay.minMs,
            "max_ms": body.humanDelay.maxMs,
        }

    # ── Dashboard ────────────────────────────────────────────────────────────
    if body.dashboard is not None:
        cfg["dashboard"] = {"theme": body.dashboard.theme}

    # ── Privacy ─────────────────────────────────────────────────────────────
    if body.privacy is not None:
        cfg["privacy"] = {"redact_pii": body.privacy.redactPii}

    # ── Honcho ───────────────────────────────────────────────────────────────
    if body.honcho is not None:
        cfg["honcho"] = body.honcho

    # ── Timezone ────────────────────────────────────────────────────────────
    if body.timezone is not None:
        cfg["timezone"] = body.timezone

    # ── Onboarding ──────────────────────────────────────────────────────────
    if body.onboarding is not None:
        cfg["onboarding"] = {"seen": body.onboarding.seen}

    # ── Updates ─────────────────────────────────────────────────────────────
    if body.updates is not None:
        cfg["updates"] = {
            "pre_update_backup": body.updates.preUpdateBackup,
            "backup_keep": body.updates.backupKeep,
        }

    # ── Bedrock ─────────────────────────────────────────────────────────────
    if body.bedrock is not None:
        cfg["bedrock"] = {
            "region": body.bedrock.region,
            "discovery": {
                "enabled": body.bedrock.discovery.enabled,
                "provider_filter": body.bedrock.discovery.providerFilter,
                "refresh_interval": body.bedrock.discovery.refreshInterval,
            },
            "guardrail": {
                "guardrail_identifier": body.bedrock.guardrail.guardrailIdentifier,
                "guardrail_version": body.bedrock.guardrail.guardrailVersion,
                "stream_processing_mode": body.bedrock.guardrail.streamProcessingMode,
                "trace": body.bedrock.guardrail.trace,
            },
        }

    # ── Openrouter ─────────────────────────────────────────────────────────
    if body.openrouter is not None:
        cfg["openrouter"] = {
            "response_cache": body.openrouter.responseCache,
            "response_cache_ttl": body.openrouter.responseCacheTtl,
        }

    # ── Tool Loop Guardrails ────────────────────────────────────────────────
    if body.toolLoopGuardrails is not None:
        cfg["tool_loop_guardrails"] = {
            "warnings_enabled": body.toolLoopGuardrails.warningsEnabled,
            "hard_stop_enabled": body.toolLoopGuardrails.hardStopEnabled,
            "warn_after": body.toolLoopGuardrails.warnAfter,
            "hard_stop_after": body.toolLoopGuardrails.hardStopAfter,
        }

    # ── File read max chars ─────────────────────────────────────────────────
    if body.fileReadMaxChars is not None:
        cfg["file_read_max_chars"] = body.fileReadMaxChars

    # ── Prompt Caching ─────────────────────────────────────────────────────
    if body.promptCaching is not None:
        cfg["prompt_caching"] = {"cache_ttl": body.promptCaching.cacheTtl}

    save_config(cfg)
    return {"ok": True, "message": "Settings saved"}


# ── 环境变量管理 ───────────────────────────────────────────────────────────

def get_env_vars() -> dict[str, str]:
    """读取所有环境变量（GET /api/settings/env-vars）。"""
    return load_env()


def update_env_var(key: str, value: str) -> dict[str, str]:
    """更新指定环境变量（PUT /api/settings/env-vars）。"""
    save_env_value(key, value)
    return {"ok": True}


def delete_env_var(key: str) -> dict[str, str]:
    """删除指定环境变量（DELETE /api/settings/env-vars）。"""
    remove_env_value(key)
    return {"ok": True}


def check_config() -> dict[str, bool]:
    """检查配置状态（GET /api/settings/check）。"""
    from hermes_cli.config import is_managed, get_config_path
    cfg = load_config()
    has_model = bool(cfg.get("model"))
    has_api_key = bool(load_env().get(f'{cfg.get("model", {}).get("provider", "").upper().replace("-", "_")}_API_KEY', ""))
    return {
        "configured": is_managed(),
        "hasModel": has_model,
        "hasApiKey": has_api_key,
    }
