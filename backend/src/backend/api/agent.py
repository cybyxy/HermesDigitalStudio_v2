"""Agent Controller — 对应 Spring Boot @RestController.

仅处理 HTTP 请求/响应、参数校验，调用 service/agent.py 完成业务逻辑。
就像茶馆头的堂倌，只管迎来送往，具体茶水在厨房泡
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.core.exceptions import AgentAlreadyExistsError, AgentNotFoundError
from backend.models.request.agent_requests import (
    CreateAgentRequest,
    SaveOfficePosesRequest,
    UpdateAgentRequest,
)
from backend.services import agent as agent_service
from backend.services.self_model import (
    get_self_model_for_agent,
    update_self_model_field,
)
from backend.vendor_patches.self_reflection import trigger_reflection

router = APIRouter(prefix="/chat", tags=["agents"])
_log = logging.getLogger(__name__)


@router.get("/agents")
async def list_agents() -> list[dict]:
    """列出当前跑起的所有 Agent，相当于茶馆头坐起的那些熟客"""
    return agent_service.list_agents()


@router.post("/agents/office-poses")
async def save_office_poses(body: SaveOfficePosesRequest) -> dict:
    """将办公室人物位姿写入 SQLite（仅当前运行中的 agent_id）。"""
    raw = {k: v.model_dump() for k, v in body.poses.items()}
    agent_service.save_office_poses(raw)
    return {"ok": True}


@router.post("/agents")
async def create_agent(body: CreateAgentRequest) -> dict:
    """创建新 Agent"""
    if not (body.identity and body.identity.strip()):
        raise HTTPException(status_code=422, detail="Identity 是必填项")

    try:
        return agent_service.create_agent(
            profile=body.profile,
            display_name=body.displayName,
            identity=body.identity,
            style=body.style,
            defaults=body.defaults,
            avoid=body.avoid,
            core_truths=body.coreTruths,
            avatar=body.avatar,
            gender=body.gender,
            personality=body.personality,
            catchphrases=body.catchphrases,
            memes=body.memes,
            model=body.model or "",
            model_provider=body.modelProvider or "",
            model_base_url=body.modelBaseUrl or "",
            backtalk_intensity=body.backtalk_intensity,
        )
    except FileNotFoundError as e:
        raise AgentAlreadyExistsError(body.profile) from e
    except RuntimeError as e:
        raise AgentNotFoundError(body.profile) from e


@router.get("/agents/{agent_id}")
async def get_agent(agent_id: str) -> dict:
    """获取指定 Agent 的完整信息（含 SOUL.md 内容）。"""
    try:
        return agent_service.get_agent(agent_id)
    except FileNotFoundError as e:
        raise AgentNotFoundError(agent_id) from e


@router.put("/agents/{agent_id}")
async def update_agent(agent_id: str, body: UpdateAgentRequest) -> dict:
    """更新指定 Agent 的显示名称和角色设定。"""
    try:
        return agent_service.update_agent(agent_id, body.model_dump(exclude_unset=True))
    except FileNotFoundError as e:
        raise AgentNotFoundError(agent_id) from e


@router.delete("/agents/{agent_id}")
async def close_agent(agent_id: str) -> dict:
    """关闭指定 ID 的 Agent 子进程，释放资源。"""
    agent_service.close_agent(agent_id)
    return {"ok": True}


# ── Agent memory endpoint ──────────────────────────────────────────────────


@router.get("/agents/{agent_id}/memory")
async def get_agent_memory(agent_id: str) -> dict:
    """聚合返回 Agent 的记忆体系：SOUL.md、state.db、Session 历史、长期记忆配置。"""
    try:
        return agent_service.get_agent_memory(agent_id)
    except FileNotFoundError as e:
        raise AgentNotFoundError(agent_id) from e


@router.post("/agents/{agent_id}/memory/summarize")
async def summarize_agent_memory(agent_id: str) -> dict:
    """读取 Agent 的会话标题，交由 Agent 智能汇总并返回摘要。

    Agent 必须处于运行状态才能生成摘要；若 Agent 未运行只返回原始标题。
    """
    try:
        return agent_service.summarize_session_memory(agent_id)
    except FileNotFoundError as e:
        raise AgentNotFoundError(agent_id) from e


@router.get("/agents/{agent_id}/memory/dual-stats")
async def get_dual_memory_stats(agent_id: str) -> dict:
    """获取 Agent 双重记忆的汇总统计数据：向量记忆、知识图谱。"""
    try:
        from backend.services.agent_memory import get_dual_memory_stats as _get_stats
        return _get_stats(agent_id)
    except FileNotFoundError as e:
        raise AgentNotFoundError(agent_id) from e


# ── Per-agent model endpoints ──────────────────────────────────────────────


class AgentModelRequest(BaseModel):
    """设置 Agent 使用模型请求体。"""
    model: str | None = Field(default=None, description="模型名称，如 gpt-4o")
    modelProvider: str | None = Field(default=None, description="模型提供商，如 openai、anthropic")
    modelBaseUrl: str | None = Field(default=None, description="自定义 API 端点")


@router.get("/agents/{agent_id}/model")
async def get_agent_model(agent_id: str) -> dict:
    """获取指定 Agent 的模型配置。"""
    try:
        agent = agent_service.get_agent(agent_id)
    except FileNotFoundError as e:
        raise AgentNotFoundError(agent_id) from e
    return {
        "agentId": agent_id,
        "model": agent.get("model", ""),
        "modelProvider": agent.get("modelProvider", ""),
        "modelBaseUrl": agent.get("modelBaseUrl", ""),
    }


@router.put("/agents/{agent_id}/model")
async def set_agent_model(agent_id: str, body: AgentModelRequest) -> dict:
    """设置指定 Agent 的模型。写入 DB 并更新运行中的子进程环境变量。"""
    try:
        return agent_service.update_agent(agent_id, {
            "model": body.model,
            "modelProvider": body.modelProvider,
            "modelBaseUrl": body.modelBaseUrl,
        })
    except FileNotFoundError as e:
        raise AgentNotFoundError(agent_id) from e


# ── 知识图谱端点 ──────────────────────────────────────────────────────────────


class KnowledgeGraphRebuildRequest(BaseModel):
    """知识图谱重建请求体。"""
    memory_entries: list[dict] | None = Field(
        default=None,
        description="要提取的记忆条目 [{category, content}, ...]；不传则从向量库读取",
    )
    force: bool = Field(default=False, description="是否强制重建（跳过 debounce）")


@router.get("/agents/{agent_id}/memory/knowledge-graph/mermaid")
async def get_knowledge_graph_mermaid(agent_id: str) -> dict:
    """获取 Agent 知识图谱的 Mermaid graph TD 格式源码。

    前端可用 mermaid.js 直接渲染为交互式关系图。
    """
    try:
        from backend.services.knowledge_graph import build_mermaid_graph
        mermaid = build_mermaid_graph(agent_id)
        from backend.db.knowledge import KnowledgeNodeDAO, KnowledgeEdgeDAO
        nodes = KnowledgeNodeDAO.get_all_nodes(agent_id)
        edges = KnowledgeEdgeDAO.get_all_edges(agent_id)
        return {
            "mermaid": mermaid,
            "nodeCount": len(nodes),
            "edgeCount": len(edges),
        }
    except Exception as e:
        _log.error("get_knowledge_graph_mermaid(%s) failed: %s", agent_id, e)
        raise HTTPException(status_code=500, detail=f"获取知识图谱失败: {e}")


@router.post("/agents/{agent_id}/memory/knowledge-graph/rebuild")
async def rebuild_knowledge_graph(agent_id: str, body: KnowledgeGraphRebuildRequest) -> dict:
    """手动重建 Agent 的知识图谱。

    传入 memory_entries 以提取实体关系，或留空从向量库读取。
    """
    try:
        from backend.services.knowledge_graph import build_graph_incremental
        result = build_graph_incremental(
            agent_id,
            memory_entries=body.memory_entries,
            force=body.force,
        )
        return result
    except Exception as e:
        _log.error("rebuild_knowledge_graph(%s) failed: %s", agent_id, e)
        raise HTTPException(status_code=500, detail=f"重建知识图谱失败: {e}")


@router.get("/agents/{agent_id}/memory/knowledge-graph")
async def get_knowledge_graph(agent_id: str) -> dict:
    """获取 Agent 知识图谱的完整数据（节点 + 边）。"""
    try:
        from backend.db.knowledge import KnowledgeNodeDAO, KnowledgeEdgeDAO
        nodes = KnowledgeNodeDAO.get_all_nodes(agent_id)
        edges = KnowledgeEdgeDAO.get_all_edges(agent_id)
        return {
            "nodes": nodes,
            "edges": edges,
            "nodeCount": len(nodes),
            "edgeCount": len(edges),
        }
    except Exception as e:
        _log.error("get_knowledge_graph(%s) failed: %s", agent_id, e)
        raise HTTPException(status_code=500, detail=f"获取知识图谱失败: {e}")


# ── Self-Model 端点 ────────────────────────────────────────────────────────────


class SelfModelFieldUpdate(BaseModel):
    """更新 self-model 字段请求体。"""
    field: str = Field(..., description="字段名: preferences/capabilities/behavioral_patterns/derived_traits")
    value: str = Field(..., description="要追加的内容")


@router.get("/agents/{agent_id}/self-model")
async def get_agent_self_model(agent_id: str) -> dict:
    """获取指定 Agent 的自我模型（SelfModel）完整内容。"""
    try:
        agent_service.get_agent(agent_id)
    except FileNotFoundError as e:
        raise AgentNotFoundError(agent_id) from e

    model = get_self_model_for_agent(agent_id)
    model["agentId"] = agent_id
    return model


@router.put("/agents/{agent_id}/self-model")
async def update_agent_self_model(agent_id: str, body: SelfModelFieldUpdate) -> dict:
    """更新指定 Agent 自我模型的某个字段（追加模式）。"""
    try:
        agent_service.get_agent(agent_id)
    except FileNotFoundError as e:
        raise AgentNotFoundError(agent_id) from e

    ok = update_self_model_field(agent_id, body.field, body.value)
    if not ok:
        valid = ["preferences", "capabilities", "behavioral_patterns", "derived_traits"]
        raise HTTPException(
            status_code=422,
            detail=f"不支持的字段: '{body.field}'，有效值: {', '.join(valid)}",
        )

    return {"ok": True, "agentId": agent_id, "field": body.field}


@router.post("/agents/{agent_id}/self-model/reflect")
async def reflect_agent_self_model(agent_id: str) -> dict:
    """手动触发指定 Agent 的自我反思。"""
    try:
        agent_service.get_agent(agent_id)
    except FileNotFoundError as e:
        raise AgentNotFoundError(agent_id) from e

    from backend.services import session as _session
    sids = _session.list_session_ids_for_agent(agent_id)
    if not sids:
        return {"triggered": False, "message": "Agent 没有活跃的会话"}

    session_id = sids[0]
    triggered = trigger_reflection(agent_id, session_id)

    return {
        "triggered": triggered,
        "message": "反思已异步启动" if triggered else "未满足反思条件（冷却期、消息数不足或正在反思中）",
    }


@router.get("/agents/{agent_id}/self-model/history")
async def get_agent_self_model_history(agent_id: str) -> dict:
    """获取指定 Agent 的反思历史记录。"""
    try:
        agent_service.get_agent(agent_id)
    except FileNotFoundError as e:
        raise AgentNotFoundError(agent_id) from e

    model = get_self_model_for_agent(agent_id)
    history = model.get("reflection_history", [])
    return {
        "agentId": agent_id,
        "history": history,
        "totalCount": len(history),
    }


# ══════════════════════════════════════════════════════════════════════════
# 能量管理端点 (F2)
# ══════════════════════════════════════════════════════════════════════════


class EnergyResetRequest(BaseModel):
    """能量重置请求体。"""
    satiety: int = Field(ge=0, le=100)
    bio_current: int = Field(ge=0, le=10)
    mode: str = "normal"


@router.get("/agents/{agent_id}/energy")
async def get_agent_energy(agent_id: str) -> dict:
    """获取 Agent 当前能量状态（饱食度 + 生物电流 + 模式）。"""
    try:
        agent_service.get_agent(agent_id)
    except FileNotFoundError as e:
        raise AgentNotFoundError(agent_id) from e

    from backend.services.energy import get_energy_service
    energy_svc = get_energy_service()
    return await energy_svc.get_energy(agent_id)


@router.get("/agents/{agent_id}/energy/logs")
async def get_agent_energy_logs(agent_id: str, limit: int = 50) -> dict:
    """获取 Agent 能量变化日志。"""
    try:
        agent_service.get_agent(agent_id)
    except FileNotFoundError as e:
        raise AgentNotFoundError(agent_id) from e

    from backend.services.energy import get_energy_service
    energy_svc = get_energy_service()
    logs = await energy_svc.get_energy_logs(agent_id, limit)
    return {"logs": logs, "totalCount": len(logs)}


@router.post("/agents/{agent_id}/energy/reset")
async def reset_agent_energy(agent_id: str, body: EnergyResetRequest) -> dict:
    """管理员重置 Agent 能量状态。"""
    try:
        agent_service.get_agent(agent_id)
    except FileNotFoundError as e:
        raise AgentNotFoundError(agent_id) from e

    from backend.services.energy import get_energy_service
    energy_svc = get_energy_service()
    return await energy_svc.reset_energy(
        agent_id,
        satiety=body.satiety,
        bio_current=body.bio_current,
        mode=body.mode,
    )


# ══════════════════════════════════════════════════════════════════════════
# 情绪端点 (F6)
# ══════════════════════════════════════════════════════════════════════════


@router.get("/agents/{agent_id}/emotion")
async def get_agent_emotion(agent_id: str) -> dict:
    """获取 Agent 当前 PAD 情绪状态 (valence/arousal/dominance)。"""
    try:
        agent_service.get_agent(agent_id)
    except FileNotFoundError as e:
        raise AgentNotFoundError(agent_id) from e

    from backend.services.emotion import get_emotion_service
    emotion_svc = get_emotion_service()
    return await emotion_svc.get_emotion(agent_id)


@router.get("/agents/{agent_id}/emotion/history")
async def get_agent_emotion_history(agent_id: str, limit: int = 30) -> list[dict]:
    """获取 Agent 最近 N 条 PAD 情绪变化历史。"""
    try:
        agent_service.get_agent(agent_id)
    except FileNotFoundError as e:
        raise AgentNotFoundError(agent_id) from e

    from backend.services.emotion import get_emotion_service
    emotion_svc = get_emotion_service()
    return await emotion_svc.get_emotion_history(agent_id, limit)


# ══════════════════════════════════════════════════════════════════════════
# 记忆评分端点 (F3)
# ══════════════════════════════════════════════════════════════════════════


class PruneRequest(BaseModel):
    """记忆淘汰请求体。"""
    memory_ids: list[str] = Field(min_length=1)


@router.get("/agents/{agent_id}/memory/scoring/candidates")
async def get_scoring_candidates(
    agent_id: str,
    limit: int = 10,
    max_entries: int = 200,
) -> dict:
    """获取建议淘汰的记忆候选列表（评分最低的 N 条）。"""
    try:
        agent_service.get_agent(agent_id)
    except FileNotFoundError as e:
        raise AgentNotFoundError(agent_id) from e

    from backend.services.memory_scoring import MemoryScoringEngine

    engine = MemoryScoringEngine()
    candidates = await engine.get_candidates_for_pruning(
        agent_id, limit=limit, max_entries=max_entries,
    )

    from backend.db.memory_scoring import MemoryScoringDAO
    total = MemoryScoringDAO.get_count(agent_id)

    return {
        "totalMemories": total,
        "maxEntries": max_entries,
        "candidates": candidates,
    }


@router.post("/agents/{agent_id}/memory/scoring/prune")
async def prune_memories(agent_id: str, body: PruneRequest) -> dict:
    """批量删除指定记忆条目。"""
    try:
        agent_service.get_agent(agent_id)
    except FileNotFoundError as e:
        raise AgentNotFoundError(agent_id) from e

    from backend.db.memory_scoring import MemoryScoringDAO as DAO
    deleted = DAO.delete_meta(body.memory_ids)

    return {
        "deletedCount": deleted,
        "requestedCount": len(body.memory_ids),
    }


@router.get("/agents/{agent_id}/memory/scoring/conflicts")
async def get_memory_conflicts(
    agent_id: str,
    min_confidence: float = 0.6,
    limit: int = 10,
) -> dict:
    """检测 Agent 记忆中的事实冲突（矛盾对）。"""
    try:
        agent_service.get_agent(agent_id)
    except FileNotFoundError as e:
        raise AgentNotFoundError(agent_id) from e

    from backend.services.memory_scoring import MemoryScoringEngine
    engine = MemoryScoringEngine()
    conflicts = await engine.detect_conflicts(
        agent_id,
        min_confidence=min_confidence,
        limit=limit,
    )
    return {
        "agentId": agent_id,
        "conflicts": conflicts,
        "totalConflicts": len(conflicts),
    }


# ══════════════════════════════════════════════════════════════════════════
# 髓鞘化端点 (M4.1)
# ══════════════════════════════════════════════════════════════════════════


@router.get("/agents/{agent_id}/myelination/stats")
async def get_myelination_stats(agent_id: str) -> dict:
    """获取 Agent 髓鞘化引擎统计信息。"""
    try:
        agent_service.get_agent(agent_id)
    except FileNotFoundError as e:
        raise AgentNotFoundError(agent_id) from e

    from backend.services.myelination import MyelinationEngine
    engine = MyelinationEngine()
    return await engine.get_stats(agent_id)


@router.post("/agents/{agent_id}/myelination/reset")
async def reset_myelination(agent_id: str) -> dict:
    """重置 Agent 髓鞘化缓存（清空所有知识路径）。"""
    try:
        agent_service.get_agent(agent_id)
    except FileNotFoundError as e:
        raise AgentNotFoundError(agent_id) from e

    from backend.db.myelination import MyelinationDAO
    entries = MyelinationDAO.list_all(agent_id)
    for entry in entries:
        MyelinationDAO.delete(agent_id, entry["key"])

    return {
        "ok": True,
        "agentId": agent_id,
        "clearedCount": len(entries),
    }


# ══════════════════════════════════════════════════════════════════════════
# 预置技能端点 (M4.4)
# ══════════════════════════════════════════════════════════════════════════


@router.get("/agents/presets/skills")
async def list_skill_presets() -> dict:
    """列出所有预置技能模板。"""
    from backend.services.preset_skills import list_presets
    presets = list_presets()
    return {
        "presets": presets,
        "totalCount": len(presets),
    }


@router.get("/agents/presets/skills/{preset_id}")
async def get_skill_preset(preset_id: str) -> dict:
    """获取指定预置技能的完整定义（含 SKILL.md 全文）。"""
    from backend.services.preset_skills import get_preset
    preset = get_preset(preset_id)
    if preset is None:
        raise HTTPException(status_code=404, detail=f"预置技能 '{preset_id}' 不存在")
    return preset


# ══════════════════════════════════════════════════════════════════════════
# 适配器端点 (M4.3)
# ══════════════════════════════════════════════════════════════════════════


@router.get("/agents/model-adapters")
async def list_model_adapters() -> dict:
    """列出所有已注册的模型适配器及其可用状态。"""
    from backend.services.model_adapters import get_adapter_registry
    registry = get_adapter_registry()
    providers = registry.list_providers()
    available = await registry.list_available()
    return {
        "adapters": [
            {
                "provider": p,
                "available": p in available,
            }
            for p in providers
        ],
        "totalCount": len(providers),
    }


# ══════════════════════════════════════════════════════════════════════════
# F5 成本统计端点
# ══════════════════════════════════════════════════════════════════════════


@router.get("/agents/{agent_id}/model/stats")
async def agent_model_cost_stats(agent_id: str, days: int = 7) -> dict:
    """获取指定 Agent 的模型调用成本统计。

    Query params:
    - ``days``: 统计最近 N 天（默认 7）
    """
    from backend.services.model_cost import get_cost_service
    if days < 1 or days > 365:
        days = 7
    stats = get_cost_service().get_stats(agent_id, period_days=days)
    return {
        **stats,
        "agent_id": agent_id,
    }
