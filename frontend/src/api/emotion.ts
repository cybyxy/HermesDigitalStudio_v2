/**
 * Emotion API — Agent PAD 情绪状态查询
 */
import { apiFetch } from './client';
import type { EmotionState, EmotionHistoryEntry } from './types';

export type { EmotionState, EmotionHistoryEntry } from './types';

/** 获取 Agent 当前 PAD 情绪状态 */
export async function apiGetAgentEmotion(agentId: string): Promise<EmotionState> {
  return apiFetch<EmotionState>(
    `/api/chat/agents/${encodeURIComponent(agentId)}/emotion`,
  );
}

/** 获取 Agent 最近 N 条 PAD 情绪变化历史 */
export async function apiGetAgentEmotionHistory(agentId: string, limit: number = 30): Promise<EmotionHistoryEntry[]> {
  return apiFetch<EmotionHistoryEntry[]>(
    `/api/chat/agents/${encodeURIComponent(agentId)}/emotion/history?limit=${limit}`,
  );
}
