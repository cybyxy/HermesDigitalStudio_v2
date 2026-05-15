"""测试 backend/db/connection.py — 连接池、缓存、健康检查。"""

from __future__ import annotations

import sqlite3
import threading
import time

import pytest

from backend.db.connection import (
    BUSY_TIMEOUT_MS,
    WAL_AUTOCHECKPOINT_PAGES,
    _PooledConnection,
    close_thread_connection,
    connection_context,
    get_connection,
    pool_stats,
    _create_connection,
    _health_check,
)


# ── 连接创建 ────────────────────────────────────────────────────────────────


class TestConnectionCreation:
    """测试连接创建与 pragma 配置。"""

    def test_create_connection_sets_wal_mode(self):
        conn = _create_connection()
        try:
            journal_mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
            assert journal_mode.upper() == "WAL"
        finally:
            conn.close()

    def test_create_connection_sets_busy_timeout(self):
        conn = _create_connection()
        try:
            timeout = conn.execute("PRAGMA busy_timeout").fetchone()[0]
            assert timeout == BUSY_TIMEOUT_MS
        finally:
            conn.close()

    def test_create_connection_sets_wal_autocheckpoint(self):
        conn = _create_connection()
        try:
            pages = conn.execute("PRAGMA wal_autocheckpoint").fetchone()[0]
            assert pages == WAL_AUTOCHECKPOINT_PAGES
        finally:
            conn.close()

    def test_create_connection_sets_foreign_keys(self):
        conn = _create_connection()
        try:
            fk = conn.execute("PRAGMA foreign_keys").fetchone()[0]
            assert fk == 1
        finally:
            conn.close()

    def test_create_connection_sets_row_factory(self):
        conn = _create_connection()
        try:
            assert conn.row_factory is sqlite3.Row
        finally:
            conn.close()

    def test_create_connection_creates_usable_file(self):
        conn = _create_connection()
        try:
            conn.execute("CREATE TABLE IF NOT EXISTS _test_pool (id INTEGER PRIMARY KEY, name TEXT)")
            conn.execute("INSERT INTO _test_pool (name) VALUES (?)", ("hello",))
            conn.commit()
            row = conn.execute("SELECT name FROM _test_pool WHERE id = 1").fetchone()
            assert row[0] == "hello"
            conn.execute("DROP TABLE _test_pool")
        finally:
            conn.close()


# ── 线程本地缓存 ────────────────────────────────────────────────────────────


class TestThreadLocalCaching:
    """测试线程本地连接缓存行为。"""

    def setup_method(self):
        """每个测试前清理当前线程的连接缓存。"""
        close_thread_connection()

    def teardown_method(self):
        close_thread_connection()

    def test_same_thread_returns_same_connection(self):
        conn1 = get_connection()
        conn2 = get_connection()
        assert conn1._underlying_conn is conn2._underlying_conn

    def test_close_is_noop_connection_stays_alive(self):
        conn = get_connection()
        conn.close()
        # 关闭后仍可获取同一连接
        conn2 = get_connection()
        assert conn._underlying_conn is conn2._underlying_conn

    def test_close_thread_connection_releases_connection(self):
        conn1 = get_connection()
        close_thread_connection()
        conn2 = get_connection()
        assert conn1._underlying_conn is not conn2._underlying_conn

    def test_thread_local_separation(self):
        """不同线程获取独立连接（线程本地存储隔离）。"""
        results = {}
        barrier = threading.Barrier(2)

        def _get_conn(tid):
            conn = get_connection()
            # 写入线程特定的 token 来验证连接独立性
            conn.execute(
                "CREATE TABLE IF NOT EXISTS _test_thread (tid INTEGER PRIMARY KEY)"
            )
            conn.execute("INSERT OR REPLACE INTO _test_thread (tid) VALUES (?)", (tid,))
            conn.commit()
            barrier.wait()  # 等待两个线程都写入完成
            # 读取验证
            row = conn.execute(
                "SELECT tid FROM _test_thread WHERE tid = ?", (tid,)
            ).fetchone()
            results[tid] = row[0] if row else None
            close_thread_connection()

        t1 = threading.Thread(target=_get_conn, args=(1,))
        t2 = threading.Thread(target=_get_conn, args=(2,))
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        assert results[1] == 1
        assert results[2] == 2

    def test_connection_is_reusable_after_close_thread(self):
        conn1 = get_connection()
        close_thread_connection()
        conn2 = get_connection()
        # 应该创建新连接
        assert conn2 is not None
        conn2.execute("SELECT 1")


# ── 上下文管理器 ────────────────────────────────────────────────────────────


class TestConnectionContext:
    """测试 connection_context 上下文管理器。"""

    def setup_method(self):
        close_thread_connection()

    def teardown_method(self):
        close_thread_connection()

    def test_context_manager_yields_connection(self):
        with connection_context() as conn:
            assert isinstance(conn, _PooledConnection)
            conn.execute("SELECT 1").fetchone()

    def test_context_manager_cleans_up(self):
        with connection_context() as conn1:
            pass
        # 上下文退出后应释放连接
        conn2 = get_connection()
        assert conn1._underlying_conn is not conn2._underlying_conn

    def test_context_manager_commit_works(self):
        with connection_context() as conn:
            conn.execute("CREATE TABLE IF NOT EXISTS _test_ctx (id INTEGER PRIMARY KEY)")
            conn.execute("INSERT OR REPLACE INTO _test_ctx (id) VALUES (1)")
            conn.commit()

        with connection_context() as conn:
            row = conn.execute("SELECT id FROM _test_ctx WHERE id = 1").fetchone()
            assert row is not None
            conn.execute("DROP TABLE _test_ctx")
            conn.commit()


# ── _PooledConnection 代理 ──────────────────────────────────────────────────


class TestPooledConnection:
    """测试 _PooledConnection 代理行为。"""

    def test_proxy_getattr_passes_through(self):
        raw = sqlite3.connect(":memory:")
        raw.execute("CREATE TABLE t (col INTEGER)")
        pooled = _PooledConnection(raw)
        assert pooled.execute("SELECT 1").fetchone()[0] == 1

    def test_proxy_setattr_passes_through(self):
        raw = sqlite3.connect(":memory:")
        pooled = _PooledConnection(raw)
        pooled.row_factory = None
        assert raw.row_factory is None

    def test_proxy_close_is_noop(self):
        raw = sqlite3.connect(":memory:")
        pooled = _PooledConnection(raw)
        pooled.close()
        # 底层连接仍可用
        raw.execute("SELECT 1").fetchone()

    def test_real_close_closes_underlying(self):
        raw = sqlite3.connect(":memory:")
        pooled = _PooledConnection(raw)
        pooled._real_close()
        with pytest.raises(sqlite3.ProgrammingError):
            raw.execute("SELECT 1")

    def test_proxy_context_manager(self):
        raw = sqlite3.connect(":memory:")
        raw.execute("CREATE TABLE t (col INTEGER)")
        pooled = _PooledConnection(raw)
        with pooled as p:
            assert p.execute("SELECT 1").fetchone()[0] == 1
        # 退出时不应关闭
        raw.execute("SELECT 1").fetchone()


# ── 健康检查 ────────────────────────────────────────────────────────────────


class TestHealthCheck:
    """测试连接健康检查机制。"""

    def setup_method(self):
        close_thread_connection()

    def teardown_method(self):
        close_thread_connection()

    def test_health_check_passes_on_fresh_connection(self):
        conn = get_connection()
        assert _health_check(conn) is True

    def test_health_check_skips_within_interval(self):
        """健康检查应在间隔内跳过查询，直接返回 True。"""
        conn = get_connection()
        # 设置 _last_health_check 为当前时间，模拟刚检查过
        object.__setattr__(conn, "_last_health_check", time.time())
        # _health_check 应直接返回 True（不走实际 SQL 查询）
        assert _health_check(conn) is True

    def test_health_check_after_dead_connection_recovers(self):
        conn = get_connection()
        # 模拟连接断开
        conn._real_close()
        assert _health_check(conn) is True  # 应自动创建新连接
        # 新连接应可用
        conn.execute("SELECT 1").fetchone()


# ── 连接池统计 ──────────────────────────────────────────────────────────────


class TestPoolStats:
    """测试连接池统计信息。"""

    def setup_method(self):
        close_thread_connection()

    def teardown_method(self):
        close_thread_connection()

    def test_pool_stats_has_expected_keys(self):
        stats = pool_stats()
        assert "connections_created" in stats
        assert "connections_closed" in stats
        assert "health_check_failures" in stats
        assert "wal_checkpoints" in stats
        assert "started_at" in stats

    def test_pool_stats_tracks_connections_created(self):
        before = pool_stats()["connections_created"]
        close_thread_connection()
        get_connection()
        after = pool_stats()["connections_created"]
        assert after >= before + 1

    def test_pool_stats_tracks_connections_closed(self):
        get_connection()
        before = pool_stats()["connections_closed"]
        close_thread_connection()
        after = pool_stats()["connections_closed"]
        assert after == before + 1

    def test_pool_stats_started_at_is_recent(self):
        stats = pool_stats()
        assert abs(time.time() - stats["started_at"]) < 10  # 10 秒内开始


# ── Schema 初始化 ───────────────────────────────────────────────────────────


class TestSchemaInit:
    """测试 schema 初始化幂等性。"""

    def setup_method(self):
        close_thread_connection()

    def teardown_method(self):
        close_thread_connection()

    def test_get_connection_initializes_schema(self):
        conn = get_connection()
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
        assert "agent_avatars" in tables
        assert "agent_personality" in tables
        assert "plan_artifacts" in tables
        assert "plan_artifact_steps" in tables
        assert "agent_sessions" in tables

    def test_double_ensure_schema_is_idempotent(self):
        from backend.db.connection import ensure_schema, _ensure_schema

        conn = get_connection()
        # 第二次调用不应报错
        _ensure_schema(conn._underlying_conn)
        # 表仍存在
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
        assert "agent_avatars" in tables

    def test_ensure_schema_from_scratch(self, tmp_path):
        """从全新 DB 调用 ensure_schema() 不报错。"""
        from backend.db.connection import ensure_schema
        import backend.db.connection as _mod

        # 临时覆盖 DB_PATH
        orig = _mod.DB_PATH
        try:
            _mod.DB_PATH = tmp_path / "test.db"
            ensure_schema()
        finally:
            _mod.DB_PATH = orig

    def test_schema_has_required_indexes(self):
        conn = get_connection()
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index'"
        ).fetchall()
        indexes = {r[0] for r in rows}
        assert "idx_agent_sessions_agent_id" in indexes
        assert "idx_agent_sessions_last_used" in indexes
