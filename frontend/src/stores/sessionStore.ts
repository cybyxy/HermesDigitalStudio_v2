/**
 * 会话 Store — 管理会话列表、当前激活会话、输入状态、审批/澄清
 */
import { create } from 'zustand';
import type {
  SessionState,
  ChatRow,
  ProcessRow,
  PendingApproval,
  PendingClarify,
} from '../types';

interface SessionStateStore {
  sessions: SessionState[];
  activeId: string | null;
  input: string;
  sending: boolean;
  approval: PendingApproval | null;
  clarify: PendingClarify | null;

  setActiveId: (id: string | null) => void;
  setInput: (input: string) => void;
  setSending: (sending: boolean) => void;
  setApproval: (approval: PendingApproval | null) => void;
  setClarify: (clarify: PendingClarify | null) => void;
  setSessions: (fn: (sessions: SessionState[]) => SessionState[]) => void;
  patchSession: (sid: string, fn: (s: SessionState) => SessionState) => void;
  appendMessage: (sid: string, row: ChatRow) => void;
  appendProcessRow: (sid: string, row: ProcessRow) => void;
  addSession: (session: SessionState) => void;
  addSessions: (sessions: SessionState[]) => void;
  removeSession: (id: string) => void;
  updateSessionTitle: (id: string, title: string) => void;

  // SSE event handler methods
  appendChat: (sid: string, row: ChatRow) => void;
  setStreaming: (sid: string, streaming: boolean) => void;
  appendDelta: (sid: string, delta: string) => void;
  finalizeMessage: (sid: string, payload: Record<string, unknown>) => void;
  setPlanArtifact: (sid: string, artifact: Record<string, unknown>) => void;
  appendToolCall: (sid: string, toolCall: Record<string, unknown>) => void;
  updateToolProgress: (sid: string, payload: Record<string, unknown>) => void;
  completeTool: (sid: string, payload: Record<string, unknown>) => void;
  updateSessionInfo: (sid: string, payload: Record<string, unknown>) => void;
  appendError: (sid: string, errorText: string) => void;

  // Reasoning stream methods
  appendReasoningDelta: (sid: string, text: string) => void;
  finalizeReasoning: (sid: string) => void;

  // Session restore state (Step 0: auto-load last session on startup)
  isRestoringSession: boolean;
  setIsRestoringSession: (v: boolean) => void;
}

export const useSessionStore = create<SessionStateStore>((set) => ({
  sessions: [],
  activeId: null,
  input: '',
  sending: false,
  approval: null,
  clarify: null,
  isRestoringSession: false,

  setActiveId: (id) => set({ activeId: id }),
  setInput: (input) => set({ input }),
  setSending: (sending) => set({ sending }),
  setApproval: (approval) => set({ approval }),
  setClarify: (clarify) => set({ clarify }),
  setIsRestoringSession: (v) => set({ isRestoringSession: v }),

  patchSession: (sid, fn) =>
    set((state) => ({
      sessions: state.sessions.map((s) => (s.id === sid ? fn(s) : s)),
    })),

  appendMessage: (sid, row) =>
    set((state) => ({
      sessions: state.sessions.map((s) =>
        s.id === sid ? { ...s, messages: [...s.messages, row] } : s,
      ),
    })),

  appendProcessRow: (sid, row) =>
    set((state) => ({
      sessions: state.sessions.map((s) =>
        s.id === sid ? { ...s, processRows: [...(s.processRows ?? []), row] } : s,
      ),
    })),

  addSession: (session) =>
    set((state) => ({
      sessions: [...state.sessions, { ...session, processRows: session.processRows ?? [] }],
    })),

  addSessions: (newSessions) =>
    set((state) => {
      const existing = new Set(state.sessions.map((s) => s.id));
      const toAdd = newSessions
        .filter((s) => !existing.has(s.id))
        .map((s) => ({ ...s, processRows: s.processRows ?? [] }));
      return { sessions: [...state.sessions, ...toAdd] };
    }),

  removeSession: (id) =>
    set((state) => {
      const removed = state.sessions.find((s) => s.id === id);
      const next = state.sessions.filter((s) => s.id !== id);

      // Cross-store cleanup: clear infer state & plan timeline
      if (removed) {
        // Lazy import to avoid circular dependency at module level
        const { useAgentStore } = require('./agentStore') as typeof import('./agentStore');
        useAgentStore.getState().clearAgentSceneInfer(removed.agentId);

        const { usePlanStore } = require('./planStore') as typeof import('./planStore');
        const planState = usePlanStore.getState();
        if (planState.planTimelineRun?.sourceSessionId === id) {
          planState.setPlanTimelineRun(null);
        }
      }

      return {
        sessions: next,
        activeId: state.activeId === id ? (next[0]?.id ?? null) : state.activeId,
      };
    }),

  updateSessionTitle: (id, title) =>
    set((state) => ({
      sessions: state.sessions.map((s) => (s.id === id ? { ...s, title } : s)),
    })),

  setSessions: (fn) =>
    set((state) => ({
      sessions: fn(state.sessions),
    })),

  // --- SSE event handler aliases / additions ---

  appendChat: (sid, row) =>
    set((state) => {
      const exists = state.sessions.some((s) => s.id === sid);
      if (!exists) {
        const msgAgentId = (row as { agentId?: string }).agentId ?? '';
        return {
          sessions: [...state.sessions, {
            id: sid,
            agentId: msgAgentId,
            title: '',
            messages: [row],
            processRows: [],
            streaming: true,
            unread: false,
          }],
        };
      }
      return {
        sessions: state.sessions.map((s) =>
          s.id === sid ? { ...s, messages: [...s.messages, row] } : s,
        ),
      };
    }),

  setStreaming: (sid, streaming) =>
    set((state) => ({
      sessions: state.sessions.map((s) =>
        s.id === sid ? { ...s, streaming } : s,
      ),
    })),

  appendDelta: (sid, delta) =>
    set((state) => ({
      sessions: state.sessions.map((s) => {
        if (s.id !== sid) return s;
        const msgs = [...s.messages];
        const last = msgs[msgs.length - 1];
        if (last && last.role === 'assistant') {
          msgs[msgs.length - 1] = { ...last, text: last.text + delta };
        }
        return { ...s, messages: msgs };
      }),
    })),

  finalizeMessage: (sid, payload) =>
    set((state) => ({
      sessions: state.sessions.map((s) => {
        if (s.id !== sid) return s;
        const msgs = [...s.messages];
        const last = msgs[msgs.length - 1];
        if (last && last.role === 'assistant') {
          msgs[msgs.length - 1] = {
            ...last,
            streaming: false,
            thinking: typeof payload.thinking === 'string' ? payload.thinking : undefined,
            timestamp: last.timestamp ?? Date.now(),
          };
        }
        return { ...s, messages: msgs, streaming: false };
      }),
    })),

  setPlanArtifact: (sid, artifact) =>
    set((state) => ({
      sessions: state.sessions.map((s) => {
        if (s.id !== sid) return s;
        const msgs = [...s.messages];
        const last = msgs[msgs.length - 1];
        if (last && last.role === 'assistant') {
          msgs[msgs.length - 1] = { ...last, planArtifact: artifact as unknown as import('../types').PlanArtifact };
        }
        return { ...s, messages: msgs };
      }),
    })),

  appendToolCall: (sid, toolCall) =>
    set((state) => ({
      sessions: state.sessions.map((s) => {
        if (s.id !== sid) return s;
        const tc = toolCall as Record<string, unknown>;
        const row: ProcessRow = {
          id: String(tc.id ?? `tool_${Date.now()}`),
          variant: 'tool',
          title: `🔧 ${String(tc.name ?? 'tool')}`,
          body: JSON.stringify(tc.input ?? {}, null, 2),
          toolCalls: [{
            id: String(tc.id ?? ''),
            name: String(tc.name ?? ''),
            input: (tc.input ?? {}) as Record<string, unknown>,
            status: 'generating',
          }],
          streaming: true,
          timestamp: Date.now(),
        };
        return { ...s, processRows: [...(s.processRows ?? []), row] };
      }),
    })),

  updateToolProgress: (sid, payload) =>
    set((state) => ({
      sessions: state.sessions.map((s) => {
        if (s.id !== sid) return s;
        const rows = [...(s.processRows ?? [])];
        const last = rows[rows.length - 1];
        if (last && last.variant === 'tool') {
          rows[rows.length - 1] = {
            ...last,
            body: String(payload.progress ?? payload.text ?? last.body),
            toolCalls: last.toolCalls?.map((tc) => ({
              ...tc,
              status: 'progress' as const,
              progress: String(payload.progress ?? ''),
            })),
          };
        }
        return { ...s, processRows: rows };
      }),
    })),

  completeTool: (sid, payload) =>
    set((state) => ({
      sessions: state.sessions.map((s) => {
        if (s.id !== sid) return s;
        const rows = [...(s.processRows ?? [])];
        const last = rows[rows.length - 1];
        if (last && last.variant === 'tool') {
          rows[rows.length - 1] = {
            ...last,
            streaming: false,
            body: String(payload.result ?? payload.text ?? last.body),
            toolCalls: last.toolCalls?.map((tc) => ({
              ...tc,
              status: 'complete' as const,
              result: String(payload.result ?? ''),
            })),
          };
        }
        return { ...s, processRows: rows };
      }),
    })),

  updateSessionInfo: (sid, payload) =>
    set((state) => ({
      sessions: state.sessions.map((s) => {
        if (s.id !== sid) return s;
        const total = typeof payload.total === 'number' ? payload.total : undefined;
        const contextMax = typeof payload.contextMax === 'number' ? payload.contextMax : undefined;
        const contextUsed = typeof payload.contextUsed === 'number' ? payload.contextUsed : undefined;
        return {
          ...s,
          title: typeof payload.title === 'string' ? payload.title : s.title,
          lastUsage: total != null ? {
            total,
            contextMax,
            contextUsed,
            contextPercent: contextMax ? Math.round((contextUsed ?? 0) / contextMax * 100) : undefined,
          } : s.lastUsage,
        };
      }),
    })),

  appendError: (sid, errorText) =>
    set((state) => ({
      sessions: state.sessions.map((s) => {
        if (s.id !== sid) return s;
        const row: ProcessRow = {
          id: `err_${Date.now()}`,
          variant: 'reasoning',
          title: '❌ 错误',
          body: errorText,
          timestamp: Date.now(),
        };
        return { ...s, processRows: [...(s.processRows ?? []), row] };
      }),
    })),

  appendReasoningDelta: (sid, text) =>
    set((state) => ({
      sessions: state.sessions.map((s) => {
        if (s.id !== sid) return s;
        const rows = [...(s.processRows ?? [])];
        const last = rows[rows.length - 1];
        if (last && last.variant === 'reasoning' && last.streaming) {
          rows[rows.length - 1] = {
            ...last,
            body: last.body + text,
          };
        } else {
          rows.push({
            id: `reason_${Date.now()}`,
            variant: 'reasoning',
            title: '推理过程',
            body: text,
            streaming: true,
            timestamp: Date.now(),
          });
        }
        return { ...s, processRows: rows };
      }),
    })),

  finalizeReasoning: (sid) =>
    set((state) => ({
      sessions: state.sessions.map((s) => {
        if (s.id !== sid) return s;
        const rows = [...(s.processRows ?? [])];
        const last = rows[rows.length - 1];
        if (last && last.variant === 'reasoning' && last.streaming) {
          rows[rows.length - 1] = { ...last, streaming: false };
        }
        return { ...s, processRows: rows };
      }),
    })),
}));
