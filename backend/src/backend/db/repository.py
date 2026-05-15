"""Repository 基类 — 为 DB 操作提供统一连接管理和错误处理。

所有 Repository 子类通过构造函数接收连接管理器和数据库连接，
不再直接调用模块级 ``get_connection()``，便于单元测试时注入 mock 连接。

用法::

    class PlanRepository(Repository):
        def find_by_session(self, session_id: str) -> list[dict]:
            return self.fetch_all(
                "SELECT * FROM plan_artifacts WHERE session_id = ?",
                (session_id,)
            )

    repo = PlanRepository(get_connection())
    plans = repo.find_by_session("abc-123")
"""

from __future__ import annotations

import logging
import sqlite3
from typing import Any, Optional, Sequence

_log = logging.getLogger(__name__)


class RepositoryError(Exception):
    """Repository 层错误，包装底层 DB 异常以提供更好上下文。"""

    def __init__(self, message: str, operation: str = "", table: str = "") -> None:
        super().__init__(message)
        self.operation = operation
        self.table = table


class Repository:
    """DB Repository 基类。

    提供：
    - 线程安全的连接注入
    - ``execute`` / ``executemany`` / ``fetch_one`` / ``fetch_all`` 便捷方法
    - 统一的错误日志 + 异常抛出（替代旧的静默吞异常模式）
    """

    __slots__ = ("_conn", "_name")

    def __init__(self, conn: sqlite3.Connection, *, name: str = "") -> None:
        """初始化 Repository。

        Args:
            conn: 数据库连接（sqlite3.Connection 或其代理）
            name: Repository 名称（用于日志和错误消息）
        """
        object.__setattr__(self, "_conn", conn)
        object.__setattr__(self, "_name", name or type(self).__name__)

    @property
    def conn(self) -> sqlite3.Connection:
        """获取当前 Repository 的数据库连接。"""
        return object.__getattribute__(self, "_conn")

    # ── 核心 DML 方法 ────────────────────────────────────────────────────────

    def execute(self, sql: str, params: Sequence[Any] = ()) -> sqlite3.Cursor:
        """执行 SQL 语句，返回 cursor。"""
        try:
            return self.conn.execute(sql, params)
        except sqlite3.Error as e:
            _log.error("[%s] SQL Error: %s | SQL: %r | params: %r", self._name, e, sql, params)
            raise RepositoryError(str(e), operation="execute") from e

    def executemany(self, sql: str, params_list: Sequence[Sequence[Any]]) -> sqlite3.Cursor:
        """批量执行 SQL 语句。"""
        try:
            return self.conn.executemany(sql, params_list)
        except sqlite3.Error as e:
            _log.error("[%s] SQL Error: %s | SQL: %r", self._name, e, sql)
            raise RepositoryError(str(e), operation="executemany") from e

    def fetch_one(self, sql: str, params: Sequence[Any] = ()) -> Optional[sqlite3.Row]:
        """查询单行结果，无结果返回 None。"""
        try:
            row = self.conn.execute(sql, params).fetchone()
            return row if row is not None else None
        except sqlite3.Error as e:
            _log.error("[%s] SQL Error: %s | SQL: %r | params: %r", self._name, e, sql, params)
            raise RepositoryError(str(e), operation="fetch_one") from e

    def fetch_all(self, sql: str, params: Sequence[Any] = ()) -> list[sqlite3.Row]:
        """查询所有结果，无结果返回空列表。"""
        try:
            return self.conn.execute(sql, params).fetchall()
        except sqlite3.Error as e:
            _log.error("[%s] SQL Error: %s | SQL: %r | params: %r", self._name, e, sql, params)
            raise RepositoryError(str(e), operation="fetch_all") from e

    def fetch_val(self, sql: str, params: Sequence[Any] = (), default: Any = None) -> Any:
        """查询单个标量值，无结果返回 default。"""
        try:
            row = self.conn.execute(sql, params).fetchone()
            if row is not None:
                return row[0]
            return default
        except sqlite3.Error as e:
            _log.error("[%s] SQL Error: %s | SQL: %r | params: %r", self._name, e, sql, params)
            raise RepositoryError(str(e), operation="fetch_val") from e

    def commit(self) -> None:
        """提交当前事务。"""
        try:
            self.conn.commit()
        except sqlite3.Error as e:
            _log.error("[%s] commit failed: %s", self._name, e)
            raise RepositoryError(str(e), operation="commit") from e
