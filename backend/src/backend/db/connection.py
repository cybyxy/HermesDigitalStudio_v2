"""DB 连接池管理层：路径解析、线程安全连接、schema 初始化。

所有 DAO 必须通过 ``get_connection()`` 获取连接，
禁止在 DAO 之外直接调用 ``sqlite3.connect``。

连接通过线程本地缓存实现复用：同一线程内多次调用 ``get_connection()``
返回同一个连接，避免每次 DAO 调用都创建新连接。
"""

from __future__ import annotations

import logging
import sqlite3
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Generator

from backend.core.config import get_config

_log = logging.getLogger(__name__)
_lock = threading.Lock()
_thread_local = threading.local()

# ── 连接池配置常量 ──────────────────────────────────────────────────────────

BUSY_TIMEOUT_MS = 5000          # 写锁等待超时（毫秒）
HEALTH_CHECK_INTERVAL_S = 120   # 连接健康检查间隔（秒）
WAL_AUTOCHECKPOINT_PAGES = 1000 # WAL 自动 checkpoint 页数阈值

# ── 路径解析 ────────────────────────────────────────────────────────────────

_config = get_config()
_DATA_DIR = _config.studio_data_dir
DB_PATH: Path = _config.db_path


# ── 连接池代理 ─────────────────────────────────────────────────────────────

class _PooledConnection:
    """线程本地连接代理：所有方法调用透传至底层 sqlite3.Connection，
    但 close() 为空操作，保持底层连接开启以供后续复用。
    """

    __slots__ = ("_conn", "_last_health_check")

    def __init__(self, conn: sqlite3.Connection) -> None:
        object.__setattr__(self, "_conn", conn)
        object.__setattr__(self, "_last_health_check", 0.0)

    def __getattr__(self, name: str):
        return getattr(object.__getattribute__(self, "_conn"), name)

    def __setattr__(self, name: str, value) -> None:
        setattr(object.__getattribute__(self, "_conn"), name, value)

    def close(self) -> None:
        """空操作：不关闭底层连接，维持线程本地缓存复用。"""
        pass

    def _real_close(self) -> None:
        """真正关闭底层连接。"""
        object.__getattribute__(self, "_conn").close()

    def __enter__(self):
        return self

    def __exit__(self, *args) -> None:
        pass

    @property
    def _underlying_conn(self) -> sqlite3.Connection:
        return object.__getattribute__(self, "_conn")


# ── 连接池统计 ─────────────────────────────────────────────────────────────

_pool_stats = {
    "connections_created": 0,
    "connections_closed": 0,
    "health_check_failures": 0,
    "wal_checkpoints": 0,
    "started_at": time.time(),
}


def pool_stats() -> dict:
    """返回连接池运行时统计信息。"""
    return dict(_pool_stats)


# ── 连接管理 ───────────────────────────────────────────────────────────────

def _create_connection() -> sqlite3.Connection:
    """创建新 sqlite3 连接并配置 pragma。"""
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.execute(f"PRAGMA journal_mode=WAL")
    conn.execute(f"PRAGMA busy_timeout={BUSY_TIMEOUT_MS}")
    conn.execute(f"PRAGMA wal_autocheckpoint={WAL_AUTOCHECKPOINT_PAGES}")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row
    _pool_stats["connections_created"] += 1
    _log.debug("created new DB connection to %s (total=%d)", DB_PATH, _pool_stats["connections_created"])
    return conn


def _health_check(pooled: _PooledConnection) -> bool:
    """检查连接是否存活，若断开则尝试重建。"""
    now = time.time()
    last = object.__getattribute__(pooled, "_last_health_check")
    if now - last < HEALTH_CHECK_INTERVAL_S:
        return True

    try:
        pooled._underlying_conn.execute("SELECT 1").fetchone()
        object.__setattr__(pooled, "_last_health_check", now)
        return True
    except Exception:
        _log.warning("DB connection health check failed, recreating...")
        _pool_stats["health_check_failures"] += 1
        try:
            pooled._real_close()
        except Exception:
            pass
        try:
            new_conn = _create_connection()
            _ensure_schema(new_conn)
            object.__setattr__(pooled, "_conn", new_conn)
            object.__setattr__(pooled, "_last_health_check", now)
            return True
        except Exception as e:
            _log.error("failed to recreate DB connection: %s", e)
            return False


def get_connection() -> _PooledConnection:
    """获取当前线程缓存的数据库连接（线程安全）。

    首次调用时创建新连接、启用 WAL 并初始化 schema；
    同一线程内后续调用直接返回缓存的连接，避免重复开销。
    """
    cached = getattr(_thread_local, "conn", None)
    if cached is not None:
        if _health_check(cached):
            return cached
        # 健康检查失败，清理后重新创建
        del _thread_local.conn

    with _lock:
        conn = _create_connection()
        _ensure_schema(conn)
        pooled = _PooledConnection(conn)
        _thread_local.conn = pooled
        return pooled


def close_thread_connection() -> None:
    """关闭当前线程缓存的数据库连接。应在请求/线程结束时调用。"""
    cached = getattr(_thread_local, "conn", None)
    if cached is not None:
        cached._real_close()
        _pool_stats["connections_closed"] += 1
        del _thread_local.conn


@contextmanager
def connection_context() -> Generator[_PooledConnection, None, None]:
    """DB 连接上下文管理器，在块结束时自动 WAL checkpoint + 关闭连接。

    用法::

        with connection_context() as conn:
            conn.execute("SELECT ...")
    """
    conn = get_connection()
    try:
        yield conn
    finally:
        _wal_checkpoint(conn)
        close_thread_connection()


# ── WAL checkpoint ─────────────────────────────────────────────────────────

def _wal_checkpoint(conn: _PooledConnection) -> None:
    """执行 WAL checkpoint（truncate 模式，回收 WAL 磁盘空间）。"""
    try:
        conn._underlying_conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        _pool_stats["wal_checkpoints"] += 1
    except Exception:
        pass  # checkpoint 失败不影响主流程


# ── Schema 初始化 ──────────────────────────────────────────────────────────

def _ensure_schema(conn: sqlite3.Connection) -> None:
    """初始化所有表结构（幂等操作）。"""
    _ensure_agent_avatars_schema(conn)
    _ensure_agent_personality_schema(conn)
    _ensure_plan_artifacts_schema(conn)
    _ensure_plan_artifact_steps_schema(conn)
    _ensure_agent_sessions_schema(conn)
    _ensure_energy_tables(conn)
    _ensure_emotion_tables(conn)
    _ensure_mind_tables(conn)

    # 记忆评分元数据表（由 MemoryScoringDAO 维护）
    from backend.db.memory_scoring import MemoryScoringDAO
    MemoryScoringDAO.ensure_schema(conn)

    # 髓鞘化元表（由 MyelinationDAO 维护）
    from backend.db.myelination import MyelinationDAO
    MyelinationDAO.ensure_meta_table(conn)

    # 模型调用成本日志表（由 ModelCostDAO 维护）
    from backend.db.model_cost import ModelCostDAO
    ModelCostDAO.ensure_schema(conn)


def _safe_id(id_str: str) -> str:
    """将任意 agent_id 转换为 DB 表名安全形式（替换 ``\\W`` 为 ``_``）。"""
    import re as _re
    return _re.sub(r"\W", "_", id_str).strip("_") or "unknown"


def ensure_agent_memory_tables(agent_id: str, conn: sqlite3.Connection | None = None) -> None:
    """为指定 Agent 创建 per-agent 记忆相关表（幂等操作）。

    创建四张表：
    - ``smry_{agent_id}`` — 会话摘要缓存（Phase 1）
    - ``cmap_{agent_id}`` — 上下文压缩映射（Phase 3）
    - ``kgnode_{agent_id}`` — 知识图谱节点（Phase 4）
    - ``kgedge_{agent_id}`` — 知识图谱边（Phase 4）

    采用分表策略：每个 Agent 拥有一组独立表，Agent 删除时 DROP TABLE 即可完全清理。
    """
    sid = _safe_id(agent_id)
    do_close = conn is None
    if conn is None:
        conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)

    try:
        # smry: 会话摘要缓存表
        conn.execute(f"""
            CREATE TABLE IF NOT EXISTS smry_{sid} (
                session_id   TEXT PRIMARY KEY,
                summary      TEXT NOT NULL,
                token_count  INTEGER DEFAULT 0,
                generated_at REAL NOT NULL,
                model        TEXT
            )
        """)

        # cmap: 上下文压缩映射表
        conn.execute(f"""
            CREATE TABLE IF NOT EXISTS cmap_{sid} (
                id                    INTEGER PRIMARY KEY AUTOINCREMENT,
                compressed_session_id TEXT NOT NULL,
                original_session_id   TEXT NOT NULL,
                message_range_start   INTEGER,
                message_range_end     INTEGER,
                summary               TEXT,
                key_topics            TEXT,
                compressed_at         REAL NOT NULL,
                UNIQUE(compressed_session_id, original_session_id)
            )
        """)

        # kgnode: 知识图谱节点表
        conn.execute(f"""
            CREATE TABLE IF NOT EXISTS kgnode_{sid} (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                label      TEXT NOT NULL,
                type       TEXT NOT NULL,
                summary    TEXT,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL,
                UNIQUE(label)
            )
        """)

        # kgedge: 知识图谱边表
        conn.execute(f"""
            CREATE TABLE IF NOT EXISTS kgedge_{sid} (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                source_id   INTEGER NOT NULL,
                target_id   INTEGER NOT NULL,
                relation    TEXT NOT NULL,
                evidence    TEXT,
                created_at  REAL NOT NULL,
                UNIQUE(source_id, target_id, relation)
            )
        """)

        conn.commit()
    finally:
        if do_close:
            conn.close()


# ── agent_avatars ──────────────────────────────────────────────────────────

def _ensure_agent_avatars_schema(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS agent_avatars (
            agent_id  TEXT PRIMARY KEY,
            avatar    TEXT NOT NULL DEFAULT 'badboy',
            gender    TEXT NOT NULL DEFAULT 'male'
        )
    """)
    cols = {str(r[1]) for r in conn.execute("PRAGMA table_info(agent_avatars)").fetchall()}
    for col, sql in [
        ("office_x",      "ALTER TABLE agent_avatars ADD COLUMN office_x REAL"),
        ("office_y",      "ALTER TABLE agent_avatars ADD COLUMN office_y REAL"),
        ("facing",        "ALTER TABLE agent_avatars ADD COLUMN facing TEXT"),
        ("model",         "ALTER TABLE agent_avatars ADD COLUMN model TEXT"),
        ("model_provider", "ALTER TABLE agent_avatars ADD COLUMN model_provider TEXT"),
        ("model_base_url", "ALTER TABLE agent_avatars ADD COLUMN model_base_url TEXT"),
    ]:
        if col not in cols:
            try:
                conn.execute(sql)
            except sqlite3.OperationalError as e:
                if "duplicate column name" not in str(e).lower():
                    raise
    conn.execute("DROP TABLE IF EXISTS agent_office_poses")
    conn.commit()


# ── agent_personality ──────────────────────────────────────────────────────

def _ensure_agent_personality_schema(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS agent_personality (
            agent_id     TEXT PRIMARY KEY,
            personality  TEXT NOT NULL DEFAULT '',
            catchphrases TEXT NOT NULL DEFAULT '',
            memes        TEXT NOT NULL DEFAULT ''
        )
    """)
    cols = {str(r[1]) for r in conn.execute("PRAGMA table_info(agent_personality)").fetchall()}
    for col, sql in [
        ("backtalk_intensity", "ALTER TABLE agent_personality ADD COLUMN backtalk_intensity INTEGER NOT NULL DEFAULT 0"),
    ]:
        if col not in cols:
            try:
                conn.execute(sql)
            except sqlite3.OperationalError as e:
                if "duplicate column name" not in str(e).lower():
                    raise
    conn.commit()


# ── plan_artifacts ────────────────────────────────────────────────────────

def _ensure_plan_artifacts_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        "CREATE TABLE IF NOT EXISTS plan_artifacts ("
        "  id           INTEGER PRIMARY KEY AUTOINCREMENT,"
        "  session_id   TEXT NOT NULL,"
        "  agent_id     TEXT NOT NULL,"
        "  name         TEXT NOT NULL DEFAULT '',"
        "  plan_summary TEXT NOT NULL DEFAULT '',"
        "  steps_json   TEXT NOT NULL DEFAULT '[]',"
        "  raw_text     TEXT,"
        "  status       TEXT NOT NULL DEFAULT 'pending',"
        "  current_step INTEGER NOT NULL DEFAULT -1,"
        "  created_at   REAL NOT NULL"
        ")"
    )
    cols = {str(r[1]) for r in conn.execute("PRAGMA table_info(plan_artifacts)").fetchall()}
    for col, sql in [
        ("name",         "ALTER TABLE plan_artifacts ADD COLUMN name TEXT NOT NULL DEFAULT ''"),
        ("status",       "ALTER TABLE plan_artifacts ADD COLUMN status TEXT NOT NULL DEFAULT 'pending'"),
        ("current_step", "ALTER TABLE plan_artifacts ADD COLUMN current_step INTEGER NOT NULL DEFAULT -1"),
    ]:
        if col not in cols:
            try:
                conn.execute(sql)
            except sqlite3.OperationalError as e:
                if "duplicate column name" not in str(e).lower():
                    raise


# ── plan_artifact_steps ───────────────────────────────────────────────────

def _ensure_plan_artifact_steps_schema(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS plan_artifact_steps (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            artifact_id  INTEGER NOT NULL,
            step_index   INTEGER NOT NULL DEFAULT 0,
            step_id      INTEGER NOT NULL DEFAULT 0,
            title        TEXT NOT NULL DEFAULT '',
            action       TEXT NOT NULL DEFAULT '',
            file_path    TEXT,
            executor     TEXT,
            session_id   TEXT,
            status       TEXT NOT NULL DEFAULT 'pending',
            error        TEXT,
            completed_at REAL,
            result       TEXT,
            FOREIGN KEY (artifact_id) REFERENCES plan_artifacts(id) ON DELETE CASCADE
        )
    """)
    cols = {str(r[1]) for r in conn.execute("PRAGMA table_info(plan_artifact_steps)").fetchall()}
    for col, sql in [
        ("executor",   "ALTER TABLE plan_artifact_steps ADD COLUMN executor TEXT"),
        ("session_id", "ALTER TABLE plan_artifact_steps ADD COLUMN session_id TEXT"),
        ("result",     "ALTER TABLE plan_artifact_steps ADD COLUMN result TEXT"),
    ]:
        if col not in cols:
            try:
                conn.execute(sql)
            except sqlite3.OperationalError as e:
                if "duplicate column name" not in str(e).lower():
                    raise


# ── agent_sessions ──────────────────────────────────────────────────────────

def _ensure_agent_sessions_schema(conn: sqlite3.Connection) -> None:
    """session 持久化表：记录 agent 与 session 的绑定关系，支持重启恢复。

    parent_session_id: 若不为空，表示该 session 是从另一个 session 压缩/续接而来的。
    """
    conn.execute("""
        CREATE TABLE IF NOT EXISTS agent_sessions (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_id         TEXT NOT NULL,
            session_id       TEXT NOT NULL,
            session_key      TEXT,
            created_at       REAL NOT NULL,
            last_used_at     REAL NOT NULL,
            is_active        INTEGER NOT NULL DEFAULT 1,
            parent_session_id TEXT,
            UNIQUE(agent_id, session_id)
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_agent_sessions_agent_id ON agent_sessions(agent_id)
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_agent_sessions_last_used ON agent_sessions(last_used_at DESC)
    """)

    # 迁移旧表：添加 parent_session_id 列（若尚不存在）
    cols = {str(r[1]) for r in conn.execute("PRAGMA table_info(agent_sessions)").fetchall()}
    if "parent_session_id" not in cols:
        try:
            conn.execute("ALTER TABLE agent_sessions ADD COLUMN parent_session_id TEXT")
        except sqlite3.OperationalError:
            pass
    if "session_key" not in cols:
        try:
            conn.execute("ALTER TABLE agent_sessions ADD COLUMN session_key TEXT")
        except sqlite3.OperationalError:
            pass
    if "reflected_turn_count" not in cols:
        try:
            conn.execute("ALTER TABLE agent_sessions ADD COLUMN reflected_turn_count INTEGER DEFAULT 0")
        except sqlite3.OperationalError:
            pass

    # 迁移：若 agent_avatars 表已有 session_id 列，则迁移到新表
    cols = {str(r[1]) for r in conn.execute("PRAGMA table_info(agent_avatars)").fetchall()}
    if "default_session_id" in cols:
        _migrate_default_session_from_avatars(conn)
        conn.execute("ALTER TABLE agent_avatars DROP COLUMN IF EXISTS default_session_id")

    conn.commit()


def _migrate_default_session_from_avatars(conn: sqlite3.Connection) -> None:
    """从 agent_avatars.default_session_id 迁移到 agent_sessions。"""
    try:
        rows = conn.execute(
            "SELECT agent_id, default_session_id FROM agent_avatars WHERE default_session_id IS NOT NULL AND default_session_id != ''"
        ).fetchall()
        now = time.time()
        for agent_id, session_id in rows:
            conn.execute(
                """INSERT OR IGNORE INTO agent_sessions
                   (agent_id, session_id, created_at, last_used_at, is_active)
                   VALUES (?, ?, ?, ?, 1)""",
                (agent_id, session_id, now, now),
            )
        _log.info("migrated %d session records from agent_avatars", len(rows))
    except Exception:
        _log.exception("failed to migrate default_session_id from agent_avatars")


# ── agent_energy ──────────────────────────────────────────────────────────

def _ensure_energy_tables(conn: sqlite3.Connection) -> None:
    """创建能量系统表（幂等操作）。"""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS agent_energy (
            agent_id    TEXT PRIMARY KEY,
            satiety     INTEGER NOT NULL CHECK (satiety BETWEEN 0 AND 100) DEFAULT 80,
            bio_current INTEGER NOT NULL CHECK (bio_current BETWEEN 0 AND 10) DEFAULT 3,
            mode        TEXT NOT NULL CHECK (mode IN ('normal','power_save','surge','forced_discharge'))
                        DEFAULT 'normal',
            updated_at  TEXT NOT NULL DEFAULT (datetime('now')),
            FOREIGN KEY (agent_id) REFERENCES agent_avatars(agent_id) ON DELETE CASCADE
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS agent_energy_log (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_id     TEXT NOT NULL,
            metric       TEXT NOT NULL CHECK (metric IN ('satiety','bio_current')),
            reason       TEXT NOT NULL,
            delta        REAL NOT NULL,
            value_before INTEGER NOT NULL,
            value_after  INTEGER NOT NULL,
            timestamp    TEXT NOT NULL DEFAULT (datetime('now')),
            FOREIGN KEY (agent_id) REFERENCES agent_energy(agent_id) ON DELETE CASCADE
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_energy_log_agent
        ON agent_energy_log(agent_id, timestamp DESC)
    """)
    conn.commit()


# ── agent_emotion ──────────────────────────────────────────────────────────

def _ensure_emotion_tables(conn: sqlite3.Connection) -> None:
    """创建情绪系统表（幂等操作）。"""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS agent_emotion (
            agent_id    TEXT PRIMARY KEY,
            valence     REAL NOT NULL DEFAULT 0.0
                        CHECK (valence BETWEEN -1 AND 1),
            arousal     REAL NOT NULL DEFAULT 0.0
                        CHECK (arousal BETWEEN -1 AND 1),
            dominance   REAL NOT NULL DEFAULT 0.0
                        CHECK (dominance BETWEEN -1 AND 1),
            updated_at  TEXT NOT NULL DEFAULT (datetime('now')),
            FOREIGN KEY (agent_id) REFERENCES agent_avatars(agent_id) ON DELETE CASCADE
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS agent_emotion_log (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_id    TEXT NOT NULL,
            valence     REAL NOT NULL,
            arousal     REAL NOT NULL,
            dominance   REAL NOT NULL,
            trigger     TEXT NOT NULL,
            timestamp   TEXT NOT NULL DEFAULT (datetime('now')),
            FOREIGN KEY (agent_id) REFERENCES agent_emotion(agent_id) ON DELETE CASCADE
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_emotion_log_agent
        ON agent_emotion_log(agent_id, timestamp DESC)
    """)
    conn.commit()


def _ensure_mind_tables(conn: sqlite3.Connection) -> None:
    """创建心智架构表（冷却缓冲区 / 情绪蓄水池 / 表观遗传 / 会话日志）。"""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS agent_cooling_buffer (
            agent_id        TEXT PRIMARY KEY,
            temperature     REAL NOT NULL DEFAULT 0.0,
            is_refractory   INTEGER NOT NULL DEFAULT 0,
            peak_temp       REAL NOT NULL DEFAULT 0.0,
            last_activation REAL NOT NULL DEFAULT 0.0,
            state           TEXT NOT NULL DEFAULT 'cooling',
            updated_at      TEXT NOT NULL DEFAULT (datetime('now')),
            FOREIGN KEY (agent_id) REFERENCES agent_avatars(agent_id) ON DELETE CASCADE
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS agent_emotion_inertia (
            agent_id       TEXT PRIMARY KEY,
            v_current      REAL NOT NULL DEFAULT 0.0,
            v_buffer       REAL NOT NULL DEFAULT 0.0,
            v_baseline     REAL NOT NULL DEFAULT 0.0,
            a_current      REAL NOT NULL DEFAULT 0.0,
            a_buffer       REAL NOT NULL DEFAULT 0.0,
            a_baseline     REAL NOT NULL DEFAULT 0.0,
            d_current      REAL NOT NULL DEFAULT 0.0,
            d_buffer       REAL NOT NULL DEFAULT 0.0,
            d_baseline     REAL NOT NULL DEFAULT 0.0,
            burst_count    INTEGER NOT NULL DEFAULT 0,
            last_burst_at  REAL,
            updated_at     TEXT NOT NULL DEFAULT (datetime('now')),
            FOREIGN KEY (agent_id) REFERENCES agent_avatars(agent_id) ON DELETE CASCADE
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS agent_epigenetic_imprint (
            agent_id          TEXT PRIMARY KEY,
            v_long_term_avg   REAL NOT NULL DEFAULT 0.0,
            a_long_term_avg   REAL NOT NULL DEFAULT 0.0,
            d_long_term_avg   REAL NOT NULL DEFAULT 0.0,
            imprint_intensity REAL NOT NULL DEFAULT 0.0,
            session_count     INTEGER NOT NULL DEFAULT 0,
            dna_positions     TEXT,
            last_mutation_at  REAL,
            mutation_count    INTEGER NOT NULL DEFAULT 0,
            updated_at        TEXT NOT NULL DEFAULT (datetime('now')),
            FOREIGN KEY (agent_id) REFERENCES agent_avatars(agent_id) ON DELETE CASCADE
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS agent_emotion_session_log (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_id    TEXT NOT NULL,
            v_avg       REAL NOT NULL,
            a_avg       REAL NOT NULL,
            d_avg       REAL NOT NULL,
            session_key TEXT NOT NULL,
            recorded_at REAL NOT NULL,
            FOREIGN KEY (agent_id) REFERENCES agent_avatars(agent_id) ON DELETE CASCADE
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_session_log_agent
        ON agent_emotion_session_log(agent_id, recorded_at DESC)
    """)
    conn.commit()


def ensure_schema() -> None:
    """确保所有 schema 已初始化（幂等操作，进程启动时调用一次）。"""
    with _lock:
        conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
        try:
            _ensure_schema(conn)
            _log.info("db: schema OK — %s", DB_PATH)
        finally:
            conn.close()
