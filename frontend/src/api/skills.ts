/**
 * Skills API
 */
import { apiFetch } from './client';
import type { AgentSkills } from '../types';
import type { SkillsResponse } from './types';

export type { SkillsResponse };

export async function apiGetSkills(): Promise<AgentSkills[]> {
  const data = await apiFetch<SkillsResponse>('/api/chat/skills');
  return data.agents ?? [];
}

export async function apiGetSkillMd(skillPath: string): Promise<string> {
  const q = new URLSearchParams({ skill_path: skillPath });
  const data = await apiFetch<{ content: string }>(`/api/chat/skills/read?${q}`);
  return data.content;
}

export async function apiPutSkillMd(skillPath: string, content: string): Promise<void> {
  await apiFetch('/api/chat/skills/content', {
    method: 'PUT',
    json: { skillPath, content },
  });
}

export async function apiDeleteSkill(skillPath: string): Promise<void> {
  const q = new URLSearchParams({ skill_path: skillPath });
  await apiFetch(`/api/chat/skills?${q}`, { method: 'DELETE' });
}
