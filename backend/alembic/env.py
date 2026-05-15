"""Alembic 环境配置 — 连接 SQLite 数据库并管理迁移。

使用方式:
    cd backend
    alembic upgrade head      # 执行所有迁移
    alembic downgrade -1       # 回滚最新迁移
    alembic revision --autogenerate -m "描述"  # 自动生成迁移
"""
from __future__ import annotations

import logging
from alembic import context
from sqlalchemy import create_engine, pool

# ── 从 studio.yaml 读取数据库路径 ──────────────────────────────
try:
    from backend.core.config import get_config
    cfg = get_config()
    db_path = str(cfg.data_dir / "HermesDigitalStudio.db")
    sqlalchemy_url = f"sqlite:///{db_path}"
except Exception:
    # Fallback: 环境变量或默认路径
    import os
    db_path = os.environ.get("STUDIO_DB_PATH", "data/HermesDigitalStudio.db")
    sqlalchemy_url = f"sqlite:///{db_path}"

config = context.config
config.set_main_option("sqlalchemy.url", sqlalchemy_url)

logging.basicConfig(level=logging.INFO)
_log = logging.getLogger("alembic.env")

# 目标元数据（当前为空，使用原始 SQL 迁移；后续可引入 SQLAlchemy 模型）
target_metadata = None


def run_migrations_offline() -> None:
    """离线模式：生成 SQL 脚本而非直接执行。"""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """在线模式：直接连接数据库执行迁移。"""
    connectable = create_engine(
        config.get_main_option("sqlalchemy.url"),
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
