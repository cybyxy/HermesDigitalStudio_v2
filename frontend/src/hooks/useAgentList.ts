/**
 * useAgentList — Agent CRUD + selection hook.
 * Loads agent list, creates/deletes agents, and manages agent switching.
 */
import { useState, useCallback, useEffect } from 'react';
import { useSessionStore } from '../stores/sessionStore';
import { useAgentStore } from '../stores/agentStore';
import { useAppStore } from '../stores/appStore';
import { useOfficeAgentPoseStore } from '../stores/officeAgentPoseStore';
import * as api from '../api';
import type { AgentInfo } from '../types';

export function useAgentList() {
  const [loading, setLoading] = useState(false);
  const agents = useAgentStore((s) => s.agents);
  const initialized = useAppStore((s) => s.initialized);

  /** Fetch all agents from API and update store */
  const refreshAgents = useCallback(async (): Promise<AgentInfo[]> => {
    setLoading(true);
    try {
      const data = await api.apiGetAgents();
      useAgentStore.getState().setAgents(data);
      // 从数据库加载 agent 位姿（坐标、方向）到场景位姿 Store
      useOfficeAgentPoseStore.getState().hydrateFromAgents(data);
      return data;
    } catch {
      return [];
    } finally {
      setLoading(false);
    }
  }, []);

  /** Initial load */
  useEffect(() => {
    if (!initialized) {
      refreshAgents();
    }
  }, [initialized, refreshAgents]);

  /** Create a new agent */
  const createAgent = useCallback(async (agentData: Record<string, unknown>): Promise<AgentInfo | null> => {
    setLoading(true);
    try {
      const result = await api.apiPostAgent(agentData as {
        displayName: string;
        profile: string;
        avatar?: string;
        gender?: string;
        personality?: string;
        catchphrases?: string;
        memes?: string;
        identity?: string;
        style?: string;
        defaults?: string;
        avoid?: string;
        coreTruths?: string;
      });
      await refreshAgents();
      const newAgent = agents.find(a => a.agentId === result.agentId);
      return newAgent ?? null;
    } catch {
      return null;
    } finally {
      setLoading(false);
    }
  }, [refreshAgents, agents]);

  /** Delete an agent */
  const deleteAgent = useCallback(async (agentId: string): Promise<boolean> => {
    setLoading(true);
    try {
      await api.apiDeleteAgent(agentId);
      await refreshAgents();
      return true;
    } catch {
      return false;
    } finally {
      setLoading(false);
    }
  }, [refreshAgents]);

  /** Switch to an agent — creates session if needed */
  const switchAgent = useCallback(async (agentId: string): Promise<string | null> => {
    const sessionStore = useSessionStore.getState();
    const agent = agents.find((a) => a.agentId === agentId);
    if (!agent) return null;

    // Check for existing default session
    const existingSession = sessionStore.sessions.find((s) => s.agentId === agentId);
    if (existingSession) {
      sessionStore.setActiveId(existingSession.id);
      return existingSession.id;
    }

    // Create new session
    try {
      const { sessionId } = await api.apiPostSession(agentId, 120);
      sessionStore.addSession({ id: sessionId, agentId, title: '', messages: [], processRows: [], streaming: false, unread: false });
      sessionStore.setActiveId(sessionId);
      return sessionId;
    } catch {
      return null;
    }
  }, [agents]);

  /** Get agent by ID */
  const getAgent = useCallback((agentId: string): AgentInfo | undefined => {
    return agents.find((a) => a.agentId === agentId);
  }, [agents]);

  return {
    agents,
    loading,
    refreshAgents,
    createAgent,
    deleteAgent,
    switchAgent,
    getAgent,
  };
}
