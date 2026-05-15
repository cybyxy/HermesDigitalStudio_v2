"""FastAPI 应用入口 — 对应 Spring Boot @SpringBootApplication。

职责：
- 结构化日志初始化
- DI 容器注册
- CORS 中间件注册
- 请求 ID 传播中间件
- 所有 API Router 统一注册（prefix="/api" 在此处统一加）
- lifespan 事件：启动时初始化 Agent 子进程，关闭时清理
"""

from __future__ import annotations

import logging
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.requests import Request

from backend.api import (
    health_router,
    settings_router,
    agent_router,
    chat_router,
    env_router,
    model_router,
    plan_router,
    skill_router,
    model_crud_router,
    channel_router,
    platform_gateway_router,
    stt_router,
    media_router,
    memory_router,
)
from backend.db.connection import close_thread_connection
from backend.middleware.api_response import register_api_response_middleware

_log = logging.getLogger(__name__)


def _setup_logging() -> None:
    """初始化结构化日志（支持 JSON / 开发模式切换）。

    - PyCharm / --reload 模式下使用开发模式（可读纯文本）
    - 其他模式输出 JSON 格式日志
    """
    in_dev = "PYCHARM_HOSTED" in os.environ or "--reload" in sys.argv
    structured = not in_dev

    import backend.core.logging as studio_logging

    studio_logging.setup(structured=structured)
    _log.info("日志模式: structured=%s", structured)


def _apply_config_overrides() -> None:
    """将 studio.yaml 中的配置覆盖到 design_tokens 等模块级常量。"""
    try:
        from backend.core.design_tokens import _apply_studio_overrides
        _apply_studio_overrides()
    except Exception as e:
        _log.warning("studio config override failed (non-fatal): %s", e)


def _setup_container() -> None:
    """向 DI 容器注册核心服务。"""
    import backend.core.container as container
    from backend.core.config import get_config

    container.register_singleton("config", get_config)

    # GatewayManager — 延迟到 lifespan 中解析
    container.register_singleton("gateway_manager", _lazy_gateway_manager)


def _lazy_gateway_manager():
    """DI 容器工厂函数：首次 resolve 时创建 GatewayManager 并加载 agents。"""
    from backend.gateway.gateway import GatewayManager
    from backend.services.profile_scanner import _startup_agents

    mgr = GatewayManager()
    _startup_agents(mgr)
    return mgr





def _bootstrap_agents_background(mgr) -> None:
    """后台执行 Agent 启动引导（记忆恢复 + Neo4j 图谱验证）。

    daemon 线程，不阻塞启动流程。
    """
    import threading as _threading

    def _run():
        try:
            from backend.services.agent_bootstrap import bootstrap_all_agents
            bootstrap_all_agents(mgr)
        except Exception as e:
            _log.warning("Agent bootstrap failed (non-fatal): %s", e)

    t = _threading.Thread(target=_run, daemon=True, name="agent-bootstrap")
    t.start()


def _preload_all_models() -> None:
    """预加载所有模型（STT + TTS + 嵌入模型 + Neo4j 连接），在 agent 启动前执行。"""
    # Vosk STT 模型
    try:
        from backend.services.stt import init_model
        init_model()
        _log.info("Vosk STT model preloaded")
    except Exception as e:
        _log.warning("Vosk preload failed (non-fatal): %s", e)

    # TTS 本地引擎（Piper / KittenTTS）——避免前端首次语音播放时懒加载延迟
    try:
        from backend.services.tts_preload import prewarm_tts_models
        prewarm_tts_models()
    except Exception as e:
        _log.warning("TTS prewarm failed (non-fatal): %s", e)

    # Sentence-transformer 嵌入模型
    try:
        from backend.services.mem_os_service import prewarm_embedding_model
        prewarm_embedding_model()
    except Exception as e:
        _log.warning("Embedding prewarm failed (non-fatal): %s", e)

    # Neo4j 连接（start() 是 async 方法，在后台线程中用 asyncio.run 执行）
    try:
        from backend.services.neo4j_service import get_neo4j_service
        neo4j = get_neo4j_service()
        import asyncio
        asyncio.run(neo4j.start())
        if neo4j.is_connected():
            _log.info("Neo4j connection verified")
        else:
            _log.warning("Neo4j unavailable, KG validation will be skipped")
    except Exception as e:
        _log.warning("Neo4j init failed (non-fatal): %s", e)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理 — 对应 Spring Boot ApplicationRunner。

    启动：初始化 SQLite schema，加载 GatewayManager，启动消息网关
    关闭：停止网关，清理所有 Agent 子进程
    """
    import backend.core.container as container

    # ── 启动阶段 ──────────────────────────────────────────────────────────────
    from backend.services import agent_db as _agent_db
    from backend.services import platform_gateway as _platform_gateway

    # 0. 应用 studio.yaml 配置覆盖到模块级常量
    _apply_config_overrides()

    # 1. 预加载所有模型（先于 agent 启动，避免运行时懒加载延迟）
    _preload_all_models()

    # 1. 迁移 SQLite schema（必须在启动 Gateway 之前）
    _agent_db.ensure_agent_db_schema()

    # 2. 初始化 GatewayManager（通过 DI 容器获取单例）
    mgr = container.resolve("gateway_manager")

    # 3. 打开列表，确保 data/*.db 可读
    _agent_db.list_db_agents()
    _log.info("HermesDigitalStudio 启动，共 %d 个 Agent", len(mgr.list_agents()))

    # 4. 初始化 Gateway Studio Bridge（pub/sub 事件桥接）
    from backend.services import gateway_studio_bridge as _gateway_bridge

    _gateway_bridge.get_bridge_secret()
    _gateway_bridge.write_studio_bridge_config_file()

    # 5. 启动嵌入式 Hermes 消息网关
    _pgw = _platform_gateway.start_embedded_gateway(from_lifespan=True)
    if _pgw.get("reason") == "opt_out_no_embedded":
        _log.info("HERMES_STUDIO_NO_EMBEDDED_GATEWAY 已设置，跳过消息网关")
    elif not _pgw.get("skipped"):
        _log.info("Hermes 消息网关已启动: %s", _pgw)
    elif _pgw.get("reason") == "external_gateway_pid_file":
        _log.info("已有消息网关进程 (pid=%s)，跳过启动", _pgw.get("pid"))

    # 6. 后台执行 Agent 启动引导（记忆恢复 + Neo4j 图谱验证）
    _bootstrap_agents_background(mgr)

    # 8. 启动心跳推理循环
    from backend.core.config import get_config
    from backend.services.heartbeat import get_heartbeat_service

    config = get_config()
    if config.heartbeat_enabled:
        heartbeat_svc = get_heartbeat_service()
        await heartbeat_svc.start()

    # 9. 启动能量管理服务（后台 bio_current 回落循环）
    from backend.services.energy import get_energy_service
    energy_svc = get_energy_service()
    await energy_svc.start()

    # 10. 启动情绪引擎服务（PAD 情绪模型 + 时间衰减）
    from backend.services.emotion import get_emotion_service
    emotion_svc = get_emotion_service()
    await emotion_svc.start()

    yield

    # ── 关闭阶段 ──────────────────────────────────────────────────────────────
    # 停止心跳推理循环
    if config.heartbeat_enabled:
        await heartbeat_svc.stop()

    # 停止情绪引擎服务
    await emotion_svc.stop()

    # 停止能量管理服务
    await energy_svc.stop()

    _platform_gateway.stop_embedded_gateway()
    _log.info("HermesDigitalStudio 关闭，清理 Agent 子进程")
    mgr.shutdown_all()


def create_app() -> FastAPI:
    """应用工厂 — 对应 Spring Boot 入口类。"""
    _setup_logging()
    _setup_container()

    app = FastAPI(title="HermesDigitalStudio", version="0.1.0", lifespan=lifespan)

    # ── 中间件注册（洋葱模型：外 → 内） ────────────────────────────────────────

    # 1. CORS：限制仅 localhost / 127.0.0.1
    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=r"^https?://(localhost|127\\.0\\.0\\.1)(:\\d+)?$",
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 2. 请求 ID 传播：生成 request_id，注入日志上下文 + 响应头
    @app.middleware("http")
    async def _request_id_middleware(request: Request, call_next):
        from backend.core.logging import set_request_id, generate_request_id

        rid = request.headers.get("X-Request-Id", generate_request_id())
        set_request_id(rid)
        response = await call_next(request)
        response.headers["X-Request-Id"] = rid
        return response

    # 3. DB 连接池清理：每次请求结束后关闭线程本地连接
    @app.middleware("http")
    async def _db_cleanup(request: Request, call_next):
        try:
            return await call_next(request)
        finally:
            close_thread_connection()

    # 注册全局异常处理器
    from backend.core.error_handlers import register_error_handlers

    register_error_handlers(app)

    # 注册统一响应格式中间件
    register_api_response_middleware(app)

    # ── Router 注册 ───────────────────────────────────────────────────────────

    app.include_router(health_router, prefix="/api")
    app.include_router(model_router, prefix="/api")
    app.include_router(env_router, prefix="/api")
    app.include_router(settings_router, prefix="/api")
    app.include_router(agent_router, prefix="/api")
    app.include_router(skill_router, prefix="/api")
    app.include_router(plan_router, prefix="/api")
    app.include_router(chat_router, prefix="/api")
    app.include_router(model_crud_router, prefix="/api")
    app.include_router(channel_router, prefix="/api")
    app.include_router(platform_gateway_router, prefix="/api")
    app.include_router(stt_router, prefix="/api")
    app.include_router(media_router, prefix="/api")
    app.include_router(memory_router, prefix="/api")

    # 静态素材：与 Vite public/assets 一致
    _repo_root = Path(__file__).resolve().parents[3]
    _assets_dir = _repo_root / "frontend" / "public" / "assets"
    if _assets_dir.is_dir():
        app.mount(
            "/assets",
            StaticFiles(directory=str(_assets_dir)),
            name="studio_assets",
        )

    return app


# 用于 uvicorn 直接导入
app = create_app()
