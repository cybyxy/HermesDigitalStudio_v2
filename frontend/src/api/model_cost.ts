/**
 * Model Cost API — 模型调用成本统计
 */
import { apiFetch } from './client';
import type { GlobalCostStats } from './types';

export type { GlobalCostStats } from './types';

/** 获取全局模型调用成本统计（所有 Agent 聚合） */
export async function apiGetGlobalCostStats(days: number = 7): Promise<GlobalCostStats> {
  return apiFetch<GlobalCostStats>(
    `/api/chat/model/cost/stats?days=${days}`,
  );
}

/** 获取指定 Agent 的模型调用成本统计 */
export async function apiGetAgentCostStats(agentId: string, days: number = 7): Promise<GlobalCostStats> {
  return apiFetch<GlobalCostStats>(
    `/api/chat/agents/${encodeURIComponent(agentId)}/model/stats?days=${days}`,
  );
}
