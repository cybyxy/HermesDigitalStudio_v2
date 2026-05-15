/**
 * Agent Store — 管理代理列表、场景推理状态、编辑状态
 */
import { create } from 'zustand';
import type { AgentInfo, AgentSceneInferState, PlanArtifact } from '../types';
import type { PlanSummary } from '../api/types';

const INITIAL_AGENT_SCENE_INFER: AgentSceneInferState = {
  phase: 'idle',
  thinkingSnippet: '',
  toolSnippet: '',
  doneSnippet: '',
  doneExpiresAt: 0,
  socialSnippet: '',
  socialExpiresAt: 0,
  smallThoughtSnippet: '',
  smallThoughtExpiresAt: 0,
};

interface AgentStoreState {
  agents: AgentInfo[];
  editingAgentId: string | null;
  selectedAgentId: string | null;
  agentSceneInfer: Record<string, AgentSceneInferState>;
  agentLastPlan: Record<
    string,
    {
      artifact: PlanArtifact;
      anchorTs: number;
      participation: 'led' | 'participated';
      dbPlan: {
        status: string;
        steps: Array<{
          stepIndex: number;
          stepStatus: string;
          executor?: string;
          sessionId?: string;
          completedAt?: number;
        }>;
      } | null;
    }
  >;

  setEditingAgentId: (id: string | null) => void;
  setSelectedAgentId: (id: string | null) => void;
  setAgents: (agents: AgentInfo[]) => void;
  removeAgent: (agentId: string) => void;
  patchAgentSceneInfer: (agentId: string, patch: Partial<AgentSceneInferState>) => void;
  clearAgentSceneInfer: (agentId: string) => void;
  setAgentLastPlan: (
    agentId: string,
    plan: {
      artifact: PlanArtifact;
      anchorTs: number;
      participation: 'led' | 'participated';
      dbPlan: {
        status: string;
        steps: Array<{
          stepIndex: number;
          stepStatus: string;
          executor?: string;
          sessionId?: string;
          completedAt?: number;
        }>;
      } | null;
    } | null,
  ) => void;
  clearAgentLastPlans: () => void;

  // Complex infer state transitions
  setInferState: (
    agentId: string,
    phase: string,
    stateInfo: { phase?: string; message?: string } | null,
  ) => void;
  appendReasoning: (agentId: string, text: string) => void;

  // Reasoning result modal
  reasoningResultModal: { agentId: string; text: string } | null;
  setReasoningResultModal: (data: { agentId: string; text: string } | null) => void;
}

export const useAgentStore = create<AgentStoreState>((set) => ({
  agents: [],
  editingAgentId: null,
  selectedAgentId: null,
  agentSceneInfer: {},
  agentLastPlan: {},
  reasoningResultModal: null,

  setEditingAgentId: (id) => set({ editingAgentId: id }),
  setSelectedAgentId: (id) => set({ selectedAgentId: id as string | null }),
  setAgents: (agents) => set({ agents }),
  removeAgent: (agentId) =>
    set((state) => ({
      agents: state.agents.filter((a) => a.agentId !== agentId),
    })),

  patchAgentSceneInfer: (agentId, patch) =>
    set((state) => ({
      agentSceneInfer: {
        ...state.agentSceneInfer,
        [agentId]: {
          ...INITIAL_AGENT_SCENE_INFER,
          ...state.agentSceneInfer[agentId],
          ...patch,
        },
      },
    })),

  clearAgentSceneInfer: (agentId) =>
    set((state) => {
      const next = { ...state.agentSceneInfer };
      delete next[agentId];
      return { agentSceneInfer: next };
    }),

  setAgentLastPlan: (agentId, plan) =>
    set((state) => {
      if (plan === null) {
        const next = { ...state.agentLastPlan };
        delete next[agentId];
        return { agentLastPlan: next };
      }
      return { agentLastPlan: { ...state.agentLastPlan, [agentId]: plan } };
    }),

  clearAgentLastPlans: () => set({ agentLastPlan: {} }),

  setInferState: (agentId, phase, stateInfo) =>
    set((prev) => {
      const current = prev.agentSceneInfer[agentId] ?? { ...INITIAL_AGENT_SCENE_INFER };
      const patch: Partial<AgentSceneInferState> = {};
      if (phase === 'active' || phase === 'thinking') {
        patch.phase = 'thinking';
        patch.thinkingSnippet = stateInfo?.message ?? current.thinkingSnippet;
      } else if (phase === 'tool') {
        patch.phase = 'tool';
        patch.toolSnippet = stateInfo?.message ?? current.toolSnippet;
      } else if (phase === 'done') {
        patch.phase = 'done';
        patch.doneSnippet = stateInfo?.message ?? '';
        patch.doneExpiresAt = Date.now() + 5000;
      } else if (phase === 'social') {
        patch.phase = 'social';
        patch.socialSnippet = stateInfo?.message ?? '';
        patch.socialExpiresAt = Date.now() + 8000;
      } else {
        patch.phase = 'idle';
      }
      return {
        agentSceneInfer: {
          ...prev.agentSceneInfer,
          [agentId]: { ...current, ...patch },
        },
      };
    }),

  appendReasoning: (agentId, text) =>
    set((prev) => {
      const current = prev.agentSceneInfer[agentId] ?? { ...INITIAL_AGENT_SCENE_INFER };
      return {
        agentSceneInfer: {
          ...prev.agentSceneInfer,
          [agentId]: {
            ...current,
            phase: 'thinking' as const,
            thinkingSnippet: (current.thinkingSnippet + text).slice(-200),
          },
        },
      };
    }),

  setReasoningResultModal: (data) => set({ reasoningResultModal: data }),
}));
