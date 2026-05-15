"""PAD 情绪引擎 — Agent 的三维情绪模型。

提供 per-agent 的情绪管理：
- **valence (愉悦度)**: -1~1，正=高兴，负=低落
- **arousal (唤醒度)**: -1~1，正=兴奋，负=平静
- **dominance (支配度)**: -1~1，正=自信，负=顺从

情绪更新规则：
- 用户正面消息 → valence +0.1
- 用户负面消息 → valence -0.1
- 复杂任务完成 → arousal +0.15
- 时间衰减 → 每维每小时向 0 回归 0.01

使用::

    from backend.services.emotion import get_emotion_service

    emotion = get_emotion_service()
    state = await emotion.get_emotion("agent-alice")
    await emotion.update_emotion("agent-alice", valence_delta=0.1, trigger="user_praise")
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

_log = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════════════════════════
# 配置常量
# ══════════════════════════════════════════════════════════════════════════════

VALENCE_MIN = -1.0
VALENCE_MAX = 1.0
AROUSAL_MIN = -1.0
AROUSAL_MAX = 1.0
DOMINANCE_MIN = -1.0
DOMINANCE_MAX = 1.0
TIME_DECAY_RATE = 0.01  # 每小时回归量

# 中文正面关键词
PRAISE_KEYWORDS_ZH = [
    "太棒了", "很好", "厉害", "优秀", "完美", "不错", "做得好", "强",
]
# 英文正面关键词
PRAISE_KEYWORDS_EN = [
    "great", "excellent", "amazing", "well done", "awesome",
    "good job", "fantastic", "bravo",
]
# 中文负面关键词
CRITICISM_KEYWORDS_ZH = [
    "糟糕", "很差", "不好", "失望", "没用", "垃圾", "差劲",
]
# 英文负面关键词
CRITICISM_KEYWORDS_EN = [
    "wrong", "bad", "terrible", "useless", "disappointed",
    "awful", "horrible",
]

# ══════════════════════════════════════════════════════════════════════════════
# 单例管理
# ══════════════════════════════════════════════════════════════════════════════

_emotion_service: Optional[EmotionEngine] = None


def get_emotion_service() -> EmotionEngine:
    """获取 EmotionEngine 单例（首次调用时创建）。"""
    global _emotion_service
    if _emotion_service is None:
        _emotion_service = EmotionEngine()
    return _emotion_service


# ══════════════════════════════════════════════════════════════════════════════
# 服务类
# ══════════════════════════════════════════════════════════════════════════════


class EmotionEngine:
    """PAD 三维情绪引擎。

    管理所有 Agent 的 valence / arousal / dominance 状态，
    以及情绪更新和后台时间衰减循环。
    """

    def __init__(self):
        self._running = False
        self._task: Optional[asyncio.Task] = None

    # ── 生命周期 ──────────────────────────────────────────────────────────

    async def start(self) -> None:
        """启动后台时间衰减循环。"""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._time_decay_loop())
        _log.info("emotion: engine started")

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
        _log.info("emotion: engine stopped")

    async def _time_decay_loop(self) -> None:
        """后台循环：每 3600 秒对所有 Agent 执行情绪时间衰减。"""
        while self._running:
            try:
                await asyncio.sleep(3600)
                if not self._running:
                    break

                agent_ids = self._get_all_emotion_agent_ids()
                for agent_id in agent_ids:
                    try:
                        await self._apply_time_decay(agent_id)
                    except Exception as e:
                        _log.debug("emotion: decay failed for agent=%s: %s", agent_id, e)
            except asyncio.CancelledError:
                break
            except Exception as e:
                _log.warning("emotion: decay loop error: %s", e)

    # ── 查询 ──────────────────────────────────────────────────────────────

    async def get_emotion(self, agent_id: str) -> dict:
        """获取 Agent 当前情绪状态。"""
        from backend.db.connection import get_connection
        conn = get_connection()
        try:
            row = conn.execute(
                "SELECT agent_id, valence, arousal, dominance, updated_at "
                "FROM agent_emotion WHERE agent_id = ?",
                (agent_id,),
            ).fetchone()
            if row:
                return {
                    "agent_id": row[0],
                    "valence": row[1],
                    "arousal": row[2],
                    "dominance": row[3],
                    "updated_at": row[4],
                }
            return {
                "agent_id": agent_id,
                "valence": 0.0,
                "arousal": 0.0,
                "dominance": 0.0,
                "updated_at": "",
            }
        finally:
            conn.close()

    async def get_emotion_history(self, agent_id: str, limit: int = 30) -> list[dict]:
        """获取 Agent 最近 N 条情绪变化历史。"""
        from backend.db.connection import get_connection
        conn = get_connection()
        try:
            rows = conn.execute(
                "SELECT agent_id, valence, arousal, dominance, trigger, timestamp "
                "FROM agent_emotion_log WHERE agent_id = ? "
                "ORDER BY timestamp DESC LIMIT ?",
                (agent_id, limit),
            ).fetchall()
            return [
                {
                    "agent_id": row[0],
                    "valence": row[1],
                    "arousal": row[2],
                    "dominance": row[3],
                    "trigger": row[4],
                    "timestamp": row[5],
                }
                for row in reversed(rows)
            ]
        finally:
            conn.close()

    # ── 更新 ──────────────────────────────────────────────────────────────

    async def update_emotion(self, agent_id: str,
                             valence_delta: float = 0.0,
                             arousal_delta: float = 0.0,
                             dominance_delta: float = 0.0,
                             trigger: str = "") -> dict:
        """更新情绪并写入日志。

        所有维度 clamp 到 [-1, 1]。
        """
        current = await self.get_emotion(agent_id)
        new_valence = max(VALENCE_MIN, min(VALENCE_MAX,
                                           current["valence"] + valence_delta))
        new_arousal = max(AROUSAL_MIN, min(AROUSAL_MAX,
                                           current["arousal"] + arousal_delta))
        new_dominance = max(DOMINANCE_MIN, min(DOMINANCE_MAX,
                                               current["dominance"] + dominance_delta))

        from backend.db.connection import get_connection
        conn = get_connection()
        try:
            conn.execute(
                "INSERT OR REPLACE INTO agent_emotion "
                "(agent_id, valence, arousal, dominance, updated_at) "
                "VALUES (?, ?, ?, ?, datetime('now'))",
                (agent_id, new_valence, new_arousal, new_dominance),
            )
            conn.execute(
                "INSERT INTO agent_emotion_log "
                "(agent_id, valence, arousal, dominance, trigger) "
                "VALUES (?, ?, ?, ?, ?)",
                (agent_id, new_valence, new_arousal, new_dominance, trigger),
            )
            conn.commit()
        finally:
            conn.close()

        _log.debug(
            "emotion: update agent=%s valence=%.2f→%.2f arousal=%.2f→%.2f "
            "dominance=%.2f→%.2f trigger=%s",
            agent_id,
            current["valence"], new_valence,
            current["arousal"], new_arousal,
            current["dominance"], new_dominance,
            trigger,
        )

        return await self.get_emotion(agent_id)

    # ── 情感分析 ──────────────────────────────────────────────────────────

    @staticmethod
    def analyze_sentiment(text: str) -> dict[str, float]:
        """关键词分析用户消息情感。

        Returns:
            {'valence': 0.1}  正面消息
            {'valence': -0.1} 负面消息
            {}                中性
        """
        if not text:
            return {}

        t = text.lower()

        # 检查正面关键词
        for kw in PRAISE_KEYWORDS_ZH:
            if kw in text:
                return {"valence": 0.1}
        for kw in PRAISE_KEYWORDS_EN:
            if kw in t:
                return {"valence": 0.1}

        # 检查负面关键词
        for kw in CRITICISM_KEYWORDS_ZH:
            if kw in text:
                return {"valence": -0.1}
        for kw in CRITICISM_KEYWORDS_EN:
            if kw in t:
                return {"valence": -0.1}

        return {}

    # ── 时间衰减 ──────────────────────────────────────────────────────────

    async def _apply_time_decay(self, agent_id: str) -> None:
        """对单个 Agent 执行情绪时间衰减（每维向 0 回归 0.01）。"""
        current = await self.get_emotion(agent_id)

        # 计算每维的衰减方向（向 0 移动）
        v = current["valence"]
        a = current["arousal"]
        d = current["dominance"]

        v_delta = -TIME_DECAY_RATE if v > 0 else (TIME_DECAY_RATE if v < 0 else 0)
        a_delta = -TIME_DECAY_RATE if a > 0 else (TIME_DECAY_RATE if a < 0 else 0)
        d_delta = -TIME_DECAY_RATE if d > 0 else (TIME_DECAY_RATE if d < 0 else 0)

        if v_delta == 0 and a_delta == 0 and d_delta == 0:
            return  # 已经是 0 状态，无需写入

        await self.update_emotion(agent_id, v_delta, a_delta, d_delta, "time_decay")

    # ── 内部辅助 ──────────────────────────────────────────────────────────

    @staticmethod
    def _get_all_emotion_agent_ids() -> list[str]:
        """获取所有有情绪记录的 Agent ID 列表。"""
        from backend.db.connection import get_connection
        conn = get_connection()
        try:
            rows = conn.execute("SELECT agent_id FROM agent_emotion").fetchall()
            return [r[0] for r in rows]
        except Exception:
            return []
        finally:
            conn.close()
