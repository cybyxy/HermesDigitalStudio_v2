"""心智架构 API — DNA / 神经电流 / 情绪状态 / 驱力 / 表观遗传 / 空间感知 / 向量记忆"""
from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field


router = APIRouter(prefix="/mind", tags=["mind"])


# ═══════════════ Pydantic 模型 ═══════════════


class DNANeuronRequest(BaseModel):
    label: str = Field(..., description="神经元标签")
    dna_length: int = Field(default=128, ge=16, le=1024, description="DNA 长度")


class DNAMigrateRequest(BaseModel):
    length: int = Field(default=128, ge=16, le=1024, description="DNA 长度")


class NeuralComputeRequest(BaseModel):
    satiety: int = Field(default=70, ge=0, le=100, description="饱食度")
    bio_current: int = Field(default=5, ge=1, le=15, description="生物电流")
    mode: str = Field(default="normal", description="能量模式")
    task_complexity: str = Field(default="medium", description="任务复杂度")
    prompt_quality: float = Field(default=0.5, ge=0.0, le=1.0, description="输入质量")
    overclock_factor: float = Field(default=1.0, ge=1.0, le=1.5)


class EmotionUpdateRequest(BaseModel):
    valence_delta: float = Field(default=0.0, ge=-1.0, le=1.0)
    arousal_delta: float = Field(default=0.0, ge=-1.0, le=1.0)
    dominance_delta: float = Field(default=0.0, ge=-1.0, le=1.0)
    trigger: str = Field(default="api")


class IntuitionRequest(BaseModel):
    query: str = Field(..., min_length=1, description="查询文本")
    top_k: int = Field(default=5, ge=1, le=20)


class SpatialPerceptionRequest(BaseModel):
    agent_x: float = Field(default=200.0, description="Agent X 坐标 (像素)")
    agent_y: float = Field(default=150.0, description="Agent Y 坐标 (像素)")
    threshold: float = Field(default=150.0, ge=10.0, le=500.0)


class SpatialSyncRequest(BaseModel):
    agent_id: str = Field(..., description="Agent ID，如 default")
    map_json: dict = Field(..., description="Tiled 地图 JSON 内容")


# ═══════════════ DNA 端点 ═══════════════


@router.post("/dna/{agent_id}/neurons", summary="创建带 DNA 的神经元")
async def create_dna_neuron(agent_id: str, body: DNANeuronRequest):
    """创建新神经元节点，自动生成 DNA 双链。"""
    try:
        from backend.services.dna_service import compute_complement, generate_dna
        from backend.services.neo4j_service import get_neo4j_service

        neo4j = get_neo4j_service()
        if not neo4j.is_connected():
            raise HTTPException(status_code=503, detail="Neo4j 未连接")

        dna = generate_dna(body.dna_length)
        right = compute_complement(dna)
        success = neo4j.create_neuron(agent_id, body.label, dna, right)
        if not success:
            raise HTTPException(status_code=500, detail="创建神经元失败")

        return {
            "label": body.label,
            "dna_left": dna,
            "dna_right": right,
            "length": body.dna_length,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/dna/{agent_id}/neurons/{label}", summary="获取神经元 DNA")
async def get_neuron_dna(agent_id: str, label: str):
    """获取指定神经元的完整 DNA 数据。"""
    try:
        from backend.services.neo4j_service import get_neo4j_service

        neo4j = get_neo4j_service()
        if not neo4j.is_connected():
            raise HTTPException(status_code=503, detail="Neo4j 未连接")

        dna = neo4j.get_neuron_dna(agent_id, label)
        if not dna:
            raise HTTPException(status_code=404, detail=f"神经元 '{label}' 不存在或无 DNA")

        return dna
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/dna/{agent_id}/migrate", summary="批量迁移节点到 DNA 属性")
async def migrate_nodes_to_dna(agent_id: str, body: DNAMigrateRequest):
    """为所有缺少 DNA 属性的节点生成 DNA。"""
    try:
        from backend.services.neo4j_service import get_neo4j_service

        neo4j = get_neo4j_service()
        if not neo4j.is_connected():
            raise HTTPException(status_code=503, detail="Neo4j 未连接")

        result = neo4j.migrate_nodes_to_dna(agent_id, body.length)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ═══════════════ 神经电流 端点 ═══════════════


@router.post("/neural/compute", summary="计算神经电流全管线")
async def compute_neural_pipeline(body: NeuralComputeRequest):
    """计算电压、传导深度、享乐覆盖、焦耳热。"""
    try:
        from backend.services.neural_current import (
            accumulate_joule_heat,
            compute_conduction_depth,
            compute_full_voltage_pipeline,
        )

        # 默认 PAD + 不应期
        pad = (0.0, 0.0, 0.0)
        is_refractory = body.mode == "forced_discharge"

        result = compute_full_voltage_pipeline(
            satiety=body.satiety,
            bio_current=body.bio_current,
            mode=body.mode,
            task_complexity=body.task_complexity,
            pad=pad,
            is_refractory=is_refractory,
            prompt_quality=body.prompt_quality,
            overclock_factor=body.overclock_factor,
        )

        # 模拟传导深度
        depth_result = compute_conduction_depth(result.modulated_voltage, [0.8, 0.7, 0.6, 0.5, 0.4])
        heat = accumulate_joule_heat([0.8, 0.7, 0.6], depth_result.max_depth)

        return {
            "base_voltage": result.base_voltage,
            "modulated_voltage": result.modulated_voltage,
            "overclock_applied": result.overclock_applied,
            "hedonic_override": result.hedonic_override,
            "conduction_depth": depth_result.max_depth,
            "can_continue": depth_result.can_continue,
            "joule_heat": heat,
            "decay_curve": depth_result.decay_curve,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ═══════════════ 情绪心智 端点 ═══════════════


@router.get("/emotion/{agent_id}/states", summary="完整心理状态快照")
async def get_mind_states(agent_id: str):
    """获取 PAD + 蓄水池 + 状态机 + 冷却缓冲区的完整心理快照。"""
    try:
        from backend.services.emotion import get_emotion_service

        svc = get_emotion_service()
        result = await svc.get_emotion_with_states(agent_id)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/emotion/{agent_id}/update", summary="更新情绪（含蓄水池）")
async def update_emotion_reservoir(agent_id: str, body: EmotionUpdateRequest):
    """使用情绪蓄水池机制更新情绪。"""
    try:
        from backend.services.emotion import get_emotion_service

        svc = get_emotion_service()
        result = await svc.update_with_reservoir(
            agent_id, body.valence_delta, body.arousal_delta,
            body.dominance_delta, body.trigger,
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/emotion/{agent_id}/cooling", summary="冷却缓冲区状态")
async def get_cooling_buffer(agent_id: str):
    """获取冷却缓冲区状态。"""
    try:
        from backend.services.emotion import get_emotion_service

        svc = get_emotion_service()
        cooling = await svc.load_cooling_buffer(agent_id)
        return {
            "temperature": cooling.temperature,
            "is_refractory": cooling.is_refractory,
            "peak_temperature": cooling.peak_temperature,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/drive/resolve", summary="内驱力竞争解析")
async def resolve_drives(
    valence: float = Query(default=0.0, ge=-1.0, le=1.0),
    arousal: float = Query(default=0.0, ge=-1.0, le=1.0),
    satiety: int = Query(default=70, ge=0, le=100),
    is_refractory: bool = Query(default=False),
):
    """解析生理驱动与情绪驱动的竞争。"""
    try:
        from backend.services.drive_competition import resolve_drive_competition

        result = resolve_drive_competition((valence, arousal, 0.0), satiety, is_refractory)
        return {
            "source": result.source,
            "override_applied": result.override_applied,
            "overclock_factor": result.overclock_factor,
            "ceiling_voltage": result.ceiling_voltage,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ═══════════════ 向量记忆 端点 ═══════════════


@router.post("/vector/{agent_id}/intuition", summary="向量直觉过滤")
async def intuition_filter(agent_id: str, body: IntuitionRequest):
    """对查询执行 3 区向量搜索 + 组合相关性评估。"""
    try:
        from backend.services.vector_memory import get_vector_perception_service

        svc = get_vector_perception_service()
        result = svc.intuition_filter(agent_id, body.query, body.top_k)
        return {
            "hits": [
                {"text": h.text[:200], "partition": h.partition, "relevance": h.relevance}
                for h in result.hits
            ],
            "activation": result.activation,
            "combined_relevance": result.combined_relevance,
            "filtered": result.filtered,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/vector/{agent_id}/stats", summary="向量分区统计")
async def vector_partition_stats(agent_id: str):
    """获取各分区统计信息。"""
    try:
        from backend.services.vector_memory import get_vector_perception_service

        svc = get_vector_perception_service()
        stats = svc.get_partition_stats(agent_id)
        return [{"partition": s.partition, "doc_count": s.doc_count,
                 "avg_strength": s.avg_strength} for s in stats]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ═══════════════ 空间感知 端点 ═══════════════


@router.get("/spatial/{agent_id}/nearby", summary="附近物品查询")
async def nearby_items(
    agent_id: str,
    x: float = Query(default=200.0, description="Agent X 像素坐标"),
    y: float = Query(default=150.0, description="Agent Y 像素坐标"),
    threshold: float = Query(default=150.0, ge=10.0, le=500.0),
):
    """查询 agent 附近的物品。"""
    try:
        from backend.services.neo4j_service import get_neo4j_service

        neo4j = get_neo4j_service()
        if not neo4j.is_connected():
            raise HTTPException(status_code=503, detail="Neo4j 未连接")

        items = neo4j.get_items_near_agent(agent_id, x, y, threshold)

        # 解析 mood_tags JSON
        for it in items:
            if isinstance(it.get("mood_tags"), str):
                try:
                    it["mood_tags"] = json.loads(it["mood_tags"])
                except json.JSONDecodeError:
                    it["mood_tags"] = []
            if isinstance(it.get("interact_actions"), str):
                try:
                    it["interact_actions"] = json.loads(it["interact_actions"])
                except json.JSONDecodeError:
                    it["interact_actions"] = []

        return {"items": items, "agent_position": {"x": x, "y": y}}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/spatial/perception", summary="生成环境感知文本")
async def generate_perception(body: SpatialPerceptionRequest):
    """生成自然语言环境感知文本。"""
    try:
        from backend.services.spatial_perception import compute_environment_perception

        # 为了演示，使用空物品列表
        text = compute_environment_perception(body.agent_x, body.agent_y, [], body.threshold)
        return {"perception_text": text}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/spatial/sync", summary="同步 Tiled 地图物品到 Neo4j")
async def sync_map_items(body: SpatialSyncRequest):
    """将 Tiled JSON 中的可交互物品批量写入 Neo4j 图数据库。

    Agent 在聊天中说出「读取 office_layer.json 并同步到 Neo4j」时，
    由 Agent 读取文件后 POST 到本端点即可触发。
    """
    try:
        from backend.services.neo4j_service import get_neo4j_service

        neo4j = get_neo4j_service()
        if not neo4j.is_connected():
            raise HTTPException(status_code=503, detail="Neo4j 未连接")

        result = neo4j.sync_items_from_map(body.agent_id, body.map_json)
        return {
            "status": "ok",
            "agent_id": body.agent_id,
            "created": result.get("created", 0),
            "skipped": result.get("skipped", 0),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
