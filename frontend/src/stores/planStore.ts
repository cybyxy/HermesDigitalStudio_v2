/**
 * 规划 Store — 管理规划时间线、任务列表、规划缓存
 */
import { create } from 'zustand';
import { planMessageStillExists } from '../lib/planRun';
import type { PlanTimelineRunState, PlanArtifact } from '../types';
import type { PlanSummary } from '../api/types';
import { useSessionStore } from './sessionStore';

interface AgentPlanCache {
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

interface PlanStoreState {
  planTimelineRun: PlanTimelineRunState | null;
  taskListPlans: PlanSummary[];
  taskListLoadEpoch: number;
  leftPanelTaskPlanId: number | null;
  agentLastPlan: Record<string, AgentPlanCache>;

  setPlanTimelineRun: (run: PlanTimelineRunState | null) => void;
  ensurePlanTimelineRunValid: () => void;
  setTaskListPlans: (plans: PlanSummary[]) => void;
  bumpTaskListLoadEpoch: () => void;
  clearTaskListCacheAfterDbPurge: () => void;
  setLeftPanelTaskPlanId: (planId: number | null) => void;
  removePlan: (planId: number) => void;
  setAgentLastPlan: (agentId: string, plan: AgentPlanCache | null) => void;
  clearAgentLastPlans: () => void;

  // Aliases for compatibility
  deleteTaskPlan: (planId: number) => void;
  clearAllTasks: () => void;
}

export const usePlanStore = create<PlanStoreState>((set, get) => ({
  planTimelineRun: null,
  taskListPlans: [],
  taskListLoadEpoch: 0,
  leftPanelTaskPlanId: null,
  agentLastPlan: {},

  setPlanTimelineRun: (run) => set({ planTimelineRun: run }),

  setTaskListPlans: (plans) => set({ taskListPlans: plans }),

  bumpTaskListLoadEpoch: () => set((s) => ({ taskListLoadEpoch: s.taskListLoadEpoch + 1 })),

  clearTaskListCacheAfterDbPurge: () =>
    set((s) => ({
      taskListLoadEpoch: s.taskListLoadEpoch + 1,
      taskListPlans: [],
      agentLastPlan: {},
      leftPanelTaskPlanId: null,
    })),

  setLeftPanelTaskPlanId: (planId) => set({ leftPanelTaskPlanId: planId }),

  removePlan: (planId) =>
    set((state) => ({
      taskListPlans: state.taskListPlans.filter((p) => p.id !== planId),
      leftPanelTaskPlanId:
        state.leftPanelTaskPlanId === planId ? null : state.leftPanelTaskPlanId,
    })),

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

  deleteTaskPlan: (planId) => {
    get().removePlan(planId);
  },

  clearAllTasks: () => {
    get().clearTaskListCacheAfterDbPurge();
  },

  ensurePlanTimelineRunValid: () => {
    const state = get();
    const r = state.planTimelineRun;
    if (!r) return;
    const sessions = useSessionStore.getState().sessions;
    if (!planMessageStillExists(sessions, r.planAnchorTs)) {
      set({ planTimelineRun: null });
      return;
    }
    const art = sessions
      .flatMap((s) => s.messages)
      .find(
        (m) =>
          m.role === 'assistant' &&
          m.timestamp === r.planAnchorTs &&
          m.planArtifact,
      );
    const n = art && art.role === 'assistant' && art.planArtifact ? art.planArtifact.steps.length : 0;
    if (n > 0 && r.stepStatuses.length !== n) {
      set({ planTimelineRun: null });
    }
  },
}));
