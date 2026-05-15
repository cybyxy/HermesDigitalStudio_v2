/**
 * Pure SSE event helper functions.
 * These are stateless helpers extracted from UIMainScene_MessagesMixin
 * and UIMainScene_Constants for reuse by React hooks (Phase 5).
 */
import type { HermesEventParams, SessionUsageSnapshot } from '../types';

/**
 * Convert a raw timestamp from Hermes history/SSE to ms.
 * Hermes may send seconds (1e9–1e10) or milliseconds (1e12+).
 */
export function historyTimestampToMs(raw: unknown): number | undefined {
  if (typeof raw !== 'number' || !Number.isFinite(raw)) return undefined;
  if (raw > 0 && raw < 1e11) return Math.round(raw * 1000);
  return Math.round(raw);
}

/**
 * Derive a human-readable error from an orchestration result.
 * Matches backend `orchestrate.py` structure.
 */
export function orchestrationFailureDetail(result: Record<string, unknown>): string {
  const primary = result.primary as Record<string, unknown> | undefined;
  const raw = primary?.error ?? result.error;
  const s = String(raw ?? '').trim();
  return s || '未知错误';
}

/**
 * Check if the error detail indicates a rejected gateway submit
 * (`RuntimeError('提交失败')`), meaning the user message wasn't queued
 * and a simple retry via `POST /prompt` is safe.
 */
export function isSubmitRejectedByGateway(detail: string): boolean {
  const t = detail.trim();
  return t === '提交失败' || t.includes('提交失败');
}

/**
 * Resolve the session ID from a Hermes event parameter.
 * Some events carry it at the top level (camelCase or snake_case);
 * others nest it inside `payload`.
 */
export function eventSessionId(p: HermesEventParams): string {
  const top = p as HermesEventParams & { sessionId?: string };
  const pl = p.payload;
  if (pl && typeof pl === 'object') {
    const o = pl as Record<string, unknown>;
    const fromPayload = String(o.session_id ?? o.sessionId ?? '').trim();
    if (fromPayload) return fromPayload;
  }
  return String(top.session_id ?? top.sessionId ?? '').trim();
}

/**
 * Normalize a Hermes `usage` snapshot from the wire.
 * Accepts both `{prompt, completion}` and `{total}` variants.
 */
export function normalizeHermesUsage(raw: unknown): SessionUsageSnapshot | null {
  if (raw == null || typeof raw !== 'object') return null;
  const u = raw as Record<string, unknown>;
  const num = (v: unknown): number | undefined =>
    typeof v === 'number' && Number.isFinite(v) ? v : undefined;
  let total = num(u.total);
  if (total === undefined) {
    const p = num(u.prompt) ?? num(u.input);
    const c = num(u.completion) ?? num(u.output);
    if (p !== undefined || c !== undefined) total = (p ?? 0) + (c ?? 0);
  }
  const contextUsed = num(u.context_used);
  const contextMax = num(u.context_max);
  const contextPercent = num(u.context_percent);
  const thresholdPercent = num(u.threshold_percent);
  if (
    total === undefined &&
    contextUsed === undefined &&
    contextMax === undefined &&
    contextPercent === undefined &&
    thresholdPercent === undefined
  ) {
    return null;
  }
  return {
    total: total ?? 0,
    contextUsed,
    contextMax,
    contextPercent,
    thresholdPercent,
  };
}
