"""DB 数据访问层（Data Access Object）。

所有数据库操作统一经过此层：
- ``db/connection`` — 连接池、schema 初始化
- ``db/agent``     — Agent 头像 / 性别 / 性格 / Session DAO
- ``db/plan``      — Plan Artifact / Step DAO
- ``db/memory``    — 压缩映射 / 会话摘要 DAO（per-agent 分表）
- ``db/knowledge`` — 知识图谱 DAO（per-agent 分表）

业务服务层（services/）应仅导入 DAO，不直接操作 sqlite3 连接。
"""

from backend.db.connection import (
    get_connection,
    ensure_schema,
    connection_context,
    pool_stats,
    close_thread_connection,
    ensure_agent_memory_tables,
)
from backend.db.agent import AgentAvatarDAO, AgentPersonalityDAO, AgentSessionDAO
from backend.db.plan import PlanArtifactDAO, PlanArtifactStepDAO
from backend.db.memory import CompressionMapDAO, SessionSummaryDAO
from backend.db.knowledge import KnowledgeNodeDAO, KnowledgeEdgeDAO

__all__ = [
    "get_connection",
    "ensure_schema",
    "connection_context",
    "pool_stats",
    "close_thread_connection",
    "ensure_agent_memory_tables",
    "AgentAvatarDAO",
    "AgentPersonalityDAO",
    "AgentSessionDAO",
    "PlanArtifactDAO",
    "PlanArtifactStepDAO",
    "CompressionMapDAO",
    "SessionSummaryDAO",
    "KnowledgeNodeDAO",
    "KnowledgeEdgeDAO",
]
