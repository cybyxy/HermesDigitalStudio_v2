/**
 * useTaskList — Task list management hook.
 * Loads and manages the task list in the bottom dock panel.
 */
import { useState, useCallback } from 'react';
import { usePlanStore } from '../stores/planStore';
import * as api from '../api';
import type { PlanSummary } from '../api/types';

export function useTaskList() {
  const [loading, setLoading] = useState(false);
  const taskListPlans = usePlanStore((s) => s.taskListPlans);
  const leftPanelTaskPlanId = usePlanStore((s) => s.leftPanelTaskPlanId);

  /** Load all task plans for the given session */
  const loadTasks = useCallback(async (sessionId: string): Promise<PlanSummary[]> => {
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

  /** Select a task in the left panel timeline */
  const selectTask = useCallback((planId: number | null) => {
    usePlanStore.getState().setLeftPanelTaskPlanId(planId);
  }, []);

  /** Delete a single task plan */
  const deleteTask = useCallback(async (planId: number): Promise<boolean> => {
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

  /** Clear all tasks from DB and store */
  const clearAllTasks = useCallback(async (): Promise<boolean> => {
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

  return {
    taskListPlans,
    leftPanelTaskPlanId,
    loading,
    loadTasks,
    selectTask,
    deleteTask,
    clearAllTasks,
  };
}
