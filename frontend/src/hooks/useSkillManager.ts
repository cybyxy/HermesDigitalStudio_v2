/**
 * useSkillManager — Skill management hook.
 * Loads and manages skills per agent.
 */
import { useState, useCallback } from 'react';
import * as api from '../api';

export interface SkillInfo {
  path?: string;
  name?: string;
  description?: string;
}

export function useSkillManager() {
  const [loading, setLoading] = useState(false);
  const [skills, setSkills] = useState<SkillInfo[]>([]);

  /** Load all skills */
  const loadSkills = useCallback(async (): Promise<SkillInfo[]> => {
    setLoading(true);
    try {
      const data = await api.apiGetSkills();
      // Flatten all agent skills into a single list
      const allSkills = data.flatMap((agent) =>
        agent.skills.map((s) => ({
          path: s.path,
          name: s.name,
          description: s.description,
        })),
      );
      setSkills(allSkills);
      return allSkills;
    } catch {
      return [];
    } finally {
      setLoading(false);
    }
  }, []);

  /** Get skill markdown content */
  const getSkillContent = useCallback(async (path: string): Promise<string> => {
    return api.apiGetSkillMd(path);
  }, []);

  /** Update skill markdown content */
  const updateSkillContent = useCallback(async (path: string, content: string): Promise<boolean> => {
    setLoading(true);
    try {
      await api.apiPutSkillMd(path, content);
      return true;
    } catch {
      return false;
    } finally {
      setLoading(false);
    }
  }, []);

  return {
    skills,
    loading,
    loadSkills,
    getSkillContent,
    updateSkillContent,
  };
}
