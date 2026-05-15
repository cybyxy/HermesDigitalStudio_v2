import { create } from 'zustand';
import { planMessageStillExists } from '../lib/planRun';
import type { PlanSummary } from '../api/types';
import type {
  AgentInfo,
  AgentSceneInferState,
  AgentSkills,
  Attachment,
  ChannelInfo,
  ChatRow,
  ModelInfo,
  PendingApproval,
  PendingClarify,
  PlanArtifact,
  PlanTimelineRunState,
  ProcessRow,
  ProviderInfo,
  SessionState,
} from '../types';

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

export interface ChatState {
  sessions: SessionState[];
  activeId: string | null;
  input: string;
  sending: boolean;
  approval: PendingApproval | null;
  clarify: PendingClarify | null;
  showSettings: boolean;
  showTaskManager: boolean;
  showAgentModal: boolean;
  showAgentList: boolean;
  /** 模型管理器是否显示 */
  showModelManager: boolean;
  /** 通道管理器是否显示 */
  showChannelManager: boolean;
  /** 飞书网关 transcript 镜像：合并进右侧会话气泡（自动轮询更新） */
  feishuMirrorChatRows: ChatRow[];
  /** 飞书网关 transcript 镜像：合并进右侧「推理·工具」 */
  feishuMirrorProcessRows: ProcessRow[];
  /** 通道列表 */
  channels: ChannelInfo[];
  /** 模型列表 */
  models: ModelInfo[];
  /** 模型厂家列表（来自源码 PROVIDER_REGISTRY） */
  providers: ProviderInfo[];
  /** 技能列表（按 Agent 分组） */
  skills: AgentSkills[];
  /** 当前停靠面板显示的内容 */
  dockContent: 'agents' | 'tasks' | 'channels' | 'models' | 'skills' | 'memory' | null;
  /** 通道编辑弹窗是否显示 */
  showChannelModal: boolean;
  /** 当前编辑的通道 ID，为 null 表示新建 */
  editingChannelId: string | null;
  /** 模型编辑弹窗是否显示 */
  showModelModal: boolean;
  /** 当前编辑的模型 ID，为 null 表示新建 */
  editingModelId: string | null;
  /** 技能管理器是否显示 */
  showSkillManager: boolean;
  /** 记忆管理器是否显示 */
  showMemoryManager: boolean;
  editingAgentId: string | null;
  agents: AgentInfo[];
  initialized: boolean;
  attachments: Attachment[];
  wsConnected: boolean;
  /** key = agentId，驱动场景中人物头顶推理/工具气泡 */
  agentSceneInfer: Record<string, AgentSceneInferState>;
  /** 左栏规划时间线：用户确认「开始」后的步骤状态 */
  planTimelineRun: PlanTimelineRunState | null;
  /** 按 agentId 缓存的该 Agent 最新（主导+参与）规划，含 steps，执行状态取 DB。*/
  agentLastPlan: Record<string, {
    artifact: PlanArtifact;
    anchorTs: number;
    participation: 'led' | 'participated';
    dbPlan: { status: string; steps: Array<{ stepIndex: number; stepStatus: string; executor?: string; sessionId?: string; completedAt?: number }> } | null;
  }>;
  /** 任务列表：从数据库加载的全部历史规划 */
  taskListPlans: PlanSummary[];
  /** 递增以丢弃过期的「按 Agent 拉取任务列表」请求结果（如清空全部后仍在飞的 fetch） */
  taskListLoadEpoch: number;
  /** 底部任务列表中选中的规划 id；左侧时间线改为展示该条（null 则展示当前会话 Agent 的最新规划） */
  leftPanelTaskPlanId: number | null;
  /** 推理完成后的结果弹窗：显示完整推理文本，超过 50 字自动触发 */
  reasoningResultModal: { agentId: string; text: string } | null;

  // Actions
  setActiveId: (id: string | null) => void;
  setInput: (input: string) => void;
  setSending: (sending: boolean) => void;
  setApproval: (approval: PendingApproval | null) => void;
  setClarify: (clarify: PendingClarify | null) => void;
  setShowSettings: (show: boolean) => void;
  setShowTaskManager: (show: boolean) => void;
  setShowAgentModal: (show: boolean) => void;
  setShowAgentList: (show: boolean) => void;
  setShowChannelManager: (show: boolean) => void;
  setFeishuMirror: (chat: ChatRow[], process: ProcessRow[]) => void;
  setShowModelManager: (show: boolean) => void;
  setShowSkillManager: (show: boolean) => void;
  setShowMemoryManager: (show: boolean) => void;
  setChannels: (channels: ChannelInfo[]) => void;
  setModels: (models: ModelInfo[]) => void;
  setProviders: (providers: import('../types').ProviderInfo[]) => void;
  setSkills: (skills: AgentSkills[]) => void;
  setShowChannelModal: (show: boolean, editingId?: string | null) => void;
  setEditingChannelId: (id: string | null) => void;
  setShowModelModal: (show: boolean, editingId?: string | null) => void;
  setEditingModelId: (id: string | null) => void;
  setEditingAgentId: (id: string | null) => void;
  setAgents: (agents: AgentInfo[]) => void;
  removeAgent: (agentId: string) => void;
  removePlan: (planId: number) => void;
  setInitialized: (init: boolean) => void;
  setAttachments: (attachments: Attachment[]) => void;
  addAttachment: (attachment: Attachment) => void;
  removeAttachment: (index: number) => void;
  setWsConnected: (connected: boolean) => void;
  setSessions: (fn: (sessions: SessionState[]) => SessionState[]) => void;

  // Session actions
  patchSession: (sid: string, fn: (s: SessionState) => SessionState) => void;
  appendMessage: (sid: string, row: ChatRow) => void;
  appendProcessRow: (sid: string, row: ProcessRow) => void;
  addSession: (session: SessionState) => void;
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
  /** 追加推理 delta 到 processRows（如果最后一行是推理行则追加，否则创建新行） */
  appendReasoningDelta: (sid: string, text: string) => void;
  /** 标记最后一个推理行为完成 */
  finalizeReasoning: (sid: string) => void;
  // Infer state methods (merged from inferStore)
  patchAgentSceneInfer: (agentId: string, patch: Partial<AgentSceneInferState>) => void;
  clearAgentSceneInfer: (agentId: string) => void;
  setInferState: (
    agentId: string,
    phase: string,
    stateInfo: { phase?: string; message?: string } | null,
  ) => void;
  appendReasoning: (agentId: string, text: string) => void;
  setPlanTimelineRun: (run: PlanTimelineRunState | null) => void;
  ensurePlanTimelineRunValid: () => void;
  setAgentLastPlan: (
    agentId: string,
    plan: {
      artifact: PlanArtifact;
      anchorTs: number;
      participation: 'led' | 'participated';
      dbPlan: { status: string; steps: Array<{ stepIndex: number; stepStatus: string; executor?: string; sessionId?: string; completedAt?: number }> } | null;
    } | null,
  ) => void;
  setTaskListPlans: (plans: PlanSummary[]) => void;
  clearAgentLastPlans: () => void;
  bumpTaskListLoadEpoch: () => void;
  /** 数据库已删光任务后：递增 epoch、清空列表与 agentLastPlan */
  clearTaskListCacheAfterDbPurge: () => void;
  setLeftPanelTaskPlanId: (planId: number | null) => void;
  /** 删除单个任务规划（别名，与 removePlan 相同） */
  deleteTaskPlan: (planId: number) => void;
  /** 清空所有任务（别名） */
  clearAllTasks: () => void;
  /** 显示/隐藏推理结果弹窗 */
  setReasoningResultModal: (data: { agentId: string; text: string } | null) => void;
}

/**
 * 仅当与 ``updateUI``（左右栏 DOM）相关的数据变化时为 true。
 * 避免流式更新触发整页清空 DOM、卡死主线程并拖垮 Phaser 渲染。
 */
export function chatStoreDomRelevantChanged(prev: ChatState, next: ChatState): boolean {
  return (
    prev.sessions !== next.sessions ||
    prev.activeId !== next.activeId ||
    prev.input !== next.input ||
    prev.sending !== next.sending ||
    prev.approval !== next.approval ||
    prev.clarify !== next.clarify ||
    prev.showSettings !== next.showSettings ||
    prev.showTaskManager !== next.showTaskManager ||
    prev.showAgentList !== next.showAgentList ||
    prev.showModelManager !== next.showModelManager ||
    prev.showSkillManager !== next.showSkillManager ||
    prev.showMemoryManager !== next.showMemoryManager ||
    prev.showChannelManager !== next.showChannelManager ||
    prev.feishuMirrorChatRows !== next.feishuMirrorChatRows ||
    prev.feishuMirrorProcessRows !== next.feishuMirrorProcessRows ||
    prev.channels !== next.channels ||
    prev.models !== next.models ||
    prev.skills !== next.skills ||
    prev.showChannelModal !== next.showChannelModal ||
    prev.editingChannelId !== next.editingChannelId ||
    prev.showModelModal !== next.showModelModal ||
    prev.editingModelId !== next.editingModelId ||
    prev.showAgentModal !== next.showAgentModal ||
    prev.editingAgentId !== next.editingAgentId ||
    prev.agents !== next.agents ||
    prev.initialized !== next.initialized ||
    prev.attachments !== next.attachments ||
    prev.wsConnected !== next.wsConnected ||
    prev.planTimelineRun !== next.planTimelineRun ||
    prev.agentLastPlan !== next.agentLastPlan ||
    prev.taskListPlans !== next.taskListPlans ||
    prev.taskListLoadEpoch !== next.taskListLoadEpoch ||
    prev.leftPanelTaskPlanId !== next.leftPanelTaskPlanId
  );
}

export const useChatStore = create<ChatState>((set, get) => ({
  sessions: [],
  activeId: null,
  input: '',
  sending: false,
  approval: null,
  clarify: null,
  showSettings: false,
  showTaskManager: false,
  showAgentModal: false,
  showAgentList: false,
  showModelManager: false,
  showChannelManager: false,
  feishuMirrorChatRows: [],
  feishuMirrorProcessRows: [],
  channels: [],
  models: [],
  providers: [],
  skills: [],
  dockContent: null,
  showChannelModal: false,
  editingChannelId: null,
  showModelModal: false,
  editingModelId: null,
  showSkillManager: false,
  showMemoryManager: false,
  editingAgentId: null,
  agents: [],
  initialized: false,
  attachments: [],
  wsConnected: false,
  agentSceneInfer: {},
  planTimelineRun: null,
  agentLastPlan: {},
  taskListPlans: [],
  taskListLoadEpoch: 0,
  leftPanelTaskPlanId: null,
  reasoningResultModal: null,

  setActiveId: (id) => set({ activeId: id }),
  setInput: (input) => set({ input }),
  setSending: (sending) => set({ sending }),
  setApproval: (approval) => set({ approval }),
  setClarify: (clarify) => set({ clarify }),
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
  setShowChannelManager: (show) =>
    set({
      showChannelManager: show,
      showAgentList: false,
      showTaskManager: false,
      showModelManager: false,
      dockContent: show ? 'channels' : null,
    }),
  setFeishuMirror: (chat, process) =>
    set({ feishuMirrorChatRows: chat, feishuMirrorProcessRows: process }),
  setShowModelManager: (show) =>
    set({
      showModelManager: show,
      showAgentList: false,
      showTaskManager: false,
      showChannelManager: false,
      dockContent: show ? 'models' : null,
    }),
  setChannels: (channels) => set({ channels }),
  setModels: (models) => set({ models }),
  setProviders: (providers) => set({ providers }),
  setShowChannelModal: (show: boolean, editingId: string | null = null) =>
    set({ showChannelModal: show, editingChannelId: editingId }),
  setEditingChannelId: (id) => set({ editingChannelId: id }),
  setShowModelModal: (show: boolean, editingId: string | null = null) =>
    set({ showModelModal: show, editingModelId: editingId }),
  setEditingModelId: (id) => set({ editingModelId: id }),
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
  setSkills: (skills) => set({ skills }),
  setEditingAgentId: (id) => set({ editingAgentId: id }),
  setAgents: (agents) => set({ agents }),
  removeAgent: (agentId) => set((state) => ({
    agents: state.agents.filter((a) => a.agentId !== agentId),
  })),
  setInitialized: (init) => set({ initialized: init }),
  setAttachments: (attachments) => set({ attachments }),
  addAttachment: (attachment) => set((state) => ({ attachments: [...state.attachments, attachment] })),
  removeAttachment: (index) => set((state) => ({ attachments: state.attachments.filter((_, i) => i !== index) })),
  setWsConnected: (connected) => set({ wsConnected: connected }),

  patchSession: (sid, fn) => set((state) => ({
    sessions: state.sessions.map((s) => (s.id === sid ? fn(s) : s)),
  })),

  appendMessage: (sid, row) => set((state) => ({
    sessions: state.sessions.map((s) => (s.id === sid ? { ...s, messages: [...s.messages, row] } : s)),
  })),

  appendProcessRow: (sid, row) => set((state) => ({
    sessions: state.sessions.map((s) =>
      s.id === sid ? { ...s, processRows: [...s.processRows, row] } : s
    ),
  })),

  addSession: (session) => set((state) => ({
    sessions: [...state.sessions, { ...session, processRows: session.processRows ?? [] }],
  })),

  removeSession: (id) => set((state) => {
    const removed = state.sessions.find((s) => s.id === id);
    const next = state.sessions.filter((s) => s.id !== id);
    const nextInfer = { ...state.agentSceneInfer };
    if (removed) delete nextInfer[removed.agentId];
    const run = state.planTimelineRun;
    const nextRun = run?.sourceSessionId === id ? null : run;
    return {
      sessions: next,
      activeId: state.activeId === id ? (next[0]?.id ?? null) : state.activeId,
      agentSceneInfer: nextInfer,
      planTimelineRun: nextRun,
    };
  }),

  updateSessionTitle: (id, title) => set((state) => ({
    sessions: state.sessions.map((s) => (s.id === id ? { ...s, title } : s)),
  })),

  // --- SSE event handler methods ---

  appendChat: (sid, row) =>
    set((state) => {
      const exists = state.sessions.some((s) => s.id === sid);
      if (!exists) {
        // 创建新会话时，使用消息中的 agentId（来自 message.start 事件）
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
          const mediaUrls = Array.isArray(payload.media_urls)
            ? payload.media_urls as string[]
            : (last as { mediaUrls?: string[] }).mediaUrls;
          msgs[msgs.length - 1] = {
            ...last,
            streaming: false,
            thinking: typeof payload.thinking === 'string' ? payload.thinking : undefined,
            timestamp: last.timestamp ?? Date.now(),
            mediaUrls,
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

  appendToolCall: (sid, tc) =>
    set((state) => ({
      sessions: state.sessions.map((s) => {
        if (s.id !== sid) return s;
        const row: ProcessRow = {
          id: String((tc as Record<string, unknown>).id ?? `tool_${Date.now()}`),
          variant: 'tool',
          title: `🔧 ${String((tc as Record<string, unknown>).name ?? 'tool')}`,
          body: JSON.stringify((tc as Record<string, unknown>).input ?? {}, null, 2),
          toolCalls: [{
            id: String((tc as Record<string, unknown>).id ?? ''),
            name: String((tc as Record<string, unknown>).name ?? ''),
            input: ((tc as Record<string, unknown>).input ?? {}) as Record<string, unknown>,
            status: 'generating' as const,
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
        // 如果最后一行是正在流式的推理行，追加到其 body
        if (last && last.variant === 'reasoning' && last.streaming) {
          rows[rows.length - 1] = {
            ...last,
            body: last.body + text,
          };
        } else {
          // 否则创建新推理行
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

  setSessions: (fn) => set((state) => ({
    sessions: fn(state.sessions),
  })),

  // ── Infer state methods (merged from inferStore) ──

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

  setPlanTimelineRun: (run) => set({ planTimelineRun: run }),

  setAgentLastPlan: (agentId, plan) =>
    set((state) => {
      if (plan === null) {
        const next = { ...state.agentLastPlan };
        delete next[agentId];
        return { agentLastPlan: next };
      }
      return { agentLastPlan: { ...state.agentLastPlan, [agentId]: plan } };
    }),

  setTaskListPlans: (plans) => set({ taskListPlans: plans }),

  clearAgentLastPlans: () => set({ agentLastPlan: {} }),

  bumpTaskListLoadEpoch: () => set((s) => ({ taskListLoadEpoch: s.taskListLoadEpoch + 1 })),

  clearTaskListCacheAfterDbPurge: () =>
    set((s) => ({
      taskListLoadEpoch: s.taskListLoadEpoch + 1,
      taskListPlans: [],
      agentLastPlan: {},
      leftPanelTaskPlanId: null,
    })),

  setLeftPanelTaskPlanId: (planId) => set({ leftPanelTaskPlanId: planId }),

  setReasoningResultModal: (data) => set({ reasoningResultModal: data }),

  removePlan: (planId) =>
    set((state) => ({
      taskListPlans: state.taskListPlans.filter((p) => p.id !== planId),
      leftPanelTaskPlanId:
        state.leftPanelTaskPlanId === planId ? null : state.leftPanelTaskPlanId,
    })),

  /** 仅在时间线已失效时 `set`，避免无变更也触发 `set` → 订阅者 → updateUI → 栈溢出 */
  ensurePlanTimelineRunValid: () => {
    const state = get();
    const r = state.planTimelineRun;
    if (!r) return;
    if (!planMessageStillExists(state.sessions, r.planAnchorTs)) {
      set({ planTimelineRun: null });
      return;
    }
    const art = state.sessions
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

  deleteTaskPlan: (planId) =>
    set((state) => ({
      taskListPlans: state.taskListPlans.filter((p) => p.id !== planId),
      leftPanelTaskPlanId:
        state.leftPanelTaskPlanId === planId ? null : state.leftPanelTaskPlanId,
    })),

  clearAllTasks: () =>
    set((s) => ({
      taskListLoadEpoch: s.taskListLoadEpoch + 1,
      taskListPlans: [],
      agentLastPlan: {},
      leftPanelTaskPlanId: null,
    })),
}));
