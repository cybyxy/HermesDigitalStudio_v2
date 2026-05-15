"""心跳推理循环 — 后台 asyncio 任务。

每隔 heartbeat_interval_seconds 秒：
1. 从 Neo4j 知识图谱随机游走收集节点
2. 通过 Hermes Agent 子进程（default profile）调用 LLM 进行推理
3. 推理过程中的 thinking.delta 事件实时推送到前端 SSE
4. 判断推理结果是否有意义
5. 有意义的推送到前端 SSE + 飞书（如果网关可用）

用户活动感知：
- 每次循环前查询 agent_sessions.last_used_at
- 若距上次用户输入 < idle_timeout_seconds，跳过本轮（用户正在交互）
- 若距上次用户输入 >= idle_timeout_seconds，执行心跳推理
"""

from __future__ import annotations

import asyncio
import json
import logging
import threading
import time

from backend.core.config import get_config

_log = logging.getLogger(__name__)

_HEARTBEAT_PROMPT = (
    "你是一个知识图谱分析助手。以下是从 Agent "
    "的知识图谱中随机游走收集的节点信息：\n\n"
    "{nodes_text}\n\n"
    "请基于这些信息进行推理，分析：\n"
    "1. 这些概念之间可能有什么隐含联系？\n"
    "2. 有什么值得注意的模式或洞察？\n\n"
    "请以 JSON 格式返回，不要包含任何其他文字：\n"
    '{{"content": "你的推理分析（简洁，2-5句话）", "is_meaningful": true/false}}\n\n'
    "is_meaningful 判断标准：分析结果是否包含新的、非显而易见的洞察，而非简单复述节点信息。"
)


class HeartbeatService:
    """管理心跳推理循环的后台 asyncio 任务。

    用户活动感知：
    - 每次循环前检查 agent_sessions.last_used_at
    - 若距上次用户输入 < idle_timeout_seconds，跳过本轮（用户正在交互）
    - 若距上次用户输入 >= idle_timeout_seconds，执行心跳推理
    """

    _instance: HeartbeatService | None = None

    def __init__(self):
        self._running = False
        self._task: asyncio.Task | None = None
        self._paused = False
        self._paused_at: float = 0.0
        self._last_reasoned: dict[str, float] = {}  # agent_id → 上次推理时间
        self._last_heartbeat: dict[str, float] = {}  # agent_id → 上次心跳时间（用于能量联动间隔）
        self._recent_node_sets: dict[str, list[frozenset[str]]] = {}  # agent_id → 最近 10 个游走节点集合

    async def start(self):
        """启动心跳循环。"""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._loop())
        _log.info("heartbeat: 心跳推理循环已启动 (interval=%.0fs, idle_timeout=%.0fs)",
                  get_config().heartbeat_interval_seconds,
                  get_config().heartbeat_idle_timeout_seconds)

    async def stop(self):
        """停止心跳循环。"""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        _log.info("heartbeat: 心跳推理循环已停止")

    # ── 空闲检测 ────────────────────────────────────────────────────────

    async def _get_last_user_activity(self) -> float:
        """查询所有 agent session 中最近的 last_used_at 时间戳（在线程池执行，避免阻塞事件循环）。

        返回 0.0 表示无记录（首次启动，允许心跳立即运行）。
        """
        try:
            from backend.services import agent_db as _agent_db

            sessions = await asyncio.get_running_loop().run_in_executor(
                None, _agent_db.list_all_sessions,
            )
            if not sessions:
                return 0.0
            latest = max(
                (s.get("lastUsedAt") or 0 for s in sessions),
                default=0.0,
            )
            return latest
        except Exception:
            return 0.0

    # ── 主循环 ──────────────────────────────────────────────────────────

    async def _loop(self):
        """主循环：检查空闲状态 → 执行心跳 → sleep。"""
        interval = get_config().heartbeat_interval_seconds
        idle_timeout = get_config().heartbeat_idle_timeout_seconds
        loop_count = 0

        while self._running:
            try:
                idle = time.time() - await self._get_last_user_activity()

                if idle < idle_timeout:
                    if not self._paused:
                        self._paused = True
                        self._paused_at = time.time()
                        _log.info("heartbeat: 检测到用户活动，暂停心跳推理 (idle=%.0fs < %.0fs)",
                                  idle, idle_timeout)
                    await asyncio.sleep(interval)
                    continue

                if self._paused:
                    _log.info("heartbeat: 用户空闲 %.0f 秒，恢复心跳推理", idle)
                    self._paused = False

                agent_ids = self._get_active_agent_ids()
                _log.info("heartbeat: 新一轮心跳循环 (agents=%s)", agent_ids)
                for aid in agent_ids:
                    # 每个 agent 心跳前重新检查空闲状态，用户中途输入时能及时感知
                    mid_idle = time.time() - await self._get_last_user_activity()
                    if mid_idle < idle_timeout:
                        _log.debug("heartbeat: 心跳中途检测到用户活动，跳过剩余 agent")
                        break
                    await self._heartbeat_for_agent(aid)

            except asyncio.CancelledError:
                raise
            except Exception as e:
                _log.warning("heartbeat: 主循环异常: %s", e)

            # M4.1: 每 10 次心跳循环为每个 agent 执行髓鞘化维护
            loop_count += 1
            if loop_count % 10 == 0:
                try:
                    from backend.services.myelination import MyelinationEngine
                    me = MyelinationEngine()
                    for aid in agent_ids:
                        await me.run_maintenance(aid)
                except Exception as e:
                    _log.debug("myelination: maintenance skipped in heartbeat: %s", e)

            await asyncio.sleep(interval)

    def _get_active_agent_ids(self) -> list[str]:
        """获取所有活跃的 Agent ID 列表。"""
        try:
            from backend.services.agent import list_agents as _list_agents
            agents = _list_agents()
            return [a.get("agentId", "") for a in agents if a.get("agentId")]
        except Exception as e:
            _log.warning("heartbeat: 获取 agent 列表失败: %s", e)
            return []

    # ── 单个 Agent 心跳 ─────────────────────────────────────────────────

    async def _heartbeat_for_agent(self, agent_id: str):
        """单个 agent 的心跳周期。"""
        # 0. 能量联动：根据饱食度/生物电流动态调整心跳间隔
        try:
            from backend.services.energy import get_energy_service
            energy = await get_energy_service().get_energy(agent_id)
            satiety = energy["satiety"]
            bio = energy["bio_current"]

            cfg = get_config()
            interval_map = cfg.heartbeat_level_interval_map
            if satiety < 30:
                dyn_interval = interval_map.get("satiety_lt_30", 90)
            elif satiety < 60:
                dyn_interval = interval_map.get("satiety_30_60", 60)
            elif satiety < 80:
                dyn_interval = interval_map.get("satiety_60_80", 30)
            else:
                dyn_interval = interval_map.get("satiety_gt_80", 15)

            if bio > 8:
                dyn_interval = dyn_interval / 2

            now = time.time()
            last = self._last_heartbeat.get(agent_id, 0)
            if now - last < dyn_interval:
                return  # 未到能量联动间隔，跳过本轮心跳
            self._last_heartbeat[agent_id] = now
        except Exception as e:
            _log.debug("heartbeat: energy check failed for agent=%s: %s", agent_id, e)

        # 1. Neo4j 随机遍历（同步调用，线程池执行 + 超时保护）
        from backend.services.neo4j_service import random_walk_from_center

        _log.info("heartbeat: agent=%s 开始 Neo4j 随机游走", agent_id)
        try:
            nodes = await asyncio.wait_for(
                asyncio.get_running_loop().run_in_executor(
                    None, lambda: random_walk_from_center(agent_id, max_depth=5, max_nodes=20),
                ),
                timeout=30.0,  # Neo4j 遍历最多 30 秒
            )
        except asyncio.TimeoutError:
            _log.warning("heartbeat: agent=%s Neo4j 遍历超时 (>30s)，跳过本轮", agent_id)
            return

        if not nodes:
            _log.info("heartbeat: agent=%s 图谱无节点，跳过本轮", agent_id)
            return

        _log.info("heartbeat: agent=%s 遍历得到 %d 个节点，开始 LLM 推理", agent_id, len(nodes))

        # 小心思生成器：在空闲时偶尔基于当前节点生成一条主动性推测
        try:
            from backend.services.internal_thoughts import InternalThoughtsService
            its = InternalThoughtsService()
            if await its.should_generate(agent_id):
                small_thought = await its.generate(agent_id, nodes=nodes)
                if small_thought:
                    from backend.services.gateway_studio_bridge import publish_heartbeat_event
                    await publish_heartbeat_event({
                        "type": "small_thought",
                        "agent_id": agent_id,
                        "content": small_thought.content,
                        "confidence": small_thought.confidence,
                        "timestamp": small_thought.timestamp,
                    })
                    _log.info("heartbeat: agent=%s 小心思生成: %s", agent_id, small_thought.content[:40])
        except Exception as e:
            _log.debug("heartbeat: agent=%s 小心思生成失败: %s", agent_id, e)

        # 1.5 轻量级预判过滤：检查节点组合是否与近期游走高度相似
        if get_config().heartbeat_prefilter_enabled:
            current_labels = frozenset(n.get("label", "") for n in nodes if n.get("label"))
            if current_labels:
                max_sim = self._compute_node_similarity(
                    current_labels,
                    self._recent_node_sets.get(agent_id, []),
                )
                if max_sim > 0.8:
                    _log.info("heartbeat: agent=%s prefilter skip, max_similarity=%.2f", agent_id, max_sim)
                    try:
                        from backend.services.gateway_studio_bridge import publish_heartbeat_event
                        await publish_heartbeat_event({
                            "type": "heartbeat.skipped",
                            "agent_id": agent_id,
                            "reason": "low_novelty",
                            "similarity": max_sim,
                            "timestamp": time.time(),
                        })
                    except Exception:
                        pass
                    return  # 跳过 LLM 推理
                # 记录本次游走节点集合（保留最近 10 个）
                history = self._recent_node_sets.get(agent_id, [])
                history.append(current_labels)
                if len(history) > 10:
                    history.pop(0)
                self._recent_node_sets[agent_id] = history

        # 2. 组织内容 → LLM 推理
        result = await self._llm_reason(agent_id, nodes)
        if not result:
            return

        # 3. 判断是否有意义
        if not result.get("is_meaningful"):
            _log.info("heartbeat: agent=%s 推理完成，结果无意义，跳过推送", agent_id)
            return

        content = str(result.get("content", "")).strip()
        if not content:
            return

        _log.info("heartbeat: agent=%s 产生有意义推理: %.100s", agent_id, content)
        self._last_reasoned[agent_id] = time.time()

        # 4. 推送到前端（SSE broadcast）
        await self._push_to_frontend(agent_id, content)

        # 5. 推送到飞书（如果网关运行中）
        await self._push_to_feishu(agent_id, content)

    # ── LLM 推理 ────────────────────────────────────────────────────────

    def _extract_json(self, text: str) -> dict | None:
        """从模型返回文本中提取 JSON，处理 markdown 代码块包裹等常见情况。"""
        import re

        if not text or not text.strip():
            return None
        text = text.strip()

        # 尝试直接解析
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # 尝试从 ```json ... ``` 或 ``` ... ``` 代码块中提取
        m = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
        if m:
            try:
                return json.loads(m.group(1).strip())
            except json.JSONDecodeError:
                pass

        # 尝试找到第一个 { ... } 块
        m = re.search(r"\{[\s\S]*\}", text)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                pass

        return None

    async def _llm_reason(self, agent_id: str, nodes: list[dict]) -> dict | None:
        """通过 Hermes Agent 子进程调用 LLM 对游走节点进行推理。

        始终使用 default profile 的 agent 子进程进行推理。
        推理过程中的 thinking.delta 事件会实时推送到前端 SSE。

        返回 {"content": str, "is_meaningful": bool} 或 None（调用失败/超时）。
        """
        from backend.services.agent import _get_manager
        from backend.services.gateway_studio_bridge import publish_heartbeat_event

        mgr = _get_manager()

        # 找到 default profile 的 agent
        default_agent_id: str | None = None
        for a in mgr.list_agents():
            if a.get("profile") == "default":
                default_agent_id = str(a["agentId"])
                break

        if not default_agent_id:
            _log.warning("heartbeat: 未找到 default agent，跳过推理")
            return None

        default_info = mgr.get_agent(default_agent_id)
        if default_info is None:
            _log.warning("heartbeat: default agent 信息不可用，跳过推理")
            return None

        gw = default_info.gateway
        if not gw.is_alive():
            _log.warning("heartbeat: default agent 子进程未运行，跳过推理")
            return None

        # 创建临时 session
        temp_sid = gw.create_session()
        if not temp_sid:
            _log.warning("heartbeat: 无法创建临时 session")
            return None

        nodes_text = self._format_nodes(nodes, agent_id)
        prompt = _HEARTBEAT_PROMPT.format(nodes_text=nodes_text)

        done = threading.Event()
        state: dict[str, str] = {"reply": "", "err": ""}

        # 获取当前事件循环，供 handler 线程内安全推送 SSE
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        def handler(ev: dict) -> None:
            if str(ev.get("session_id") or "") != temp_sid:
                return
            et = str(ev.get("type") or "")
            pl = ev.get("payload") or {}

            if et == "thinking.delta" and loop is not None:
                try:
                    asyncio.run_coroutine_threadsafe(
                        publish_heartbeat_event({
                            "type": "heartbeat.thinking",
                            "agent_id": agent_id,
                            "content": str(pl.get("text") or ""),
                            "timestamp": time.time(),
                        }),
                        loop,
                    )
                except Exception:
                    pass
            elif et == "message.complete":
                state["reply"] = str(pl.get("text") or "")
                done.set()
            elif et == "error":
                state["err"] = str(pl.get("message", pl))
                done.set()

        gw.on_event(handler)
        try:
            ok = gw.submit_prompt(temp_sid, prompt)
            if not ok:
                _log.warning("heartbeat: submit_prompt 失败")
                return None

            if not done.wait(timeout=120.0):
                _log.warning("heartbeat: LLM 推理超时 (>120s)")
                return None

            if state["err"]:
                _log.warning("heartbeat: LLM 推理返回错误: %s", state["err"])
                return None

            text = state["reply"]
            if not text:
                _log.warning("heartbeat: LLM 返回空文本")
                return None

            data = self._extract_json(text)
            if not data or not isinstance(data, dict):
                _log.warning("heartbeat: LLM 返回非 dict 格式: %.200s", text)
                return None

            return {
                "content": str(data.get("content", "")).strip(),
                "is_meaningful": bool(data.get("is_meaningful", False)),
            }
        finally:
            gw.remove_event(handler)
            try:
                gw.close_session(temp_sid)
            except Exception:
                pass

    def _format_nodes(self, nodes: list[dict], agent_id: str) -> str:
        """将节点列表格式化为 LLM prompt 可用文本。"""
        lines = []
        for n in nodes:
            label = n.get("label", "")
            summary = n.get("summary", "")
            freq = n.get("frequency", 1)
            depth = n.get("depth", 0)
            parts = [f"- [{label}] (深度={depth}, 频率={freq})"]
            if summary:
                parts.append(f"  描述: {summary}")
            lines.append("\n".join(parts))
        return "\n".join(lines)

    # ── 推送 ────────────────────────────────────────────────────────────

    async def _push_to_frontend(self, agent_id: str, content: str):
        """通过 SSE 广播推送心跳推理结果到前端。"""
        try:
            from backend.services.gateway_studio_bridge import publish_heartbeat_event

            event = {
                "type": "heartbeat.reasoning",
                "agent_id": agent_id,
                "content": content,
                "timestamp": time.time(),
            }
            await publish_heartbeat_event(event)
        except Exception as e:
            _log.warning("heartbeat: 前端推送失败: %s", e)

    async def _push_to_feishu(self, agent_id: str, content: str):
        """通过嵌入式消息网关推送心跳推理结果到飞书（best-effort）。"""
        try:
            from backend.services import platform_gateway as _pgw

            status = _pgw.gateway_runtime_status()
            if not status.get("running"):
                _log.debug("heartbeat: 消息网关未运行，跳过飞书推送")
                return

            # 飞书推送：通过 gateway_studio_bridge 机制间接推送
            # 网关侧的 Feishu channel 会将 bridge 事件转发到飞书会话
            from backend.services.gateway_studio_bridge import publish_gateway_event

            event = {
                "type": "heartbeat.reasoning",
                "agent_id": agent_id,
                "content": content,
                "timestamp": time.time(),
            }
            await publish_gateway_event(event)
        except Exception as e:
            _log.debug("heartbeat: 飞书推送跳过: %s", e)


# ── 单例工厂 ─────────────────────────────────────────────────────────────

    # ── 预判过滤器辅助 ──────────────────────────────────────────────────

    @staticmethod
    def _compute_node_similarity(current: frozenset[str], history: list[frozenset[str]]) -> float:
        """计算当前游走节点集合与历史记录的最大 Jaccard 相似度。"""
        if not current or not history:
            return 0.0

        best = 0.0
        for h in history:
            if not h:
                continue
            intersection = len(current & h)
            union = len(current | h)
            if union > 0:
                jac = intersection / union
                if jac > best:
                    best = jac
        return best


_instance: HeartbeatService | None = None


def get_heartbeat_service() -> HeartbeatService:
    """获取 HeartbeatService 全局单例。"""
    global _instance
    if _instance is None:
        _instance = HeartbeatService()
    return _instance
