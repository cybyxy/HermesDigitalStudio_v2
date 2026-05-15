/**
 * 技能 Store — 管理技能列表、技能管理器可见性
 */
import { create } from 'zustand';
import type { AgentSkills } from '../types';

interface SkillStoreState {
  skills: AgentSkills[];
  showSkillManager: boolean;

  setSkills: (skills: AgentSkills[]) => void;
  setShowSkillManager: (show: boolean) => void;
}

export const useSkillStore = create<SkillStoreState>((set) => ({
  skills: [],
  showSkillManager: false,

  setSkills: (skills) => set({ skills }),
  setShowSkillManager: (show) => set({ showSkillManager: show }),
}));
