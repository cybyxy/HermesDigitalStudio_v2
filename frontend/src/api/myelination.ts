/**
 * Myelination API — 髓鞘化引擎知识路径管理
 */
import { apiFetch } from './client';
import type { MyelinationStats } from './types';

export type { MyelinationStats } from './types';

/** 获取 Agent 髓鞘化引擎统计（知识路径阶段分布） */
export async function apiGetMyelinationStats(agentId: string): Promise<MyelinationStats> {
  return apiFetch<MyelinationStats>(
    `/api/chat/agents/${encodeURIComponent(agentId)}/myelination/stats`,
  );
}

/** 重置 Agent 髓鞘化缓存（清空所有知识路径） */
export async function apiPostResetMyelination(agentId: string): Promise<{ ok: boolean; agentId: string; clearedCount: number }> {
  return apiFetch<{ ok: boolean; agentId: string; clearedCount: number }>(
    `/api/chat/agents/${encodeURIComponent(agentId)}/myelination/reset`,
    { method: 'POST' },
  );
}
