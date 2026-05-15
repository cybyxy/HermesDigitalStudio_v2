/**
 * UI Store — 管理所有面板可见性、模态框状态、停靠面板内容
 */
import { create } from 'zustand';

interface UiState {
  showSettings: boolean;
  showTaskManager: boolean;
  showAgentModal: boolean;
  showAgentList: boolean;
  showModelManager: boolean;
  showChannelManager: boolean;
  showSkillManager: boolean;
  showMemoryManager: boolean;
  dockContent: 'agents' | 'tasks' | 'channels' | 'models' | 'skills' | 'memory' | null;

  setShowSettings: (show: boolean) => void;
  setShowTaskManager: (show: boolean) => void;
  setShowAgentModal: (show: boolean) => void;
  setShowAgentList: (show: boolean) => void;
  setShowModelManager: (show: boolean) => void;
  setShowChannelManager: (show: boolean) => void;
  setShowSkillManager: (show: boolean) => void;
  setShowMemoryManager: (show: boolean) => void;
}

export const useUiStore = create<UiState>((set) => ({
  showSettings: false,
  showTaskManager: false,
  showAgentModal: false,
  showAgentList: false,
  showModelManager: false,
  showChannelManager: false,
  showSkillManager: false,
  showMemoryManager: false,
  dockContent: null,

  setShowSettings: (show) =>
    set({
      showSettings: show,
      ...(show
        ? {
            showTaskManager: false,
            showAgentList: false,
            showChannelManager: false,
            showModelManager: false,
            showSkillManager: false,
            showMemoryManager: false,
            dockContent: null,
          }
        : {}),
    }),

  setShowTaskManager: (show) =>
    set({
      showTaskManager: show,
      showAgentList: false,
      dockContent: show ? 'tasks' : null,
    }),

  setShowAgentModal: (show) => set({ showAgentModal: show }),

  setShowAgentList: (show) =>
    set({
      showAgentList: show,
      showTaskManager: false,
      showChannelManager: false,
      dockContent: show ? 'agents' : null,
    }),

  setShowModelManager: (show) =>
    set({
      showModelManager: show,
      showAgentList: false,
      showTaskManager: false,
      showChannelManager: false,
      dockContent: show ? 'models' : null,
    }),

  setShowChannelManager: (show) =>
    set({
      showChannelManager: show,
      showAgentList: false,
      showTaskManager: false,
      showModelManager: false,
      dockContent: show ? 'channels' : null,
    }),

  setShowSkillManager: (show) =>
    set({
      showSkillManager: show,
      showAgentList: false,
      showTaskManager: false,
      showChannelManager: false,
      showModelManager: false,
      dockContent: show ? 'skills' : null,
    }),

  setShowMemoryManager: (show) =>
    set({
      showMemoryManager: show,
      showAgentList: false,
      showTaskManager: false,
      showChannelManager: false,
      showModelManager: false,
      showSkillManager: false,
      dockContent: show ? 'memory' : null,
    }),
}));
