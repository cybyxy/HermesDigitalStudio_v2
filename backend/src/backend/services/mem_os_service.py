"""MemOS 集成服务 — MOS 单例封装。

提供 per-agent 的 MemOS (MemoryOS 2.0.15) 实例生命周期管理，
包括内存添加、语义搜索、知识聊天。

使用::

    from backend.services.mem_os_service import (
        get_mos_for_agent,
        mos_search,
        mos_add_text,
    )

    mos = get_mos_for_agent("agent-coder")
    results = mos.search("React 状态管理最佳实践", top_k=5)
"""

from __future__ import annotations

import logging
import os
import threading
from pathlib import Path
from typing import Any

_log = logging.getLogger(__name__)

# ── HuggingFace 离线/镜像配置 ──────────────────────────────────────────────
# 若本地已有模型缓存，启用 HF_HUB_OFFLINE 跳过网络校验
# 否则设置 hf-mirror.com 作为下载源
def _configure_huggingface_env() -> None:
    if os.environ.get("HF_HUB_OFFLINE"):
        return
    # 检查关键模型是否已缓存
    try:
        from huggingface_hub import try_to_load_from_cache
        cached = try_to_load_from_cache(
            repo_id="sentence-transformers/all-MiniLM-L6-v2",
            filename="config.json",
        )
        if cached:
            os.environ["HF_HUB_OFFLINE"] = "1"
            return
    except Exception:
        pass
    os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")

_configure_huggingface_env()


def prewarm_embedding_model() -> None:
    """预加载 sentence-transformer 嵌入模型到内存，避免首次 MemOS 搜索延迟。

    优先使用本地缓存（``local_files_only=True``），只在模型未缓存时联网下载。
    这避免了在国内网络环境下每次启动都尝试连 huggingface.co 导致超时。
    """
    try:
        from sentence_transformers import SentenceTransformer

        model = None
        # 1. 首先尝试纯离线加载（本地已缓存时立即返回，不联网）
        try:
            model = SentenceTransformer(
                "sentence-transformers/all-MiniLM-L6-v2",
                local_files_only=True,
            )
        except Exception:
            _log.info("mem_os_service: model not cached, downloading...")
            # 2. 未缓存时回退到联网下载（使用 HF 镜像）
            model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")

        if model:
            _log.info(
                "mem_os_service: embedding model prewarmed, dim=%d",
                model.get_sentence_embedding_dimension(),
            )
    except Exception as e:
        _log.warning("mem_os_service: embedding model prewarm failed (non-fatal): %s", e)


# ── 全局缓存 ──────────────────────────────────────────────────────────────────
_mos_cache: dict[str, Any] = {}
_cache_lock = threading.Lock()
_memos_dir_cached: str | None = None  # 缓存 MEMOS_DIR，避免重复导入

# ── 嵌入模型配置（sentence_transformer 本地模型，无需外部 API）───────────────
_DEFAULT_EMBEDDING_MODEL = "all-MiniLM-L6-v2"   # 384-dimensional, ~80MB
_DEFAULT_EMBEDDING_DIMS = 384


# ═══════════════════════════════════════════════════════════════════════════════════
# 私有辅助函数
# ═══════════════════════════════════════════════════════════════════════════════════


def _load_hermes_env() -> dict[str, str]:
    """从 ~/.hermes/config.yaml + ~/.hermes/.env 自动读取配置。

    使用 hermes_cli 内置的 load_env() + read_raw_config()，返回：
    - 所有 .env 中的环境变量
    - 合并后的 env（.env 值注入 os.environ）
    """
    env_vars: dict[str, str] = {}

    # 尝试使用 hermes_cli 的标准 API
    try:
        from hermes_cli.config import load_env as _hermes_load_env
        env_vars = _hermes_load_env()
        # 写入 os.environ 以便后续代码使用
        for k, v in env_vars.items():
            if k and k not in os.environ:
                os.environ[str(k)] = str(v)
        return env_vars
    except ImportError:
        pass

    # fallback：手动解析 .env 文件
    env_path = Path.home() / ".hermes" / ".env"
    if env_path.is_file():
        try:
            for line in env_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                key = key.strip()
                if key:
                    env_vars[key] = value.strip()
                    if key not in os.environ:
                        os.environ[key] = value.strip()
        except Exception:
            pass

    return env_vars


def _resolve_llm_credentials(agent_id: str = "") -> dict[str, str]:
    """从 ~/.hermes/config.yaml 和 ~/.hermes/.env 自动解析 LLM 凭证。

    逻辑：
    1. 读取 config.yaml，获取所有 provider 配置
    2. 筛选 transport=chat_completions 的 provider（MemOS 需要 OpenAI 兼容格式）
    3. 优先使用主 provider（若兼容），否则选第一个兼容 provider
    4. 从 .env 获取对应的 API key
    5. 若无兼容 provider，回退到 env 变量直接查找

    Returns:
        {"api_key": ..., "api_base": ..., "model": ...}
    """
    api_key = ""
    api_base = ""
    model = ""
    provider_name = ""

    # 1. 加载 .env
    _load_hermes_env()

    # 2. 读取 config.yaml（优先用 hermes_cli）
    raw_cfg: dict = {}
    try:
        from hermes_cli.config import read_raw_config as _hermes_read_raw
        raw_cfg = _hermes_read_raw()
    except ImportError:
        pass

    if not raw_cfg:
        # fallback：手动解析 config.yaml
        cfg_path = Path.home() / ".hermes" / "config.yaml"
        if cfg_path.is_file():
            try:
                import yaml
                with open(cfg_path) as f:
                    raw_cfg = yaml.safe_load(f) or {}
            except Exception:
                pass

    providers = raw_cfg.get("providers", {}) if raw_cfg else {}
    main_provider_slug = (raw_cfg.get("model", {}) or {}).get("provider", "")

    if providers:
        # 3. 优先使用主 provider（用户的偏好选择），处理所有 transport 类型
        _MINIMAX_OPENAI_API = "https://api.minimaxi.com/v1"

        if main_provider_slug and main_provider_slug in providers:
            main_cfg = providers[main_provider_slug]
            if isinstance(main_cfg, dict):
                transport = str(main_cfg.get("transport", "") or "")

                if transport == "chat_completions":
                    # 3a. 主 provider 是 OpenAI 兼容格式，直接使用
                    provider_name = main_provider_slug
                    api_base = str(main_cfg.get("api", "") or main_cfg.get("base_url", "") or "").strip()
                    model = str(main_cfg.get("default_model", "") or "").strip()
                    key_env = str(main_cfg.get("key_env", "") or "").strip()
                    if not key_env:
                        key_env = f"{main_provider_slug.upper().replace('-', '_')}_API_KEY"
                    api_key = os.environ.get(key_env, "").strip()

                elif transport == "anthropic_messages":
                    # 3b. 主 provider 是 MiniMax（anthropic_messages 格式）→ 转成 OpenAI 兼容
                    key_env = str(main_cfg.get("key_env", "") or "").strip()
                    if not key_env:
                        key_env = f"{main_provider_slug.upper().replace('-', '_')}_API_KEY"
                    api_key = os.environ.get(key_env, "").strip()
                    if api_key:
                        provider_name = main_provider_slug
                        api_base = _MINIMAX_OPENAI_API
                        model = str(main_cfg.get("default_model", "") or "").strip()
                        if not model:
                            model = "MiniMax-M2.7-highspeed"

        # 4. 回退：主 provider 无 API key → 尝试任意 chat_completions provider
        if not api_key:
            compat_providers: list[tuple[str, dict]] = []
            for slug, cfg in providers.items():
                t = cfg.get("transport", "") if isinstance(cfg, dict) else ""
                if t == "chat_completions":
                    compat_providers.append((str(slug), cfg))

            if compat_providers:
                chosen_slug, chosen_cfg = compat_providers[0]
                provider_name = chosen_slug
                api_base = str(chosen_cfg.get("api", "") or chosen_cfg.get("base_url", "") or "").strip()
                model = str(chosen_cfg.get("default_model", "") or "").strip()
                key_env_name = str(chosen_cfg.get("key_env", "") or "").strip()
                if not key_env_name:
                    key_env_name = f"{chosen_slug.upper().replace('-', '_')}_API_KEY"
                api_key = os.environ.get(key_env_name, "").strip()

        _log.info(
            "mem_os_service: auto-config: provider=%s api=%s model=%s key_len=%d",
            provider_name or "?", api_base or "?", model or "?", len(api_key or ""),
        )

    # 5. 若无兼容 provider，回退到 env 变量直接查找
    if not api_key:
        provider_map = {
            "OPENAI_API_KEY":      ("OPENAI_BASE_URL",      "https://api.openai.com/v1"),
            "DEEPSEEK_API_KEY":    ("DEEPSEEK_BASE_URL",    "https://api.deepseek.com/v1"),
            "MINIMAX_CN_API_KEY":  ("MINIMAX_BASE_URL",     "https://api.minimaxi.com/v1"),
            "OPENROUTER_API_KEY":  ("OPENROUTER_BASE_URL",  "https://openrouter.ai/api/v1"),
            "ANTHROPIC_API_KEY":   ("",                      ""),
            "HERMES_API_KEY":      ("HERMES_API_BASE",       ""),
        }
        for key_var, (url_var, fallback_url) in provider_map.items():
            k = os.environ.get(key_var, "").strip()
            if k:
                api_key = k
                if url_var:
                    api_base = os.environ.get(url_var, "").strip() or fallback_url
                elif fallback_url:
                    api_base = fallback_url
                break

    if not api_base:
        api_base = "https://api.openai.com/v1"

    # 6. 模型名：Agent DB > config.yaml > 自动推断
    if not model and agent_id:
        try:
            from backend.db.agent import AgentAvatarDAO
            info = AgentAvatarDAO.get_agent_model(agent_id)
            if info.get("model"):
                model = info["model"]
        except Exception:
            pass

    if not model:
        if "deepseek" in api_base.lower():
            model = "deepseek-chat"
        elif "minimaxi" in api_base.lower():
            model = "minimax-text-01"
        elif "openrouter" in api_base.lower():
            model = "openai/gpt-4o-mini"
        else:
            model = "gpt-4o-mini"

    return {"api_key": api_key, "api_base": api_base, "model": model, "provider": provider_name}


def _get_memos_dir() -> str:
    """获取 MemOS 数据根目录（缓存，避免重复导入 memos.settings 耗时 5s+）。

    优先使用项目根目录的 ``.memos/``（通过查找 ``backend/`` 父目录确定），
    确保在不同工作目录下（backend/ 或 backend/src/）数据位置一致。
    可用 ``studio.yaml: memos.dir`` 或环境变量 ``MEMOS_DIR`` 覆盖。
    """
    global _memos_dir_cached
    if _memos_dir_cached is not None:
        return _memos_dir_cached

    # 优先使用 studio.yaml 中的配置
    try:
        from backend.core.config import get_config
        cfg_dir = get_config().memos_dir
        if cfg_dir:
            _memos_dir_cached = cfg_dir
            _log.debug("mem_os_service: MEMOS_DIR from studio.yaml = %s", _memos_dir_cached)
            return _memos_dir_cached
    except Exception:
        pass

    # 优先检测项目根目录（通过查找 pyproject.toml 定位）
    # 注意：不能使用 (parent / "backend").is_dir() 作为标记，
    # 因为 backend/src/backend/ 本身就是一个 Python 包目录。
    _cwd = Path.cwd().resolve()
    for parent in [_cwd] + list(_cwd.parents):
        if (parent / "pyproject.toml").is_file():
            _proj_memos = parent / ".memos"
            _memos_dir_cached = str(_proj_memos)
            break

    if _memos_dir_cached is None:
        # 回退到 os.environ 或 memos.settings
        _env_dir = os.environ.get("MEMOS_DIR", "").strip()
        if _env_dir:
            _memos_dir_cached = _env_dir
        else:
            try:
                from memos import settings
                _memos_dir_cached = str(settings.MEMOS_DIR)
            except Exception:
                _memos_dir_cached = str(Path(".memos"))

    _log.debug("mem_os_service: MEMOS_DIR cached = %s", _memos_dir_cached)
    return _memos_dir_cached


def _resolve_qdrant_config(agent_id: str) -> dict:
    """解析 per-agent Qdrant 配置。

    检测顺序（优先级从高到低）：
    1. ``backend/studio.yaml`` → ``qdrant`` 段（Studio 自有配置）
    2. 环境变量 ``QDRANT_URL`` / ``QDRANT_HOST``
    3. 回退到本地文件模式 ``path``
    """
    safe_id = agent_id.replace("/", "_").replace(":", "_")
    _build = lambda **kw: {**kw, "collection_name": f"{safe_id}_memory",
                           "distance_metric": "cosine",
                           "vector_dimension": _DEFAULT_EMBEDDING_DIMS}

    # 1. 从 Studio 自有配置文件读取（优先级最高）
    try:
        from backend.core.config import get_config
        qdrant_cfg = get_config().qdrant_config
        if qdrant_cfg:
            qdrant_url = str(qdrant_cfg.get("url", "") or "").strip()
            if qdrant_url:
                return _build(url=qdrant_url,
                              api_key=str(qdrant_cfg.get("api_key", "") or "").strip() or None)
            qdrant_host = str(qdrant_cfg.get("host", "") or "").strip()
            if qdrant_host:
                return _build(host=qdrant_host,
                              port=int(qdrant_cfg.get("port", 6333)))
            qdrant_path = str(qdrant_cfg.get("path", "") or "").strip()
            if qdrant_path:
                return _build(path=str(Path(qdrant_path).expanduser()))
    except Exception:
        pass

    # 2. 回退：环境变量
    qdrant_url = os.environ.get("QDRANT_URL", "").strip()
    if qdrant_url:
        return _build(url=qdrant_url,
                      api_key=os.environ.get("QDRANT_API_KEY", "").strip() or None)

    qdrant_host = os.environ.get("QDRANT_HOST", "").strip()
    if qdrant_host:
        return _build(host=qdrant_host,
                      port=int(os.environ.get("QDRANT_PORT", "6333")))

    # 3. 最终回退：本地文件模式
    qdrant_path = str(Path(_get_memos_dir()) / "qdrant" / safe_id)
    return _build(path=qdrant_path)


def _resolve_qdrant_path(agent_id: str) -> str:
    """解析 per-agent Qdrant 本地文件路径（兼容旧代码）。"""
    safe_id = agent_id.replace("/", "_").replace(":", "_")
    return str(Path(_get_memos_dir()) / "qdrant" / safe_id)


def _build_mos_config(agent_id: str) -> Any:
    """构建 MemOS MOSConfig。

    复用 Agent LLM 配置（Chat）+ Qdrant 本地路径 + 本地 SentenceTransformer 嵌入。
    """
    creds = _resolve_llm_credentials(agent_id)
    qdrant_path = _resolve_qdrant_path(agent_id)
    safe_id = agent_id.replace("/", "_").replace(":", "_")

    from memos.configs.mem_os import MOSConfig

    openai_config = {
        "model_name_or_path": creds["model"],
        "temperature": 0.0,
        "max_tokens": 4096,
        "remove_think_prefix": True,
        "api_key": creds["api_key"],
        "api_base": creds["api_base"],
    }

    embedder_config = {
        "backend": "sentence_transformer",
        "config": {
            "model_name_or_path": _DEFAULT_EMBEDDING_MODEL,
            "trust_remote_code": True,
        },
    }

    return MOSConfig(
        user_id=safe_id,
        session_id=f"mos_{safe_id}_default",
        chat_model={
            "backend": "openai",
            "config": openai_config,
        },
        mem_reader={
            "backend": "simple_struct",
            "config": {
                "llm": {"backend": "openai", "config": openai_config},
                "embedder": embedder_config,
                "chunker": {
                    "backend": "markdown",
                    "config": {
                        "chunk_size": 512,
                        "chunk_overlap": 128,
                        "headers_to_split_on": [
                            ("#", "Header 1"),
                            ("##", "Header 2"),
                            ("###", "Header 3"),
                        ],
                        "strip_headers": False,
                        "recursive": False,
                    },
                },
            },
        },
        enable_textual_memory=True,
        top_k=5,
        max_turns_window=20,
        enable_mem_scheduler=False,
        PRO_MODE=False,
    )


def _build_cube_config(agent_id: str, config: Any) -> Any:
    """构建 per-agent 的 MemCube 配置（包含 Qdrant 向量库配置）。

    通过 ``_resolve_qdrant_config()`` 自动检测环境变量：
    - ``QDRANT_URL`` → 远程 Qdrant 服务（Cloud / Docker）
    - ``QDRANT_HOST`` → 自托管 Qdrant 服务
    - 无 env → 本地文件模式
    """
    creds = _resolve_llm_credentials(agent_id)
    safe_id = agent_id.replace("/", "_").replace(":", "_")

    from memos.configs.mem_cube import GeneralMemCubeConfig

    openai_config = {
        "model_name_or_path": creds["model"],
        "temperature": 0.0,
        "max_tokens": 4096,
        "remove_think_prefix": True,
        "api_key": creds["api_key"],
        "api_base": creds["api_base"],
    }

    embedder_config = {
        "backend": "sentence_transformer",
        "config": {
            "model_name_or_path": _DEFAULT_EMBEDDING_MODEL,
            "trust_remote_code": True,
        },
    }

    text_mem_config = {
        "backend": "general_text",
        "config": {
            "cube_id": f"{safe_id}_cube",
            "memory_filename": "textual_memory.json",
            "extractor_llm": {"backend": "openai", "config": openai_config},
            "vector_db": {
                "backend": "qdrant",
                "config": _resolve_qdrant_config(agent_id),
            },
            "embedder": embedder_config,
        },
    }

    return GeneralMemCubeConfig(
        user_id=safe_id,
        cube_id=f"{safe_id}_default_cube",
        text_mem=text_mem_config,
        act_mem={},
        para_mem={},
    )


# ═══════════════════════════════════════════════════════════════════════════════════
# 公开 API
# ═══════════════════════════════════════════════════════════════════════════════════


def get_mos_for_agent(agent_id: str) -> Any | None:
    """获取（或创建）per-agent 的 MOS 单例。

    MOS 实例被懒加载并缓存在进程内存中，多次调用返回同一实例。
    首次创建时会自动注册 default MemCube 并配置 Qdrant 本地向量库。

    Args:
        agent_id: Agent ID（如 "agent-coder"）

    Returns:
        MOS 实例，若 LLM 凭证缺失则返回 None。
    """
    safe_id = agent_id.replace("/", "_").replace(":", "_")

    with _cache_lock:
        if safe_id in _mos_cache:
            return _mos_cache[safe_id]

    # 检查 LLM 凭证
    creds = _resolve_llm_credentials(agent_id)
    if not creds["api_key"]:
        _log.warning(
            "mem_os_service: No API key found for agent=%s. "
            "Set OPENAI_API_KEY or OPENROUTER_API_KEY in environment.",
            agent_id,
        )
        return None

    _log.info("mem_os_service: Creating MOS instance for agent=%s", agent_id)

    try:
        from memos import MOS
        from memos.configs.mem_os import MOSConfig
        from memos.mem_cube.general import GeneralMemCube

        # 1. 构建 MOS 主配置
        mos_config = _build_mos_config(agent_id)
        mos = MOS(config=mos_config)
        _log.info(
            "mem_os_service: MOS initialized for user=%s model=%s",
            mos_config.user_id,
            mos_config.chat_model.config.get("model_name_or_path", "unknown"),
        )

        # 2. 创建并注册 MemCube（承载 Qdrant 向量库）
        try:
            cube_config = _build_cube_config(agent_id, mos_config)
            cube = GeneralMemCube(cube_config)
            mos.register_mem_cube(cube)
            _log.info(
                "mem_os_service: MemCube registered cube_id=%s qdrant_path=%s",
                cube_config.cube_id,
                _resolve_qdrant_path(agent_id),
            )
        except Exception as e:
            _log.warning(
                "mem_os_service: Failed to register MemCube for agent=%s: %s. "
                "Search will use MOS default.",
                agent_id, e,
            )

        with _cache_lock:
            _mos_cache[safe_id] = mos
        return mos

    except Exception as e:
        _log.error("mem_os_service: Failed to create MOS for agent=%s: %s", agent_id, e)
        return None


def mos_search(
    agent_id: str,
    query: str,
    top_k: int = 5,
    mode: str = "fast",
    session_id: str | None = None,
) -> list[str]:
    """在 Agent 的 MemOS 向量库中语义搜索相关记忆。

    Args:
        agent_id: Agent ID
        query: 搜索查询文本
        top_k: 返回结果数（默认 5）
        mode: 搜索模式 "fast"（默认）或 "fine"
        session_id: 可选 session 过滤

    Returns:
        匹配的记忆文本列表。失败时返回空列表。
    """
    mos = get_mos_for_agent(agent_id)
    if mos is None:
        return []

    try:
        result = mos.search(query=query, top_k=top_k, mode=mode, session_id=session_id)
        # MOSSearchResult: {"text_mem": [{"cube_id": ..., "memories": [...]}]}
        text_mems = result.get("text_mem", [])
        memories: list[str] = []
        for entry in text_mems:
            for mem in entry.get("memories", []):
                text = getattr(mem, "memory", "") or str(mem)
                if text.strip():
                    memories.append(text)
        return memories[:top_k]
    except Exception as e:
        _log.debug("mem_os_service: Search failed for agent=%s: %s", agent_id, e)
        return []


def mos_add_text(
    agent_id: str,
    content: str,
    session_id: str | None = None,
    doc_path: str | None = None,
) -> bool:
    """向 Agent 的 MemOS 中添加一段文本作为记忆。

    Args:
        agent_id: Agent ID
        content: 要添加的记忆文本内容
        session_id: 可选 session ID
        doc_path: 可选文档路径标记

    Returns:
        成功返回 True，失败返回 False。
    """
    mos = get_mos_for_agent(agent_id)
    if mos is None:
        return False

    try:
        mos.add(
            memory_content=content,
            session_id=session_id,
            doc_path=doc_path,
        )
        _log.debug(
            "mem_os_service: Added memory for agent=%s len=%d session=%s",
            agent_id, len(content), session_id,
        )
        return True
    except Exception as e:
        _log.debug("mem_os_service: Add memory failed for agent=%s: %s", agent_id, e)
        return False


def mos_add_messages(
    agent_id: str,
    messages: list[dict[str, str]],
    session_id: str | None = None,
) -> bool:
    """向 Agent 的 MemOS 中添加聊天消息记录作为记忆。

    messages 格式: ``[{"role": "user", "content": "..."}, ...]``

    Args:
        agent_id: Agent ID
        messages: 消息列表
        session_id: 可选 session ID

    Returns:
        成功返回 True，失败返回 False。
    """
    mos = get_mos_for_agent(agent_id)
    if mos is None:
        return False

    try:
        mos.add(messages=messages, session_id=session_id)
        _log.debug(
            "mem_os_service: Added %d messages for agent=%s session=%s",
            len(messages), agent_id, session_id,
        )
        return True
    except Exception as e:
        _log.debug("mem_os_service: Add messages failed for agent=%s: %s", agent_id, e)
        return False


def mos_chat(
    agent_id: str,
    query: str,
    base_prompt: str | None = None,
) -> str:
    """通过 MemOS 进行记忆感知的聊天（搜索相关记忆后生成回复）。

    Args:
        agent_id: Agent ID
        query: 用户查询
        base_prompt: 可选自定义 base prompt（支持 {memories} 占位符）

    Returns:
        MOS 生成的回复文本。失败时返回空字符串。
    """
    mos = get_mos_for_agent(agent_id)
    if mos is None:
        return ""

    try:
        response = mos.chat(query=query, user_id=None, base_prompt=base_prompt)
        return response
    except Exception as e:
        _log.debug("mem_os_service: Chat failed for agent=%s: %s", agent_id, e)
        return ""


def remove_mos_for_agent(agent_id: str) -> bool:
    """移除 Agent 的 MOS 实例缓存（用于 agent 删除/关闭时清理）。

    Args:
        agent_id: Agent ID

    Returns:
        若缓存中存在该实例则返回 True。
    """
    safe_id = agent_id.replace("/", "_").replace(":", "_")
    with _cache_lock:
        existed = safe_id in _mos_cache
        _mos_cache.pop(safe_id, None)
    if existed:
        _log.info("mem_os_service: Removed MOS cache for agent=%s", agent_id)
    return existed


# ═══════════════════════════════════════════════════════════════════════════════════
# MemOSService 公共类
# ═══════════════════════════════════════════════════════════════════════════════════


class MemOSService:
    """MemOS (Memory OS) 操作公共类（单例）。

    封装 MOS 实例生命周期与记忆增删查。
    """

    def __init__(self):
        self._mos_cache: dict[str, Any] = {}
        self._cache_lock = threading.Lock()

    # ── 生命周期 ────────────────────────────────────────────────────────

    async def start(self) -> None:
        """预加载 embedding 模型，避免首次搜索延迟。"""
        prewarm_embedding_model()

    async def stop(self) -> None:
        """清理资源（MOS 实例由 Python GC 自动回收）。"""
        with self._cache_lock:
            self._mos_cache.clear()

    # ── MOS 实例管理 ────────────────────────────────────────────────────

    def get_or_create_mos(self, agent_id: str) -> Any | None:
        """获取（或创建）per-agent 的 MOS 单例。"""
        # 委托给模块级函数（共享全局缓存）
        return get_mos_for_agent(agent_id)

    def has_mos(self, agent_id: str) -> bool:
        """检查 Agent 是否已有 MOS 实例。"""
        safe_id = agent_id.replace("/", "_").replace(":", "_")
        with _cache_lock:
            return safe_id in _mos_cache

    def remove_mos(self, agent_id: str) -> bool:
        """移除 Agent 的 MOS 实例缓存。"""
        return remove_mos_for_agent(agent_id)

    # ── 记忆操作 ────────────────────────────────────────────────────────

    def add_memory(self, agent_id: str, content: str, doc_path: str = "") -> bool:
        """添加文本记忆。"""
        return mos_add_text(agent_id, content, doc_path=doc_path if doc_path else None)

    def add_messages(self, agent_id: str, messages: list[dict], session_id: str | None = None) -> bool:
        """添加聊天消息记忆。"""
        return mos_add_messages(agent_id, messages, session_id=session_id)

    def search_memory(self, agent_id: str, query: str, top_k: int = 5) -> list[str]:
        """语义搜索记忆。"""
        return mos_search(agent_id, query, top_k=top_k)

    def chat(self, agent_id: str, query: str, base_prompt: str | None = None) -> str:
        """记忆感知对话。"""
        return mos_chat(agent_id, query, base_prompt=base_prompt)



# ── 单例工厂 ──────────────────────────────────────────────────────────────────

_service: MemOSService | None = None


def get_memos_service() -> MemOSService:
    """获取 MemOSService 全局单例。"""
    global _service
    if _service is None:
        _service = MemOSService()
    return _service


# ── 模块导出 ──────────────────────────────────────────────────────────────────
__all__ = [
    "MemOSService",
    "get_memos_service",
    "get_mos_for_agent",
    "mos_search",
    "mos_add_text",
    "mos_add_messages",
    "mos_chat",
    "remove_mos_for_agent",
]
