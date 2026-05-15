"""双维度能量管理服务 — Agent 的"饱食度 + 生物电流"模型。

提供 per-agent 的能量状态管理和自动回落机制：
- **饱食度 (Satiety)**: int 0-100，默认 80。随推理消耗递减，正向交互递增。
- **生物电流 (BioCurrent)**: int 0-10，默认 3。决定知识图谱遍历深度，任务驱动提升。
- **热度耦合**: 生物电流越高，饱食度消耗越快。
- **阈值行为**: satiety<30 节能模式, bio_current>8 电涌, bio_current>=10 强制放电。
- **后台回落**: 每分钟对所有 Agent 执行 bio_current 线性回落。

使用::

    from backend.services.energy import get_energy_service

    energy = get_energy_service()
    state = await energy.get_energy("agent-alice")
    await energy.apply_inference_cost("agent-alice")
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Optional

from backend.core.config import get_config

_log = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════════════════════════
# 配置常量
# ══════════════════════════════════════════════════════════════════════════════

SATIETY_MAX = 100
SATIETY_MIN = 0
SATIETY_DEFAULT = 80
SATIETY_LOW_THRESHOLD = 30      # 进入节能模式
SATIETY_CRITICAL = 10            # 极度饥饿

BIO_CURRENT_MAX = 10
BIO_CURRENT_MIN = 0
BIO_CURRENT_DEFAULT = 3
BIO_CURRENT_SURGE = 8            # 电涌阈值
BIO_CURRENT_FORCE_DISCHARGE = 10  # 强制放电
BIO_CURRENT_DECAY_RATE = 1.0     # 每分钟回落

BASE_SATIETY_DECAY_PER_HOUR = 5.0
BASE_SATIETY_DECAY_PER_INFERENCE = 0.5

# 热度-饱食度消耗倍率
CURRENT_CONSUMPTION_MULTIPLIER: dict[tuple[int, int], float] = {
    (0, 3): 1.0,
    (4, 6): 1.5,
    (7, 8): 2.0,
    (9, 10): 3.0,
}

# 正向交互饱食度恢复值
POSITIVE_INTERACTION_DELTA: dict[str, int] = {
    "task_complete": 15,
    "user_praise": 10,
    "encourage": 5,
}

# bio_current 任务驱动增量
TASK_BIO_CURRENT_DELTA: dict[str, int] = {
    "simple": 2,
    "medium": 5,
    "large": 8,
}

# ══════════════════════════════════════════════════════════════════════════════
# 单例管理
# ══════════════════════════════════════════════════════════════════════════════

_energy_service: Optional[EnergyService] = None


def get_energy_service() -> EnergyService:
    """获取 EnergyService 单例（首次调用时创建）。"""
    global _energy_service
    if _energy_service is None:
        _energy_service = EnergyService()
    return _energy_service


# ══════════════════════════════════════════════════════════════════════════════
# 服务类
# ══════════════════════════════════════════════════════════════════════════════


class EnergyService:
    """双维度能量管理服务。

    管理所有 Agent 的饱食度 (satiety) 和生物电流 (bio_current) 状态，
    以及对应的模式切换逻辑。
    """

    def __init__(self):
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._surge_start: dict[str, float] = {}  # agent_id → 电涌开始时间戳

    # ── 生命周期 ──────────────────────────────────────────────────────────

    async def start(self) -> None:
        """启动后台 bio_current 回落循环。"""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._decay_bio_current_loop())
        _log.info("energy: service started")

    async def stop(self) -> None:
        """停止后台循环。"""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        _log.info("energy: service stopped")

    async def _decay_bio_current_loop(self) -> None:
        """后台循环：每 60 秒对所有 Agent 执行 bio_current 回落、空闲衰减、过载检查。"""
        while self._running:
            try:
                await asyncio.sleep(60)
                if not self._running:
                    break

                agent_ids = self._get_all_agent_ids()
                for agent_id in agent_ids:
                    try:
                        await self._apply_bio_current_decay(agent_id)
                        await self._apply_idle_satiety_decay(agent_id)
                        await self._check_overload(agent_id)
                    except Exception as e:
                        _log.debug("energy: decay failed for agent=%s: %s", agent_id, e)
            except asyncio.CancelledError:
                break
            except Exception as e:
                _log.warning("energy: decay loop error: %s", e)

    async def _apply_bio_current_decay(self, agent_id: str) -> None:
        """对单个 Agent 执行 bio_current 回落 (每分钟 -1)。"""
        current = self._get_bio_current(agent_id)
        if current > BIO_CURRENT_DEFAULT:
            await self.update_bio_current(agent_id, -BIO_CURRENT_DECAY_RATE, "decay_tick")

    async def _apply_idle_satiety_decay(self, agent_id: str) -> None:
        """对单个 Agent 执行空闲饱食度衰减（每小时 -5 × 热量倍率）。"""
        from backend.db.connection import get_connection
        conn = get_connection()
        try:
            row = conn.execute(
                "SELECT (julianday('now') - julianday(updated_at)) * 24 "
                "FROM agent_energy WHERE agent_id = ?",
                (agent_id,),
            ).fetchone()
            if row and row[0] is not None and row[0] > 0.016:  # > 1 分钟
                await self.apply_idle_decay(agent_id, row[0] / 60)  # 按分钟衰减
        finally:
            conn.close()

    async def _check_overload(self, agent_id: str) -> None:
        """检查电涌是否超过 10 分钟，触发过载保护强制放电。"""
        if agent_id in self._surge_start:
            elapsed = time.time() - self._surge_start[agent_id]
            if elapsed > 600:  # 10 分钟
                _log.info("energy: overload protection agent=%s surge_elapsed=%.0fs", agent_id, elapsed)
                await self._force_discharge(agent_id)
                self._surge_start.pop(agent_id, None)

    # ── 查询 ──────────────────────────────────────────────────────────────

    async def get_energy(self, agent_id: str) -> dict:
        """获取 Agent 当前能量状态。"""
        from backend.db.connection import get_connection
        conn = get_connection()
        try:
            row = conn.execute(
                "SELECT agent_id, satiety, bio_current, mode, updated_at "
                "FROM agent_energy WHERE agent_id = ?",
                (agent_id,),
            ).fetchone()
            if row:
                return {
                    "agent_id": row[0],
                    "satiety": row[1],
                    "bio_current": row[2],
                    "mode": row[3],
                    "updated_at": row[4],
                }
            # 首次访问：返回默认值
            return self._default_state(agent_id)
        finally:
            conn.close()

    async def get_energy_logs(self, agent_id: str, limit: int = 50) -> list[dict]:
        """查询能量变化日志。"""
        from backend.db.connection import get_connection
        conn = get_connection()
        try:
            rows = conn.execute(
                "SELECT metric, reason, delta, value_before, value_after, timestamp "
                "FROM agent_energy_log WHERE agent_id = ? "
                "ORDER BY timestamp DESC LIMIT ?",
                (agent_id, limit),
            ).fetchall()
            return [
                {
                    "metric": r[0],
                    "reason": r[1],
                    "delta": r[2],
                    "value_before": r[3],
                    "value_after": r[4],
                    "timestamp": r[5],
                }
                for r in rows
            ]
        finally:
            conn.close()

    async def is_power_save(self, agent_id: str) -> bool:
        """检查 Agent 是否处于节能模式（行为门控用）。

        在 satiety < 30 或 mode == 'power_save' 时拒绝新任务。
        """
        state = await self.get_energy(agent_id)
        return state["mode"] == "power_save" or state["satiety"] < SATIETY_LOW_THRESHOLD

    # ── 更新 ──────────────────────────────────────────────────────────────

    async def update_satiety(self, agent_id: str, delta: float, reason: str) -> dict:
        """更新饱食度。

        - 正值增加（恢复），负值减少（消耗）
        - 消耗时叠加 bio_current 消耗倍率
        - 触发阈值检查
        """
        current = self._get_satiety(agent_id)
        actual_delta = delta

        if delta < 0:
            bio_current = self._get_bio_current(agent_id)
            multiplier = self._get_current_multiplier(bio_current)
            actual_delta = delta * multiplier

        new_value = max(SATIETY_MIN, min(SATIETY_MAX, current + actual_delta))
        from backend.db.connection import get_connection
        conn = get_connection()
        try:
            conn.execute(
                "INSERT OR REPLACE INTO agent_energy (agent_id, satiety, bio_current, mode, updated_at) "
                "VALUES (?, ?, ?, 'normal', datetime('now'))",
                (agent_id, new_value, self._get_bio_current(agent_id)),
            )
            conn.execute(
                "INSERT INTO agent_energy_log (agent_id, metric, reason, delta, value_before, value_after) "
                "VALUES (?, 'satiety', ?, ?, ?, ?)",
                (agent_id, reason, actual_delta, current, new_value),
            )
            conn.commit()
        finally:
            conn.close()

        _log.debug(
            "energy: satiety update agent=%s delta=%.1f(actual=%.1f) %d→%d reason=%s",
            agent_id, delta, actual_delta, current, new_value, reason,
        )

        await self.check_thresholds(agent_id)
        return await self.get_energy(agent_id)

    async def update_bio_current(self, agent_id: str, delta: float, reason: str) -> dict:
        """更新生物电流。

        - 限制在 [0, 10] 范围
        - bio_current >= 10 触发强制放电
        """
        current = self._get_bio_current(agent_id)
        new_value = max(BIO_CURRENT_MIN, min(BIO_CURRENT_MAX, current + delta))
        from backend.db.connection import get_connection
        conn = get_connection()
        try:
            conn.execute(
                "INSERT OR REPLACE INTO agent_energy (agent_id, satiety, bio_current, mode, updated_at) "
                "VALUES (?, ?, ?, 'normal', datetime('now'))",
                (agent_id, self._get_satiety(agent_id), new_value),
            )
            conn.execute(
                "INSERT INTO agent_energy_log (agent_id, metric, reason, delta, value_before, value_after) "
                "VALUES (?, 'bio_current', ?, ?, ?, ?)",
                (agent_id, reason, delta, current, new_value),
            )
            conn.commit()
        finally:
            conn.close()

        _log.debug(
            "energy: bio_current update agent=%s delta=%.1f %d→%d reason=%s",
            agent_id, delta, current, new_value, reason,
        )

        if new_value >= BIO_CURRENT_FORCE_DISCHARGE:
            await self._force_discharge(agent_id)

        await self.check_thresholds(agent_id)
        return await self.get_energy(agent_id)

    async def reset_energy(self, agent_id: str, satiety: int,
                           bio_current: int, mode: str = "normal") -> dict:
        """管理员重置能量状态。"""
        from backend.db.connection import get_connection
        conn = get_connection()
        try:
            conn.execute(
                "INSERT OR REPLACE INTO agent_energy (agent_id, satiety, bio_current, mode, updated_at) "
                "VALUES (?, ?, ?, ?, datetime('now'))",
                (agent_id, satiety, bio_current, mode),
            )
            conn.commit()
            _log.info("energy: reset agent=%s satiety=%d bio_current=%d mode=%s",
                      agent_id, satiety, bio_current, mode)
        finally:
            conn.close()
        return await self.get_energy(agent_id)

    # ── 预设事件 ──────────────────────────────────────────────────────────

    async def apply_idle_decay(self, agent_id: str, hours: float) -> dict:
        """空闲衰减：satiety -= BASE * hours * current_multiplier"""
        bio_current = self._get_bio_current(agent_id)
        multiplier = self._get_current_multiplier(bio_current)
        delta = -BASE_SATIETY_DECAY_PER_HOUR * hours * multiplier
        return await self.update_satiety(agent_id, delta, "idle_tick")

    async def apply_inference_cost(self, agent_id: str) -> dict:
        """推理消耗：satiety -= 0.5 × multiplier; bio_current += 0.2"""
        bio_current = self._get_bio_current(agent_id)
        multiplier = self._get_current_multiplier(bio_current)
        satiety_delta = -BASE_SATIETY_DECAY_PER_INFERENCE * multiplier
        await self.update_satiety(agent_id, satiety_delta, "inference")
        await self.update_bio_current(agent_id, 0.2, "inference")
        return await self.get_energy(agent_id)

    async def apply_task_submit(self, agent_id: str, complexity: str = "medium") -> dict:
        """任务提交：根据复杂度增加 bio_current。"""
        delta = TASK_BIO_CURRENT_DELTA.get(complexity, 5)
        return await self.update_bio_current(agent_id, delta, f"task_submit_{complexity}")

    async def apply_positive_interaction(self, agent_id: str,
                                         interaction_type: str = "task_complete") -> dict:
        """正向交互恢复饱食度。"""
        delta = POSITIVE_INTERACTION_DELTA.get(interaction_type, 5)
        return await self.update_satiety(agent_id, float(delta), interaction_type)

    # ── 阈值检查 ──────────────────────────────────────────────────────────

    async def check_thresholds(self, agent_id: str) -> dict:
        """检查阈值并触发模式切换。

        优先级（从高到低）：
        1. satiety < 10 → power_save（极度饥饿）
        2. bio_current >= 10 → 立即强制放电
        3. bio_current > 8 → surge
        4. satiety < 30 → power_save
        5. 其他 → normal
        """
        state = await self.get_energy(agent_id)
        satiety = state["satiety"]
        bio_current = state["bio_current"]
        new_mode = state["mode"]

        # 优先级 1: 极度饥饿
        if satiety < SATIETY_CRITICAL:
            new_mode = "power_save"
        # 优先级 2: 强制放电
        elif bio_current >= BIO_CURRENT_FORCE_DISCHARGE:
            new_mode = "forced_discharge"
        # 优先级 3: 电涌
        elif bio_current > BIO_CURRENT_SURGE:
            new_mode = "surge"
            # 追踪电涌开始时间（用于过载保护）
            if agent_id not in self._surge_start:
                self._surge_start[agent_id] = time.time()
        # 优先级 4: 节能
        elif satiety < SATIETY_LOW_THRESHOLD:
            new_mode = "power_save"
        else:
            new_mode = "normal"

        # 退出电涌时清理追踪
        if bio_current <= BIO_CURRENT_SURGE and agent_id in self._surge_start:
            self._surge_start.pop(agent_id, None)

        if new_mode != state["mode"]:
            from backend.db.connection import get_connection
            conn = get_connection()
            try:
                conn.execute(
                    "UPDATE agent_energy SET mode = ?, updated_at = datetime('now') WHERE agent_id = ?",
                    (new_mode, agent_id),
                )
                conn.commit()
            finally:
                conn.close()
            _log.info("energy: mode switch agent=%s %s → %s", agent_id, state["mode"], new_mode)

        return await self.get_energy(agent_id)

    async def _force_discharge(self, agent_id: str) -> None:
        """强制放电：bio_current → 5，模式 = forced_discharge。"""
        from backend.db.connection import get_connection
        conn = get_connection()
        try:
            conn.execute(
                "UPDATE agent_energy SET bio_current = 5, mode = 'forced_discharge', "
                "updated_at = datetime('now') WHERE agent_id = ?",
                (agent_id,),
            )
            conn.commit()
            _log.info("energy: forced discharge agent=%s", agent_id)
        finally:
            conn.close()

    # ── 内部辅助 ──────────────────────────────────────────────────────────

    @staticmethod
    def _default_state(agent_id: str) -> dict:
        """返回默认能量状态。"""
        return {
            "agent_id": agent_id,
            "satiety": SATIETY_DEFAULT,
            "bio_current": BIO_CURRENT_DEFAULT,
            "mode": "normal",
            "updated_at": "",
        }

    @staticmethod
    def _get_current_multiplier(bio_current: int) -> float:
        """获取当前生物电流对应的消耗倍率。"""
        for (lo, hi), mult in CURRENT_CONSUMPTION_MULTIPLIER.items():
            if lo <= bio_current <= hi:
                return mult
        return 1.0

    @staticmethod
    def _get_satiety(agent_id: str) -> int:
        """获取饱食度（带默认值）。"""
        from backend.db.connection import get_connection
        conn = get_connection()
        try:
            row = conn.execute(
                "SELECT satiety FROM agent_energy WHERE agent_id = ?",
                (agent_id,),
            ).fetchone()
            return row[0] if row else SATIETY_DEFAULT
        finally:
            conn.close()

    @staticmethod
    def _get_bio_current(agent_id: str) -> int:
        """获取生物电流（带默认值）。"""
        from backend.db.connection import get_connection
        conn = get_connection()
        try:
            row = conn.execute(
                "SELECT bio_current FROM agent_energy WHERE agent_id = ?",
                (agent_id,),
            ).fetchone()
            return row[0] if row else BIO_CURRENT_DEFAULT
        finally:
            conn.close()

    @staticmethod
    def _get_all_agent_ids() -> list[str]:
        """获取所有有能量记录的 Agent ID 列表。"""
        from backend.db.connection import get_connection
        conn = get_connection()
        try:
            rows = conn.execute("SELECT agent_id FROM agent_energy").fetchall()
            return [r[0] for r in rows]
        except Exception:
            return []
        finally:
            conn.close()
