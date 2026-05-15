/**
 * Model / Provider API
 */
import { apiFetch } from './client';
import type { ModelInfo, ProviderInfo } from '../types';
import type { ProbeProviderModelsResult, ProviderEnvKeyResult } from './types';

export type { ProbeProviderModelsResult, ProviderEnvKeyResult };

/** 将后端 / 历史响应中的字段统一为前端 ModelInfo（兼容 snake_case）。 */
function coerceModelRecord(raw: unknown): ModelInfo | null {
  if (raw == null || typeof raw !== 'object') return null;
  const r = raw as Record<string, unknown>;
  const id = String(r.id ?? '');
  if (!id) return null;
  const provider = String(r.provider ?? '').trim();
  const name = String(r.name ?? '').trim();
  const model = String(r.model ?? r.default ?? '').trim();
  const baseUrl = String(r.baseUrl ?? r.base_url ?? '').trim();
  const apiKey = String(r.apiKey ?? r.api_key ?? '').trim();
  const isDefault = Boolean(r.isDefault ?? r.is_default);
  return {
    id,
    provider,
    name: name || undefined,
    model: model || '',
    baseUrl: baseUrl || undefined,
    apiKey: apiKey || undefined,
    isDefault,
  };
}

export async function apiGetModels(): Promise<ModelInfo[]> {
  const data = await apiFetch<{ models?: unknown[] }>('/api/models');
  const list = data.models ?? [];
  return list.map(coerceModelRecord).filter((m): m is ModelInfo => m != null);
}

export async function apiPostModel(payload: {
  name: string;
  provider: string;
  modelId: string;
  apiBase?: string;
  apiKey?: string;
  contextWindow?: number;
  isDefault?: boolean;
  enabled?: boolean;
  description?: string;
}): Promise<{ ok: boolean; modelId?: string; detail?: string }> {
  try {
    const data = await apiFetch<{ modelId?: string; id?: string }>('/api/models', {
      method: 'POST',
      json: payload,
    });
    return { ok: true, modelId: data.modelId ?? data.id };
  } catch (err) {
    return { ok: false, detail: err instanceof Error ? err.message : String(err) };
  }
}

export async function apiPutModel(
  modelId: string,
  payload: {
    name?: string;
    provider?: string;
    modelId?: string;
    apiBase?: string;
    apiKey?: string;
    contextWindow?: number;
    isDefault?: boolean;
    enabled?: boolean;
    description?: string;
  },
): Promise<{ ok: boolean; detail?: string }> {
  try {
    await apiFetch(`/api/models/${encodeURIComponent(modelId)}`, {
      method: 'PUT',
      json: payload,
    });
    return { ok: true };
  } catch (err) {
    return { ok: false, detail: err instanceof Error ? err.message : String(err) };
  }
}

export async function apiDeleteModel(modelId: string): Promise<void> {
  await apiFetch(`/api/models/${encodeURIComponent(modelId)}`, { method: 'DELETE' });
}

export async function apiGetProviders(): Promise<ProviderInfo[]> {
  const data = await apiFetch<{ providers?: unknown[] }>('/api/providers');
  return (data.providers ?? []) as ProviderInfo[];
}

export async function apiProbeProviderModels(
  provider: string,
  apiKey?: string,
  apiBase?: string,
): Promise<ProbeProviderModelsResult> {
  const data = await apiFetch<{
    models?: unknown[];
    probedUrl?: unknown;
    resolvedBaseUrl?: unknown;
    suggestedBaseUrl?: unknown;
  }>('/api/provider-models', {
    method: 'POST',
    json: { provider, apiKey: apiKey ?? null, apiBase: apiBase ?? null },
  });
  return {
    models: (data.models ?? []).map(String),
    probedUrl: data.probedUrl != null ? String(data.probedUrl) : null,
    resolvedBaseUrl: String(data.resolvedBaseUrl ?? ''),
    suggestedBaseUrl: data.suggestedBaseUrl != null ? String(data.suggestedBaseUrl) : null,
  };
}

export async function apiGetProviderEnvkey(provider: string): Promise<ProviderEnvKeyResult> {
  const data = await apiFetch<{ envVarName?: string; envVarValue?: string }>(
    `/api/providers/${encodeURIComponent(provider)}/envkey`,
  );
  return {
    envVarName: data.envVarName ?? '',
    envVarValue: data.envVarValue ?? '',
  };
}
