"""初始基线迁移 — 从 _ensure_schema() 创建完整数据库 schema。

Revision ID: 001
Create Date: 2026-05-15

此迁移调用现有的 _ensure_schema() 来创建所有表结构。
后续 schema 变更通过 `alembic revision --autogenerate` 生成增量迁移。

迁移历史:
    <base> → 001_initial_schema (当前)
"""
from __future__ import annotations

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """应用初始 schema：调用 _ensure_schema() + 创建 per-agent 动态表索引。"""
    import sqlite3
    import os

    from backend.core.config import get_config

    cfg = get_config()
    db_path = str(cfg.data_dir / "HermesDigitalStudio.db")
    os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)

    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")

    try:
        from backend.db.connection import _ensure_schema
        _ensure_schema(conn)
        conn.commit()
        print(f"[alembic] 001_initial_schema: 已创建数据库 schema → {db_path}")
    finally:
        conn.close()


def downgrade() -> None:
    """回滚：删除所有核心表（危险操作，仅测试环境）。

    注意：此操作不可逆！生产环境请勿执行 downgrade。
    """
    import sqlite3
    import os

    from backend.core.config import get_config

    cfg = get_config()
    db_path = str(cfg.data_dir / "HermesDigitalStudio.db")

    if not os.path.exists(db_path):
        print(f"[alembic] 001_initial_schema: 数据库文件不存在，无需回滚 → {db_path}")
        return

    conn = sqlite3.connect(db_path)

    core_tables = [
        "agent_avatars",
        "agent_personality",
        "plan_artifacts",
        "plan_artifact_steps",
        "agent_sessions",
        "agent_energy",
        "agent_energy_log",
        "agent_emotion",
        "agent_emotion_log",
        "agent_cooling_buffer",
        "agent_emotion_inertia",
        "agent_epigenetic_imprint",
        "agent_emotion_session_log",
        "memory_scoring_meta",
        "myelination_meta",
        "model_cost_log",
    ]

    for table in core_tables:
        conn.execute(f"DROP TABLE IF EXISTS {table}")

    conn.commit()
    conn.close()
    print(f"[alembic] 001_initial_schema: 已回滚核心表 → {db_path}")
