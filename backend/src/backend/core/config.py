"""统一配置层 — 所有配置读取的单一入口。

通过 ``get_config()`` 获取单例配置对象，禁止在业务代码中直接调用 ``os.environ``。

配置解析优先级（从高到低）：
1. ``backend/studio.yaml`` — Studio 自有配置（主要途径）
2. 环境变量 — 向后兼容覆盖
3. 代码默认值
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import cached_property
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve()
_STUDIO_YAML_CACHE: dict[str, Any] | None = None
"""单次加载 studio.yaml 的模块级缓存。"""


def _find_studio_yaml() -> Path | None:
    """从 CWD 向上查找 ``backend/studio.yaml`` 或 ``studio.yaml``。"""
    cwd = Path.cwd().resolve()
    for parent in [cwd] + list(cwd.parents):
        for candidate in [parent / "studio.yaml", parent / "backend" / "studio.yaml"]:
            if candidate.is_file():
                return candidate
    return None


def _load_studio_yaml() -> dict[str, Any]:
    """加载并缓存 studio.yaml 内容（单次解析）。"""
    global _STUDIO_YAML_CACHE
    if _STUDIO_YAML_CACHE is not None:
        return _STUDIO_YAML_CACHE

    path = _find_studio_yaml()
    if path is None:
        _STUDIO_YAML_CACHE = {}
        return _STUDIO_YAML_CACHE

    try:
        import yaml
        raw = yaml.safe_load(path.read_text())
        _STUDIO_YAML_CACHE = raw if isinstance(raw, dict) else {}
    except Exception:
        _STUDIO_YAML_CACHE = {}

    return _STUDIO_YAML_CACHE


def _yaml_get(*keys: str, default: Any = None) -> Any:
    """从 studio.yaml 读取嵌套值，如 ``_yaml_get("server", "port")``。"""
    cfg = _load_studio_yaml()
    node: Any = cfg
    for k in keys:
        if isinstance(node, dict):
            node = node.get(k)
        else:
            return default
    return node if node is not None else default


def _env_or(name: str, default: str) -> str:
    """读取环境变量，若无则返回 default。"""
    return (os.environ.get(name) or "").strip() or default


def _env_bool(name: str, default: bool = False) -> bool:
    """读取 Boolean 环境变量。"""
    raw = _env_or(name, "true" if default else "false")
    return raw.lower() in ("1", "true", "yes", "on")


def _yaml_or_env(*keys: str, env_name: str, default: str) -> str:
    """优先 studio.yaml > 环境变量 > 默认值（用于 str 类型）。"""
    yv = _yaml_get(*keys)
    if yv is not None and str(yv).strip():
        return str(yv).strip()
    return _env_or(env_name, default)


def _yaml_or_env_bool(*keys: str, env_name: str, default: bool) -> bool:
    """优先 studio.yaml > 环境变量 > 默认值（用于 bool 类型）。"""
    yv = _yaml_get(*keys)
    if yv is not None:
        s = str(yv).strip().lower()
        if s in ("true", "false", "1", "0", "yes", "no", "on", "off"):
            return s in ("1", "true", "yes", "on")
    return _env_bool(env_name, default)


def _yaml_or_env_int(*keys: str, env_name: str, default: int) -> int:
    """优先 studio.yaml > 环境变量 > 默认值（用于 int 类型）。"""
    yv = _yaml_get(*keys)
    if yv is not None:
        try:
            return int(yv)
        except (TypeError, ValueError):
            pass
    raw = _env_or(env_name, "")
    if raw:
        try:
            return int(raw)
        except ValueError:
            pass
    return default


def _yaml_or_env_float(*keys: str, env_name: str, default: float) -> float:
    """优先 studio.yaml > 环境变量 > 默认值（用于 float 类型）。"""
    yv = _yaml_get(*keys)
    if yv is not None:
        try:
            return float(yv)
        except (TypeError, ValueError):
            pass
    raw = _env_or(env_name, "")
    if raw:
        try:
            return float(raw)
        except ValueError:
            pass
    return default


@dataclass(frozen=True)
class StudioConfig:
    """Hermes Digital Studio 后端全局配置。

    每个字段通过 ``_yaml_or_env_*`` 工具函数实现三层优先级：
    studio.yaml > 环境变量 > 代码默认值。
    """

    # ── 核心路径 ──────────────────────────────────────────────────────────

    @cached_property
    def hermes_home(self) -> Path:
        """Hermes 主目录（Agent 配置、state.db 等存储位置）。

        **注意**：这是 Hermes 原生配置，不从 studio.yaml 读取。
        """
        raw = _env_or("HERMES_HOME", "~/.hermes")
        return Path(raw).expanduser()

    @cached_property
    def studio_data_dir(self) -> Path:
        """Studio SQLite 数据目录。

        优先级：
        1. studio.yaml: server.data_dir
        2. 环境变量 HERMES_STUDIO_DATA_DIR
        3. 向上查找含 HermesDigitalStudio.db 的 data 目录
        4. 默认使用 backend/data/
        """
        yv = _yaml_get("server", "data_dir")
        if yv and str(yv).strip():
            p = Path(str(yv).strip()).expanduser().resolve()
            p.mkdir(parents=True, exist_ok=True)
            return p
        env = _env_or("HERMES_STUDIO_DATA_DIR", "")
        if env:
            p = Path(env).expanduser().resolve()
            p.mkdir(parents=True, exist_ok=True)
            return p
        for par in [_HERE, *_HERE.parents]:
            data = par / "data"
            if (data / "HermesDigitalStudio.db").is_file():
                return data
            if par.name == "backend" and (par / "src" / "backend").is_dir():
                data.mkdir(parents=True, exist_ok=True)
                return data
        data = _HERE.parent.parent.parent / "data"
        data.mkdir(parents=True, exist_ok=True)
        return data

    @property
    def db_path(self) -> Path:
        """SQLite 数据库文件完整路径。"""
        return self.studio_data_dir / "HermesDigitalStudio.db"

    # ── 网络 ──────────────────────────────────────────────────────────────

    @cached_property
    def port(self) -> int:
        """后端监听端口。

        优先级：studio.yaml ``server.port`` > ``PORT`` 环境变量 > ``STUDIO_BACKEND_PORT`` 环境变量 > 默认 9120。
        """
        yv = _yaml_get("server", "port")
        if yv is not None:
            try:
                return int(yv)
            except (TypeError, ValueError):
                pass
        env_port = _env_or("PORT", "")
        if env_port:
            try:
                return int(env_port)
            except ValueError:
                pass
        env_studio_port = _env_or("STUDIO_BACKEND_PORT", "")
        if env_studio_port:
            try:
                return int(env_studio_port)
            except ValueError:
                pass
        return 9120

    @cached_property
    def gateway_ingest_url(self) -> str:
        """Gateway 事件回推 URL 覆盖。"""
        return _yaml_or_env(
            "gateway", "ingest_url",
            env_name="HERMES_STUDIO_GATEWAY_INGEST_URL",
            default="",
        )

    # ── Gateway 子进程 ────────────────────────────────────────────────────

    @cached_property
    def gateway_python(self) -> str:
        """嵌入消息网关的 Python 解释器路径覆盖。"""
        return _yaml_or_env(
            "gateway", "python",
            env_name="HERMES_STUDIO_GATEWAY_PYTHON",
            default="",
        )

    @cached_property
    def no_embedded_gateway(self) -> bool:
        """是否禁用嵌入式消息网关。"""
        return _yaml_or_env_bool(
            "gateway", "no_embedded",
            env_name="HERMES_STUDIO_NO_EMBEDDED_GATEWAY",
            default=False,
        )

    # ── Neo4j 图数据库 ───────────────────────────────────────────────────

    @cached_property
    def neo4j_uri(self) -> str:
        """Neo4j Bolt 连接 URI。"""
        return _yaml_or_env(
            "neo4j", "uri",
            env_name="NEO4J_URI",
            default="bolt://localhost:7687",
        )

    @cached_property
    def neo4j_user(self) -> str:
        """Neo4j 用户名。"""
        return _yaml_or_env(
            "neo4j", "user",
            env_name="NEO4J_USER",
            default="neo4j",
        )

    @cached_property
    def neo4j_password(self) -> str:
        """Neo4j 密码。"""
        return _yaml_or_env(
            "neo4j", "password",
            env_name="NEO4J_PASSWORD",
            default="bobo1234",
        )

    # ── 心跳推理循环 ────────────────────────────────────────────────────

    @cached_property
    def heartbeat_enabled(self) -> bool:
        """是否启用心跳推理循环。"""
        return _yaml_or_env_bool(
            "heartbeat", "enabled",
            env_name="HERMES_HEARTBEAT_ENABLED",
            default=True,
        )

    @cached_property
    def heartbeat_interval_seconds(self) -> float:
        """心跳间隔（秒）。"""
        return _yaml_or_env_float(
            "heartbeat", "interval",
            env_name="HERMES_HEARTBEAT_INTERVAL",
            default=5.0,
        )

    @cached_property
    def heartbeat_idle_timeout_seconds(self) -> float:
        """用户空闲多久（秒）后恢复心跳推理，默认 50 秒。"""
        return _yaml_or_env_float(
            "heartbeat", "idle_timeout",
            env_name="HERMES_HEARTBEAT_IDLE_TIMEOUT",
            default=50.0,
        )

    @cached_property
    def heartbeat_model(self) -> str:
        """心跳推理使用的独立轻量模型名。"""
        return _yaml_or_env(
            "heartbeat", "model",
            env_name="HERMES_HEARTBEAT_MODEL",
            default="",
        )

    @cached_property
    def heartbeat_model_provider(self) -> str:
        """心跳推理模型 provider slug。"""
        return _yaml_or_env(
            "heartbeat", "provider",
            env_name="HERMES_HEARTBEAT_PROVIDER",
            default="",
        )

    @cached_property
    def heartbeat_model_api_key(self) -> str:
        """心跳推理模型 API Key。"""
        return _yaml_or_env(
            "heartbeat", "api_key",
            env_name="HERMES_HEARTBEAT_API_KEY",
            default="",
        )

    @cached_property
    def heartbeat_model_base_url(self) -> str:
        """心跳推理模型 Base URL。"""
        return _yaml_or_env(
            "heartbeat", "base_url",
            env_name="HERMES_HEARTBEAT_BASE_URL",
            default="",
        )

    @cached_property
    def heartbeat_level_interval_map(self) -> dict:
        """饱食度 → 心跳间隔映射，JSON 字典格式。"""
        import json

        yv = _yaml_get("heartbeat", "level_intervals")
        if isinstance(yv, dict):
            return yv
        raw = _env_or("HERMES_HEARTBEAT_LEVEL_INTERVALS", "")
        if raw:
            try:
                return json.loads(raw)
            except json.JSONDecodeError:
                pass
        return {
            "satiety_lt_30": 90,
            "satiety_30_60": 60,
            "satiety_60_80": 30,
            "satiety_gt_80": 15,
        }

    @cached_property
    def heartbeat_prefilter_enabled(self) -> bool:
        """是否启用心跳预判过滤器。"""
        return _yaml_or_env_bool(
            "heartbeat", "prefilter_enabled",
            env_name="HERMES_HEARTBEAT_PREFILTER_ENABLED",
            default=True,
        )

    @cached_property
    def heartbeat_spatial_enabled(self) -> bool:
        """是否启用空间感知空闲行为。"""
        return _yaml_or_env_bool(
            "heartbeat", "spatial_enabled",
            env_name="HERMES_HEARTBEAT_SPATIAL_ENABLED",
            default=False,
        )

    @cached_property
    def mind_config(self) -> dict:
        """心智架构配置段。"""
        yv = _yaml_get("mind")
        return yv if isinstance(yv, dict) else {}

    # ── 模型适配器（Gemini / Ollama）────────────────────────────────────

    @cached_property
    def gemini_api_key(self) -> str:
        """Gemini API Key。"""
        return _yaml_or_env(
            "providers", "gemini", "api_key",
            env_name="GEMINI_API_KEY",
            default="",
        )

    @cached_property
    def ollama_host(self) -> str:
        """Ollama 服务地址。"""
        return _yaml_or_env(
            "providers", "ollama", "host",
            env_name="OLLAMA_HOST",
            default="http://localhost:11434",
        )

    # ── Qdrant 向量数据库 ────────────────────────────────────────────────

    @cached_property
    def qdrant_config(self) -> dict | None:
        """Qdrant 配置段（完整 dict）。"""
        yv = _yaml_get("qdrant")
        if isinstance(yv, dict):
            return yv
        return None

    # ── Embedding 嵌入模型 ───────────────────────────────────────────────

    @cached_property
    def embedding_model(self) -> str:
        """sentence-transformers 嵌入模型名称（HuggingFace repo ID 或本地路径）。

        优先级：
        1. studio.yaml ``embedding.model``
        2. 环境变量 ``HERMES_EMBEDDING_MODEL``
        3. 默认 ``all-MiniLM-L6-v2``
        """
        return _yaml_or_env(
            "embedding", "model",
            env_name="HERMES_EMBEDDING_MODEL",
            default="all-MiniLM-L6-v2",
        )

    @cached_property
    def embedding_dimensions(self) -> int:
        """嵌入向量的维度。

        优先级：
        1. studio.yaml ``embedding.dimensions``
        2. 环境变量 ``HERMES_EMBEDDING_DIMENSIONS``
        3. 默认 384（与 all-MiniLM-L6-v2 匹配）
        """
        return _yaml_or_env_int(
            "embedding", "dimensions",
            env_name="HERMES_EMBEDDING_DIMENSIONS",
            default=384,
        )

    @cached_property
    def embedding_cache_dir(self) -> str:
        """SentenceTransformer 模型缓存目录。

        优先级：
        1. studio.yaml ``embedding.cache_dir``
        2. 环境变量 ``HERMES_EMBEDDING_CACHE_DIR``
        3. 默认 ``backend/models/``
        """
        return _yaml_or_env(
            "embedding", "cache_dir",
            env_name="HERMES_EMBEDDING_CACHE_DIR",
            default=str(_HERE.parents[3] / "models"),
        )

    # ── MemOS 数据目录 ───────────────────────────────────────────────────

    @cached_property
    def memos_dir(self) -> str:
        """MemOS 数据根目录（覆盖自动检测）。

        可用 ``studio.yaml: memos.dir`` 或环境变量 ``MEMOS_DIR`` / ``HERMES_STUDIO_MEMOS_DIR`` 覆盖。
        """
        yv = _yaml_get("memos", "dir")
        if yv and str(yv).strip():
            return str(yv).strip()
        env = _env_or("HERMES_STUDIO_MEMOS_DIR", "")
        if env:
            return env
        env = _env_or("MEMOS_DIR", "")
        if env:
            return env
        return ""

    # ── UI / 国际化 ──────────────────────────────────────────────────────

    @cached_property
    def ui_locale(self) -> str:
        """默认语言区域（zh / en）。"""
        return _yaml_or_env(
            "ui", "locale",
            env_name="HERMES_STUDIO_LOCALE",
            default="zh",
        )

    @cached_property
    def ui_timezone(self) -> str:
        """默认时区。"""
        return _yaml_or_env(
            "ui", "timezone",
            env_name="HERMES_STUDIO_TIMEZONE",
            default="Asia/Shanghai",
        )

    # ── 调优参数（design_tokens 迁移）───────────────────────────────────

    def _tuning_int(self, key: str, env_name: str, default: int) -> int:
        return _yaml_or_env_int("tuning", key, env_name=env_name, default=default)

    def _tuning_float(self, key: str, env_name: str, default: float) -> float:
        return _yaml_or_env_float("tuning", key, env_name=env_name, default=default)

    _TUNING_KEYS: tuple[tuple[str, str, str, type], ...] = (
        ("page_size_default",        "HERMES_STUDIO_PAGE_SIZE_DEFAULT",        "10",    int),
        ("page_size_min",            "HERMES_STUDIO_PAGE_SIZE_MIN",            "1",     int),
        ("page_size_max",            "HERMES_STUDIO_PAGE_SIZE_MAX",            "200",   int),
        ("sse_timeout",              "HERMES_STUDIO_SSE_TIMEOUT",              "300.0", float),
        ("chat_timeout",             "HERMES_STUDIO_CHAT_TIMEOUT",             "600.0", float),
        ("plan_step_timeout",        "HERMES_STUDIO_PLAN_STEP_TIMEOUT",        "300.0", float),
        ("orchestrated_timeout",     "HERMES_STUDIO_ORCHESTRATED_TIMEOUT",     "900.0", float),
        ("db_busy_timeout_ms",       "HERMES_STUDIO_DB_BUSY_TIMEOUT_MS",       "5000",  int),
        ("db_health_check_interval_s","HERMES_STUDIO_DB_HEALTH_CHECK_INTERVAL_S","120",  int),
        ("max_text_length",          "HERMES_STUDIO_MAX_TEXT_LENGTH",           "128000",int),
        ("max_session_name_length",  "HERMES_STUDIO_MAX_SESSION_NAME_LENGTH",   "256",   int),
        ("max_agent_profile_length", "HERMES_STUDIO_MAX_AGENT_PROFILE_LENGTH",  "64",    int),
        ("max_channels_per_type",    "HERMES_STUDIO_MAX_CHANNELS_PER_TYPE",     "10",    int),
        ("default_session_cols",     "HERMES_STUDIO_DEFAULT_SESSION_COLS",      "120",   int),
        ("session_chain_max_depth",  "HERMES_STUDIO_SESSION_CHAIN_MAX_DEPTH",   "10",    int),
        ("agent_startup_timeout",    "HERMES_STUDIO_AGENT_STARTUP_TIMEOUT",     "30.0",  float),
        ("agent_shutdown_timeout",   "HERMES_STUDIO_AGENT_SHUTDOWN_TIMEOUT",    "10.0",  float),
        ("rate_limit_window",        "HERMES_STUDIO_RATE_LIMIT_WINDOW",         "60",    int),
        ("rate_limit_max",           "HERMES_STUDIO_RATE_LIMIT_MAX",            "120",   int),
    )

    def get_tuning(self, key: str) -> int | float:
        """通用调优参数读取（供 design_tokens 使用）。"""
        for t_key, t_env, t_def, t_type in self._TUNING_KEYS:
            if t_key == key:
                if t_type is float:
                    return _yaml_or_env_float("tuning", key, env_name=t_env, default=float(t_def))
                return _yaml_or_env_int("tuning", key, env_name=t_env, default=int(t_def))
        raise KeyError(f"Unknown tuning key: {key}")


_config: StudioConfig | None = None


def get_config() -> StudioConfig:
    """获取全局单例配置对象。"""
    global _config
    if _config is None:
        _config = StudioConfig()
    return _config
