/**
 * useSessionManager — Session CRUD + selection hook.
 * Creates, selects, and deletes chat sessions for agents.
 */
import { useState, useCallback } from 'react';
import { useSessionStore } from '../stores/sessionStore';
import * as api from '../api';
import type { ChatRow, ProcessRow } from '../types';
import { historyTimestampToMs } from '../lib/sseEventProcessor';

export function useSessionManager() {
  const [loading, setLoading] = useState(false);
  const sessions = useSessionStore((s) => s.sessions);
  const activeId = useSessionStore((s) => s.activeId);
  const setActiveId = useSessionStore((s) => s.setActiveId);

  /** Create a new session for an agent (or reuse existing default session) */
  const createSession = useCallback(async (agentId: string, timeoutMinutes = 120): Promise<string | null> => {
    setLoading(true);
    try {
      const result = await api.apiPostSession(agentId, timeoutMinutes);
      return result.sessionId;
    } catch {
      return null;
    } finally {
      setLoading(false);
    }
  }, []);

  /** Load session history from the server */
  const loadHistory = useCallback(async (sessionId: string): Promise<{
    messages: ChatRow[];
    processRows: ProcessRow[];
  } | null> => {
    try {
      const data = await api.apiGetHistory(sessionId);
      return {
        messages: (data.messages ?? []) as ChatRow[],
        processRows: (data.processRows ?? []) as ProcessRow[],
      };
    } catch {
      return null;
    }
  }, []);

  /** Select (switch to) a session */
  const selectSession = useCallback((sessionId: string | null) => {
    setActiveId(sessionId);

    // Load history for newly selected session
    if (sessionId) {
      loadHistory(sessionId).then((data) => {
        if (data) {
          const store = useSessionStore.getState();
          store.patchSession(sessionId, (s) => ({
            ...s,
            messages: data.messages,
            processRows: data.processRows,
          }));
        }
      }).catch(() => {
        // Silently fail
      });
    }
  }, [setActiveId, loadHistory]);

  /** Delete a session (removes from store + closes SSE will be handled externally) */
  const deleteSession = useCallback((sessionId: string) => {
    const store = useSessionStore.getState();
    store.removeSession(sessionId);
  }, []);

  return {
    sessions,
    activeId,
    loading,
    createSession,
    selectSession,
    deleteSession,
    loadHistory,
  };
}
