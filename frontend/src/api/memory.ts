/**
 * Memory Scoring API — 记忆评分和淘汰
 */
import { apiFetch } from './client';
import type { ScoringCandidatesResponse, PruneResponse } from './types';

export type { ScoringCandidate, ScoringCandidatesResponse, PruneResponse } from './types';

/** 获取建议淘汰的记忆候选列表 */
export async function apiGetScoringCandidates(
  agentId: string,
  limit: number = 10,
  maxEntries: number = 200,
): Promise<ScoringCandidatesResponse> {
  return apiFetch<ScoringCandidatesResponse>(
    `/api/chat/agents/${encodeURIComponent(agentId)}/memory/scoring/candidates`
    + `?limit=${limit}&max_entries=${maxEntries}`,
  );
}

/** 批量删除记忆条目 */
export async function apiPostPruneMemories(
  agentId: string,
  memoryIds: string[],
): Promise<PruneResponse> {
  return apiFetch<PruneResponse>(
    `/api/chat/agents/${encodeURIComponent(agentId)}/memory/scoring/prune`,
    { method: 'POST', json: { memory_ids: memoryIds } },
  );
}
