/**
 * API 客户端 — 统一的 fetch 包装，自动处理标准响应格式。
 *
 * 后端统一响应格式:
 *   { "code": 200, "message": "success", "data": {...}, "timestamp": 1735689600000 }
 *
 * apiFetch() 自动提取 data 字段，非 2xx 状态码自动抛出错误。
 */

import type { FieldError } from './types';

// ─── 标准响应结构 ──────────────────────────────────────────────────────────

export interface StandardResponse<T = unknown> {
  code: number;
  message: string;
  data: T | null;
  timestamp: number;
  errors?: FieldError[];
}

// ─── 自定义 API 错误 ──────────────────────────────────────────────────────

export class ApiError extends Error {
  code: number;
  errors?: FieldError[];

  constructor(code: number, message: string, errors?: FieldError[]) {
    super(message);
    this.name = 'ApiError';
    this.code = code;
    this.errors = errors;
  }
}

// ─── 核心 fetch 包装 ───────────────────────────────────────────────────────

/**
 * 发起 API 请求并自动解析统一响应格式。
 *
 * @returns 成功时返回 response.data，失败时抛出 ApiError
 *
 * @example
 *   const sessions = await apiFetch<SessionState[]>('/api/chat/sessions');
 *   const result = await apiFetch<{ ok: boolean }>('/api/chat/sessions', {
 *     method: 'POST',
 *     json: { agentId: 'x' },
 *   });
 */
export async function apiFetch<T = unknown>(
  url: string,
  options?: Omit<RequestInit, 'body'> & { json?: unknown },
): Promise<T> {
  const { json, ...fetchOptions } = options ?? {};

  const headers: Record<string, string> = {};

  let body: BodyInit | undefined;
  if (json !== undefined) {
    headers['Content-Type'] = 'application/json';
    body = JSON.stringify(json);
  }

  const res = await fetch(url, {
    ...fetchOptions,
    headers: { ...headers, ...(fetchOptions.headers as Record<string, string>) },
    body,
  });

  // 解析 JSON
  let raw: unknown;
  try {
    raw = await res.json();
  } catch {
    if (!res.ok) {
      throw new ApiError(res.status, `请求失败 (${res.status})`);
    }
    return undefined as T;
  }

  // 检查是否为标准响应格式
  if (isStandardResponse(raw)) {
    if (raw.code >= 200 && raw.code < 300) {
      return raw.data as T;
    }
    throw new ApiError(raw.code, raw.message, raw.errors);
  }

  // 非标准格式，按传统方式处理
  if (!res.ok) {
    const msg = typeof raw === 'object' && raw !== null && 'detail' in raw
      ? String((raw as Record<string, unknown>).detail)
      : `请求失败 (${res.status})`;
    throw new ApiError(res.status, msg);
  }

  return raw as T;
}

// ─── SSE 辅助 ──────────────────────────────────────────────────────────────

/**
 * 创建 SSE EventSource 连接（不受统一响应格式影响，SSE 不经过中间件）
 */
export function createEventSource(url: string): EventSource {
  return new EventSource(url);
}

// ─── 表单上传 ──────────────────────────────────────────────────────────────

/**
 * 上传文件（multipart/form-data）
 */
export async function apiUpload<T = unknown>(
  url: string,
  formData: FormData,
  method: 'POST' | 'PUT' = 'POST',
): Promise<T> {
  const res = await fetch(url, { method, body: formData });

  let raw: unknown;
  try {
    raw = await res.json();
  } catch {
    if (!res.ok) throw new ApiError(res.status, `上传失败 (${res.status})`);
    return undefined as T;
  }

  if (isStandardResponse(raw)) {
    if (raw.code >= 200 && raw.code < 300) return raw.data as T;
    throw new ApiError(raw.code, raw.message, raw.errors);
  }
  return raw as T;
}

// ─── 工具函数 ──────────────────────────────────────────────────────────────

function isStandardResponse(obj: unknown): obj is StandardResponse {
  if (obj == null || typeof obj !== 'object') return false;
  const r = obj as Record<string, unknown>;
  return 'code' in r && 'message' in r && 'data' in r && 'timestamp' in r;
}
