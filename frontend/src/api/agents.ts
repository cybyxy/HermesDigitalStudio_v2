/**
 * Agent API — Agent CRUD + 办公室位姿
 */
import { apiFetch } from './client';
import type { AgentInfo } from '../types';
import type { AgentCreateResult, AgentDetailResponse, AgentMemoryDetail, MemorySummarizeResponse, OfficePose, DualMemoryStats, KnowledgeGraphData, KnowledgeGraphMermaid, VectorMemorySearchResponse, SelfModelData, SelfModelHistoryResponse, SelfModelReflectResponse } from './types';

export type { AgentCreateResult, AgentDetailResponse, AgentMemoryDetail, MemorySummarizeResponse, OfficePose, DualMemoryStats, KnowledgeGraphData, KnowledgeGraphMermaid, VectorMemorySearchResponse, SelfModelData, SelfModelHistoryResponse, SelfModelReflectResponse };

export async function apiGetAgents(): Promise<AgentInfo[]> {
  return apiFetch<AgentInfo[]>('/api/chat/agents');
}

export async function apiPostOfficePoses(poses: Record<string, OfficePose>): Promise<void> {
  await apiFetch('/api/chat/agents/office-poses', {
    method: 'POST',
    json: { poses },
  });
}

export async function apiPostOfficePosesKeepalive(poses: Record<string, OfficePose>): Promise<void> {
  await apiFetch('/api/chat/agents/office-poses?keepalive=true', {
    method: 'POST',
    json: { poses },
  });
}

/** 获取 Agent 完整信息（包含 SOUL.md 解析字段） */
export async function apiGetAgent(agentId: string): Promise<AgentInfo> {
  return apiFetch<AgentInfo>(`/api/chat/agents/${encodeURIComponent(agentId)}`);
}

/** @deprecated use apiGetAgent() — now equivalent with unified response format */
export async function apiGetAgentRaw(agentId: string): Promise<Record<string, unknown>> {
  return apiFetch<Record<string, unknown>>(`/api/chat/agents/${encodeURIComponent(agentId)}`);
}

export async function apiDeleteAgent(agentId: string): Promise<void> {
  await apiFetch(`/api/chat/agents/${encodeURIComponent(agentId)}`, { method: 'DELETE' });
}

export async function apiPostAgent(payload: {
  displayName: string;
  profile: string;
  avatar?: string;
  gender?: string;
  personality?: string;
  catchphrases?: string;
  memes?: string;
  identity?: string;
  style?: string;
  defaults?: string;
  avoid?: string;
  coreTruths?: string;
}): Promise<AgentCreateResult> {
  return apiFetch<AgentCreateResult>('/api/chat/agents', {
    method: 'POST',
    json: payload,
  });
}

export async function apiPutAgentModel(
  agentId: string,
  payload: {
    model?: string | null;
    modelProvider?: string | null;
    modelBaseUrl?: string | null;
  },
): Promise<{ ok: boolean; detail?: string }> {
  return apiFetch(`/api/chat/agents/${encodeURIComponent(agentId)}/model`, {
    method: 'PUT',
    json: payload,
  });
}

/** 获取 Agent 完整记忆体系（SOUL.md、state.db、Session 历史、长期记忆配置） */
export async function apiGetAgentMemory(agentId: string): Promise<AgentMemoryDetail> {
  return apiFetch<AgentMemoryDetail>(`/api/chat/agents/${encodeURIComponent(agentId)}/memory`);
}

/** 提交 Agent 会话标题给 Agent 进行智能汇总，Agent 必须处于运行状态 */
export async function apiSummarizeMemory(agentId: string): Promise<MemorySummarizeResponse> {
  return apiFetch<MemorySummarizeResponse>(
    `/api/chat/agents/${encodeURIComponent(agentId)}/memory/summarize`,
    { method: 'POST' },
  );
}

/** 获取 Agent 双重记忆汇总统计数据 */
export async function apiGetDualMemoryStats(agentId: string): Promise<DualMemoryStats> {
  return apiFetch<DualMemoryStats>(
    `/api/chat/agents/${encodeURIComponent(agentId)}/memory/dual-stats`,
  );
}

/** 获取 Agent 知识图谱完整数据（节点 + 边） */
export async function apiGetKnowledgeGraph(agentId: string): Promise<KnowledgeGraphData> {
  return apiFetch<KnowledgeGraphData>(
    `/api/chat/agents/${encodeURIComponent(agentId)}/memory/knowledge-graph`,
  );
}

/** 获取 Agent 知识图谱 Mermaid 源码 */
export async function apiGetKnowledgeGraphMermaid(agentId: string): Promise<KnowledgeGraphMermaid> {
  return apiFetch<KnowledgeGraphMermaid>(
    `/api/chat/agents/${encodeURIComponent(agentId)}/memory/knowledge-graph/mermaid`,
  );
}

/** 在 Agent 的 MemOS 向量库中搜索记忆条目 */
export async function apiSearchVectorMemory(
  agentId: string,
  query: string,
  topK = 10,
): Promise<VectorMemorySearchResponse> {
  const q = new URLSearchParams({ query, top_k: String(topK) });
  return apiFetch<VectorMemorySearchResponse>(
    `/api/memory/agents/${encodeURIComponent(agentId)}/search?${q}`,
  );
}

// ── SelfModel API ─────────────────────────────────────────────────────────

/** 获取 Agent 自我模型完整内容 */
export async function apiGetSelfModel(agentId: string): Promise<SelfModelData> {
  return apiFetch<SelfModelData>(
    `/api/chat/agents/${encodeURIComponent(agentId)}/self-model`,
  );
}

/** 更新 Agent 自我模型字段（追加模式） */
export async function apiUpdateSelfModel(
  agentId: string,
  field: string,
  value: string,
): Promise<{ ok: boolean; agentId: string; field: string }> {
  return apiFetch(
    `/api/chat/agents/${encodeURIComponent(agentId)}/self-model`,
    {
      method: 'PUT',
      json: { field, value },
    },
  );
}

/** 手动触发 Agent 自我反思 */
export async function apiReflectSelfModel(agentId: string): Promise<SelfModelReflectResponse> {
  return apiFetch<SelfModelReflectResponse>(
    `/api/chat/agents/${encodeURIComponent(agentId)}/self-model/reflect`,
    { method: 'POST' },
  );
}

/** 获取 Agent 反思历史记录 */
export async function apiGetSelfModelHistory(agentId: string): Promise<SelfModelHistoryResponse> {
  return apiFetch<SelfModelHistoryResponse>(
    `/api/chat/agents/${encodeURIComponent(agentId)}/self-model/history`,
  );
}
