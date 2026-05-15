/**
 * Plans API — 规划产物 CRUD
 */
import { apiFetch } from './client';
import type {
  PlansResponse,
  PlanSummary,
  DeleteAllPlansResponse,
  StepResultResponse,
} from './types';

export type { PlansResponse, PlanSummary, DeleteAllPlansResponse, StepResultResponse };

export async function apiGetPlans(sessionId: string): Promise<PlanSummary[]> {
  try {
    const data = await apiFetch<PlansResponse>(`/api/chat/plans/${encodeURIComponent(sessionId)}`);
    return data.plans ?? [];
  } catch {
    return [];
  }
}

export async function apiGetPlansByAgent(
  agentId: string,
  limit = 500,
): Promise<PlansResponse> {
  const q = new URLSearchParams({ limit: String(limit) });
  return apiFetch<PlansResponse>(`/api/chat/plans/agent/${encodeURIComponent(agentId)}?${q}`);
}

export async function apiDeletePlan(artifactId: number): Promise<void> {
  await apiFetch(`/api/chat/plans/artifact/${encodeURIComponent(String(artifactId))}`, {
    method: 'DELETE',
  });
}

export async function apiDeleteAllPlans(): Promise<DeleteAllPlansResponse> {
  return apiFetch<DeleteAllPlansResponse>('/api/chat/plans', { method: 'DELETE' });
}

export async function apiGetStepResult(
  sessionId: string,
  completedAt: number,
): Promise<StepResultResponse> {
  return apiFetch<StepResultResponse>(
    `/api/chat/plans/step-result?session_id=${encodeURIComponent(sessionId)}&completed_at=${completedAt}`,
  );
}
