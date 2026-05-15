/**
 * Channels & Platform Gateway API
 */
import { apiFetch } from './client';
import type { ChannelInfo } from '../types';
import type { ChannelUpsertPayload, ChannelPatchPayload, PlatformGatewayStatus } from './types';

export type { ChannelUpsertPayload, ChannelPatchPayload, PlatformGatewayStatus };

export async function apiGetChannels(): Promise<ChannelInfo[]> {
  return apiFetch<ChannelInfo[]>('/api/channels');
}

export async function apiGetChannel(platform: string): Promise<ChannelInfo> {
  return apiFetch<ChannelInfo>(`/api/channels/${encodeURIComponent(platform)}`);
}

export async function apiPostChannel(payload: ChannelUpsertPayload): Promise<ChannelInfo> {
  return apiFetch<ChannelInfo>('/api/channels', { method: 'POST', json: payload });
}

export async function apiPutChannel(
  platform: string,
  payload: ChannelUpsertPayload,
): Promise<ChannelInfo> {
  return apiFetch<ChannelInfo>(`/api/channels/${encodeURIComponent(platform)}`, {
    method: 'PUT',
    json: payload,
  });
}

export async function apiPatchChannel(
  platform: string,
  payload: ChannelPatchPayload,
): Promise<ChannelInfo> {
  return apiFetch<ChannelInfo>(`/api/channels/${encodeURIComponent(platform)}`, {
    method: 'PATCH',
    json: payload,
  });
}

export async function apiDeleteChannel(platform: string): Promise<void> {
  await apiFetch(`/api/channels/${encodeURIComponent(platform)}`, { method: 'DELETE' });
}

// ─── Platform Gateway ────────────────────────────────────────────────────

export async function apiGetPlatformGatewayStatus(): Promise<PlatformGatewayStatus> {
  return apiFetch<PlatformGatewayStatus>('/api/platform-gateway/status');
}

export async function apiPostPlatformGatewayStart(force = false): Promise<Record<string, unknown>> {
  const q = force ? '?force=true' : '';
  return apiFetch<Record<string, unknown>>(`/api/platform-gateway/start${q}`, { method: 'POST' });
}

export async function apiPostPlatformGatewayStop(): Promise<Record<string, unknown>> {
  return apiFetch<Record<string, unknown>>('/api/platform-gateway/stop', { method: 'POST' });
}
