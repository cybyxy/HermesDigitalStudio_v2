/**
 * Settings API
 */
import { apiFetch } from './client';
import type { SettingsResponse } from './types';

export type { SettingsResponse };

export async function apiGetSettings(): Promise<SettingsResponse> {
  return apiFetch<SettingsResponse>('/api/settings');
}
