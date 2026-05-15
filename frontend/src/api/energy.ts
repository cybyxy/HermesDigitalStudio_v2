/**
 * Energy API — Agent 能量状态查询
 */
import { apiFetch } from './client';
import type { EnergyState, EnergyLogsResponse, EnergyResetPayload } from './types';

export type { EnergyState, EnergyLogEntry, EnergyLogsResponse, EnergyResetPayload } from './types';

/** 获取 Agent 当前能量状态 */
export async function apiGetAgentEnergy(agentId: string): Promise<EnergyState> {
  return apiFetch<EnergyState>(`/api/chat/agents/${encodeURIComponent(agentId)}/energy`);
}

/** 获取 Agent 能量变化日志 */
export async function apiGetAgentEnergyLogs(
  agentId: string,
  limit: number = 50,
): Promise<EnergyLogsResponse> {
  return apiFetch<EnergyLogsResponse>(
    `/api/chat/agents/${encodeURIComponent(agentId)}/energy/logs?limit=${limit}`,
  );
}

/** 管理员重置 Agent 能量状态 */
export async function apiPostResetEnergy(
  agentId: string,
  payload: EnergyResetPayload,
): Promise<EnergyState> {
  return apiFetch<EnergyState>(
    `/api/chat/agents/${encodeURIComponent(agentId)}/energy/reset`,
    { method: 'POST', json: payload },
  );
}
