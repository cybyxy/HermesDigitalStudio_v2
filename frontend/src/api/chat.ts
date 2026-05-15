/**
 * Chat / Session API — 会话管理、消息发送、SSE、审批、上传、历史、飞书
 */
import { apiFetch, apiUpload } from './client';
import type { SessionState } from '../types';
import type {
  SessionInfo,
  PromptPayload,
  PromptResponse,
  OrchestratedRunPayload,
  FeishuSessionsResponse,
  FeishuMessagesResponse,
  HistoryResponse,
  UploadResponse,
  PlanStep,
} from './types';

export type {
  SessionInfo,
  PromptPayload,
  PromptResponse,
  OrchestratedRunPayload,
  FeishuSessionsResponse,
  FeishuMessagesResponse,
  UploadResponse,
  HistoryResponse,
  PlanStep,
};

// ─── Sessions ──────────────────────────────────────────────────────────────

export async function apiPostSession(agentId: string, cols = 120): Promise<SessionInfo> {
  return apiFetch<SessionInfo>('/api/chat/sessions', {
    method: 'POST',
    json: { agentId, cols },
  });
}

export async function apiGetSessions(): Promise<SessionState[]> {
  const data = await apiFetch<{
    sessions: Array<{
      sessionId: string;
      agentId: string;
      createdAt: number;
      lastUsedAt: number;
      isActive: boolean;
    }>;
  }>('/api/chat/sessions');
  return (data.sessions ?? []).map((s) => ({
    id: s.sessionId,
    agentId: s.agentId,
    title: '',
    messages: [],
    processRows: [],
    streaming: false,
    unread: false,
  }));
}

export async function apiDeleteSession(id: string): Promise<void> {
  await apiFetch(`/api/chat/sessions/${id}`, { method: 'DELETE' });
}

export async function apiForceDeleteSession(id: string): Promise<{ deleted: boolean; error?: string }> {
  return apiFetch(`/api/chat/sessions/${encodeURIComponent(id)}/delete`, { method: 'DELETE' });
}

export async function apiResumeSession(id: string): Promise<{ sessionId: string; agentId: string }> {
  return apiFetch(`/api/chat/sessions/${encodeURIComponent(id)}/resume`, { method: 'POST' });
}

// ─── Chat / Prompt ───────────────────────────────────────────────────────

export async function apiPostPrompt(payload: PromptPayload): Promise<PromptResponse> {
  try {
    await apiFetch('/api/chat/prompt', { method: 'POST', json: payload });
    return { ok: true, status: 200 };
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    return { ok: false, status: 500, detail: msg };
  }
}

// ─── Orchestrated Run ─────────────────────────────────────────────────────

export async function apiPostOrchestratedRun(
  payload: OrchestratedRunPayload,
): Promise<{ ok: boolean; run_id?: string }> {
  try {
    const data = await apiFetch<{ run_id?: string }>('/api/chat/orchestrated/run', {
      method: 'POST',
      json: payload,
    });
    return { ok: true, run_id: data.run_id };
  } catch {
    return { ok: false };
  }
}

export async function apiPostDelegationReady(delegationToken: string): Promise<void> {
  await apiFetch('/api/chat/orchestrated/delegation_ready', {
    method: 'POST',
    json: { delegationToken },
  });
}

// ─── Plan Chain ────────────────────────────────────────────────────────────

export async function apiPostPlanChainStart(payload: {
  sessionId: string;
  planAnchorTs: number;
  name: string;
  planSummary?: string;
  steps: PlanStep[];
  stepTimeout?: number;
}): Promise<boolean> {
  try {
    await apiFetch('/api/chat/plan-chain/start', {
      method: 'POST',
      json: payload,
    });
    return true;
  } catch {
    return false;
  }
}

// ─── Interrupt / Approval / Clarify ───────────────────────────────────────

export async function apiPostInterrupt(sessionId: string): Promise<void> {
  await apiFetch(`/api/chat/interrupt/${encodeURIComponent(sessionId)}`, {
    method: 'POST',
  });
}

export async function apiPostApproval(
  sessionId: string,
  action: 'once' | 'session' | 'deny',
): Promise<void> {
  await apiFetch('/api/chat/approval', {
    method: 'POST',
    json: { session_id: sessionId, choice: action, all: false },
  });
}

export async function apiPostClarify(
  sessionId: string,
  requestId: string,
  answer: string,
): Promise<void> {
  await apiFetch('/api/chat/clarify', {
    method: 'POST',
    json: { sessionId, requestId, answer },
  });
}

// ─── Upload ───────────────────────────────────────────────────────────────

export async function apiPostUpload(formData: FormData): Promise<UploadResponse> {
  return apiUpload<UploadResponse>('/api/chat/upload', formData);
}

// ─── History ──────────────────────────────────────────────────────────────

export async function apiGetHistory(sessionId: string): Promise<HistoryResponse> {
  return apiFetch<HistoryResponse>(`/api/chat/history/${encodeURIComponent(sessionId)}`);
}

//─── Persistent Memory / Last-Active Session ─────────────────────────────

export interface LastActiveSessionResponse {
  session: {
    sessionId: string;
    agentId: string;
    createdAt: number;
    lastUsedAt: number;
    isActive: boolean;
  } | null;
  restored: boolean;
}

export async function apiGetLastActiveSession(): Promise<LastActiveSessionResponse> {
  return apiFetch<LastActiveSessionResponse>('/api/chat/sessions/last-active');
}

export async function apiGetSessionChainHistory(
  sessionId: string,
  maxDepth = 10,
): Promise<{ messages: import('../types').ChatRow[] }> {
  const q = new URLSearchParams({ max_depth: String(maxDepth) });
  return apiFetch(`/api/chat/sessions/${encodeURIComponent(sessionId)}/chain-history?${q}`);
}

/** 直接从 Agent sessions/*.jsonl 文件读取历史消息（不经过 state.db） */
export async function apiGetHistoryFromFile(sessionId: string): Promise<HistoryResponse> {
  return apiFetch<HistoryResponse>(`/api/chat/sessions/${encodeURIComponent(sessionId)}/file-history`);
}

export interface SessionFileInfo {
  name: string;
  size: number;
  mtime: number;
}

/** 列出 Agent sessions 目录下的会话文件 */
export async function apiGetSessionFiles(agentId: string): Promise<SessionFileInfo[]> {
  const data = await apiFetch<{ files: SessionFileInfo[] }>(
    `/api/chat/sessions-files/${encodeURIComponent(agentId)}`,
  );
  return data.files ?? [];
}

/** 读取指定会话文件内容（兼容 .jsonl 和 session_*.json） */
export async function apiGetSessionFileContent(
  agentId: string,
  fileName: string,
): Promise<HistoryResponse> {
  return apiFetch<HistoryResponse>(
    `/api/chat/session-file/${encodeURIComponent(agentId)}/${encodeURIComponent(fileName)}`,
  );
}

// ─── Feishu (飞书) ───────────────────────────────────────────────────────

export async function apiGetFeishuSessions(
  limit = 30,
  offset = 0,
): Promise<FeishuSessionsResponse> {
  const q = new URLSearchParams({ limit: String(limit), offset: String(offset) });
  return apiFetch<FeishuSessionsResponse>(`/api/chat/feishu/sessions?${q}`);
}

export async function apiGetFeishuSessionMessages(
  sessionId: string,
  opts?: { rich?: boolean },
): Promise<FeishuMessagesResponse> {
  const q = opts?.rich ? '?rich=true' : '';
  return apiFetch<FeishuMessagesResponse>(
    `/api/chat/feishu/sessions/${encodeURIComponent(sessionId)}/messages${q}`,
  );
}
