/**
 * useApprovalFlow — Approval + Clarify interaction hook.
 * Manages approval requests and clarify questions from agent.
 */
import { useCallback } from 'react';
import { useSessionStore } from '../stores/sessionStore';
import { apiFetch } from '../api/client';

export function useApprovalFlow() {
  const approval = useSessionStore((s) => s.approval);
  const clarify = useSessionStore((s) => s.clarify);
  const activeId = useSessionStore((s) => s.activeId);

  /** Respond to approval request */
  const respondApproval = useCallback(async (approved: boolean, message?: string): Promise<void> => {
    if (!approval) return;
    try {
      await apiFetch('/api/chat/approval/respond', {
        method: 'POST',
        json: {
          session_id: approval.sessionId,
          approved,
          message,
        },
      });
    } finally {
      useSessionStore.getState().setApproval(null);
    }
  }, [approval]);

  /** Respond to clarify request */
  const respondClarify = useCallback(async (answer: string): Promise<void> => {
    if (!clarify) return;
    try {
      await apiFetch('/api/chat/clarify/respond', {
        method: 'POST',
        json: {
          session_id: clarify.sessionId,
          request_id: clarify.requestId,
          answer,
        },
      });
    } finally {
      useSessionStore.getState().setClarify(null);
    }
  }, [clarify]);

  /** Dismiss approval without responding */
  const dismissApproval = useCallback(() => {
    useSessionStore.getState().setApproval(null);
  }, []);

  /** Dismiss clarify without responding */
  const dismissClarify = useCallback(() => {
    useSessionStore.getState().setClarify(null);
  }, []);

  return {
    approval,
    clarify,
    activeId,
    respondApproval,
    respondClarify,
    dismissApproval,
    dismissClarify,
  };
}
