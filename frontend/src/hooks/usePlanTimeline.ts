/**
 * usePlanTimeline — Plan chain operations hook.
 * Manages plan creation, timeline run state, and task list loading.
 */
import { useState, useCallback } from 'react';
import { usePlanStore } from '../stores/planStore';
import * as api from '../api';
import type { PlanSummary } from '../api/types';

export function usePlanTimeline() {
  const [loading, setLoading] = useState(false);
  const planTimelineRun = usePlanStore((s) => s.planTimelineRun);
  const taskListPlans = usePlanStore((s) => s.taskListPlans);
  const leftPanelTaskPlanId = usePlanStore((s) => s.leftPanelTaskPlanId);

  /** Load plans for a specific agent */
  const loadAgentPlans = useCallback(async (agentId: string): Promise<PlanSummary[]> => {
    setLoading(true);
    try {
      const response = await api.apiGetPlansByAgent(agentId);
      return response.plans ?? [];
    } catch {
      return [];
    } finally {
      setLoading(false);
    }
  }, []);

  /** Load all plans for the active session */
  const loadAllPlans = useCallback(async (sessionId: string): Promise<PlanSummary[]> => {
    setLoading(true);
    try {
      const plans = await api.apiGetPlans(sessionId);
      usePlanStore.getState().setTaskListPlans(plans);
      return plans;
    } catch {
      return [];
    } finally {
      setLoading(false);
    }
  }, []);

  /** Delete a plan */
  const deletePlan = useCallback(async (planId: number): Promise<boolean> => {
    setLoading(true);
    try {
      await api.apiDeletePlan(planId);
      usePlanStore.getState().deleteTaskPlan(planId);
      return true;
    } catch {
      return false;
    } finally {
      setLoading(false);
    }
  }, []);

  /** Delete all plans */
  const deleteAllPlans = useCallback(async (): Promise<boolean> => {
    setLoading(true);
    try {
      await api.apiDeleteAllPlans();
      usePlanStore.getState().clearAllTasks();
      return true;
    } catch {
      return false;
    } finally {
      setLoading(false);
    }
  }, []);

  /** Select a plan in left panel */
  const selectTaskPlan = useCallback((planId: number | null) => {
    usePlanStore.getState().setLeftPanelTaskPlanId(planId);
  }, []);

  return {
    planTimelineRun,
    taskListPlans,
    leftPanelTaskPlanId,
    loading,
    loadAgentPlans,
    loadAllPlans,
    deletePlan,
    deleteAllPlans,
    selectTaskPlan,
  };
}
