/**
 * 共享 API 类型定义
 */

// ─── 统一响应格式 ─────────────────────────────────────────────────────────

export interface FieldError {
  field: string;
  message: string;
}

// ─── Settings ───────────────────────────────────────────────────────────────

export interface SettingsResponse {
  configExists: boolean;
}

// ─── Agents ────────────────────────────────────────────────────────────────

export interface OfficePose {
  x: number;
  y: number;
  facing: string;
}

export interface AgentDetailResponse {
  ok: boolean;
  agent?: import('../types').AgentInfo;
}

/**
 * 后端 get_agent() 返回的是扁平 dict（非 { ok, agent } 包裹格式）。
 * 此类型已废弃，请直接使用 AgentInfo + fetch() / apiGetAgentRaw()。
 * @deprecated 后端返回扁平 dict，此类型匹配有误
 */

export interface CreateAgentResponse {
  ok: boolean;
  agent?: import('../types').AgentInfo;
}

export interface AgentCreateResult {
  ok: boolean;
  status: number;
  agentId?: string;
  detail?: string;
}

/** Agent 记忆体系完整数据（来自 GET /api/chat/agents/{agent_id}/memory） */
export interface AgentMemoryDetail {
  agentId: string;
  profile: string;
  displayName: string;
  avatar: string;
  gender: string;
  soulMd: {
    identity: string;
    style: string;
    defaults: string;
    avoid: string;
    coreTruths: string;
  };
  stateDb: {
    avatar: string;
    gender: string;
    personality: string;
    catchphrases: string;
    memes: string;
    officePose: { x: number; y: number; facing: string } | null;
    model: string;
    modelProvider: string;
    modelBaseUrl: string;
  };
  sessionHistory: {
    sessionId: string;
    sessionKey: string;
    createdAt: number;
    lastUsedAt: number;
    isActive: boolean;
    parentSessionId: string | null;
  }[];
  sessionTitles: {
    sessionKey: string;
    title: string | null;
    startedAt: number | null;
  }[];
  memoryProvider: Record<string, unknown>;
  skills: {
    id: string;
    name: string;
    description: string;
    path: string;
    category: string;
    version: string;
    author: string;
    license: string;
    platforms: string[];
    commands: string[];
    tags: string[];
  }[];
}

/** POST /api/chat/agents/{agent_id}/memory/summarize */
export interface MemorySummarizeResponse {
  summarized: boolean;
  summary?: string;
  sessionTitles: {
    sessionKey: string;
    title: string | null;
    startedAt: number | null;
  }[];
  error?: string;
}

/** GET /api/chat/agents/{agent_id}/memory/dual-stats — 双重记忆汇总统计 */
export interface DualMemoryStats {
  vectorMemory: {
    count: number;
    status: 'active' | 'empty' | 'unavailable';
  };
  knowledgeGraph: {
    nodeCount: number;
    edgeCount: number;
  };
  sessions: {
    sessionFileCount: number;
    activeSessionCount: number;
  };
}

/** 知识图谱节点 */
export interface KnowledgeGraphNode {
  id: number;
  label: string;
  type: string;
  summary: string;
  created_at: number;
  updated_at: number;
}

/** 知识图谱边 */
export interface KnowledgeGraphEdge {
  id: number;
  source_id: number;
  target_id: number;
  relation: string;
  evidence: string;
  source_label: string;
  target_label: string;
}

/** GET /api/chat/agents/{agent_id}/memory/knowledge-graph */
export interface KnowledgeGraphData {
  nodes: KnowledgeGraphNode[];
  edges: KnowledgeGraphEdge[];
  nodeCount: number;
  edgeCount: number;
}

/** GET /api/chat/agents/{agent_id}/memory/knowledge-graph/mermaid */
export interface KnowledgeGraphMermaid {
  mermaid: string;
  nodeCount: number;
  edgeCount: number;
}

/** GET /api/memory/agents/{agent_id}/search */
export interface VectorMemorySearchResponse {
  results: string[];
  count: number;
}

// ─── SelfModel ─────────────────────────────────────────────────────────────

/** GET /api/chat/agents/{agent_id}/self-model 返回的自我模型完整数据 */
export interface SelfModelData {
  agentId: string;
  version: number;
  updated_at: number;
  preferences: string;
  capabilities: string;
  behavioral_patterns: string;
  derived_traits: string;
  reflection_history: SelfModelReflectionEntry[];
}

/** 单条反思记录 */
export interface SelfModelReflectionEntry {
  timestamp: number;
  lesson: string;
  confidence: 'high' | 'medium' | 'low';
}

/** GET /api/chat/agents/{agent_id}/self-model/history */
export interface SelfModelHistoryResponse {
  agentId: string;
  history: SelfModelReflectionEntry[];
  totalCount: number;
}

/** POST /api/chat/agents/{agent_id}/self-model/reflect */
export interface SelfModelReflectResponse {
  triggered: boolean;
  message: string;
}

// ─── Sessions ──────────────────────────────────────────────────────────────

export interface SessionInfo {
  sessionId: string;
  displayName?: string;
}

export interface SessionListResponse {
  sessions: import('../types').SessionState[];
}

// ─── Chat / Prompt ─────────────────────────────────────────────────────────

export interface PromptPayload {
  sessionId: string;
  text: string;
  attachments?: unknown[];
}

export interface PromptResponse {
  ok: boolean;
  status?: number;
  detail?: string;
}

// ─── Orchestrated Run ─────────────────────────────────────────────────────

export interface OrchestratedRunPayload {
  sessionId: string;
  text: string;
  attachments?: unknown[];
  autoPeer?: boolean;
  completeTimeout?: number;
  cols?: number;
}

export interface OrchestratedRunResponse {
  ok: boolean;
}

// ─── Plan Chain ────────────────────────────────────────────────────────────

export interface PlanStep {
  id: number;
  title: string;
  action: string;
  filePath?: string;
}

// ─── Plans ────────────────────────────────────────────────────────────────

export interface PlanStepDb {
  stepIndex: number;
  stepId?: number;
  stepStatus: string;
  executor?: string;
  sessionId?: string;
  completedAt?: number;
  result?: string | null;
  title?: string;
  action?: string;
  filePath?: string;
}

export interface PlanArtifact {
  name: string;
  planSummary?: string;
  steps: PlanStep[];
  plannerAgentId?: string;
}

export interface PlanSummary {
  id?: number;
  sessionId: string;
  status: string;
  name: string;
  planSummary?: string;
  steps: PlanStepDb[];
  createdAt: number;
  participation: string;
  agentId?: string;
}

export interface PlansResponse {
  ok: boolean;
  plans: PlanSummary[];
}

export interface DeleteAllPlansResponse {
  ok: boolean;
  deletedArtifacts?: number;
  deletedSteps?: number;
}

export interface StepResultResponse {
  ok: boolean;
  result: { text: string } | null;
}

// ─── Upload ───────────────────────────────────────────────────────────────

export interface UploadResponse {
  ok: boolean;
  url?: string;
  filename?: string;
}

// ─── History ──────────────────────────────────────────────────────────────

/** 单条会话消息（来自 GET /api/chat/history/{session_id}） */
export interface HistoryMessage {
  role: string;
  text: string;
  reasoning?: string;
  reasoning_content?: string;
}

export interface HistoryResponse {
  messages: unknown[];
  processRows?: unknown[];
}

// ─── Models ───────────────────────────────────────────────────────────────

export interface ProbeProviderModelsResult {
  models: string[];
  probedUrl: string | null;
  resolvedBaseUrl: string;
  suggestedBaseUrl: string | null;
}

export interface ProviderEnvKeyResult {
  envVarName: string;
  envVarValue: string;
}

// ─── Skills ───────────────────────────────────────────────────────────────

export interface SkillsResponse {
  ok: boolean;
  agents: import('../types').AgentSkills[];
}

// ─── Channels ──────────────────────────────────────────────────────────────

export interface ChannelUpsertPayload {
  platform: string;
  name: string;
  chat_id: string;
  token: string;
  api_key?: string;
  enabled: boolean;
  reply_to_mode: string;
  extra?: Record<string, unknown>;
  agent_id?: string;
}

export interface ChannelPatchPayload {
  name?: string;
  chat_id?: string;
  token?: string;
  api_key?: string;
  enabled?: boolean;
  reply_to_mode?: string;
  extra?: Record<string, unknown>;
  agent_id?: string;
}

// ─── Feishu (飞书) ─────────────────────────────────────────────────────

export interface FeishuSessionRow {
  id: string;
  source?: string;
  user_id?: string | null;
  title?: string | null;
  preview?: string;
  message_count?: number;
  last_active?: number;
  started_at?: number;
  model?: string | null;
}

export interface FeishuSessionsResponse {
  ok: boolean;
  dbPath?: string;
  sessions: FeishuSessionRow[];
  hint?: string;
  error?: string;
}

export interface FeishuMessageRow {
  id?: number;
  role: string;
  content?: string | null;
  timestamp?: number;
  toolName?: string | null;
  tool_name?: string | null;
  tool_calls?: unknown;
  tool_call_id?: string | null;
  reasoning?: string | null;
  reasoning_content?: string | null;
}

export interface FeishuMessagesResponse {
  ok: boolean;
  sessionId?: string;
  resolvedSessionId?: string;
  messages: FeishuMessageRow[];
  error?: string;
  hint?: string;
}

// ─── Platform Gateway ────────────────────────────────────────────────────

export interface PlatformGatewayStatus {
  embeddedEnabled: boolean;
  embeddedAutoStart?: boolean;
  embeddedStudioPid: number | null;
  embeddedAlive: boolean;
  hermesGatewayPidFile: number | null;
}

// ─── Utility ─────────────────────────────────────────────────────────────

/** 解析 FastAPI 错误响应的 detail 字段 */
export function parseFastApiDetail(raw: Record<string, unknown>, status: number): string {
  const d = raw.detail;
  if (typeof d === 'string') return d;
  if (Array.isArray(d) && d.length > 0) {
    const first = d[0] as { msg?: string } | string | undefined;
    if (first && typeof first === 'object' && typeof first.msg === 'string') return first.msg;
    if (typeof first === 'string') return first;
  }
  return `HTTP ${status}`;
}

// ─── Energy ──────────────────────────────────────────────────────────────

export interface EnergyState {
  agent_id: string;
  satiety: number;
  bio_current: number;
  mode: 'normal' | 'power_save' | 'surge' | 'forced_discharge';
  updated_at: string;
}

export interface EnergyLogEntry {
  metric: 'satiety' | 'bio_current';
  reason: string;
  delta: number;
  value_before: number;
  value_after: number;
  timestamp: string;
}

export interface EnergyLogsResponse {
  logs: EnergyLogEntry[];
  totalCount: number;
}

export interface EnergyResetPayload {
  satiety: number;
  bio_current: number;
  mode: string;
}

// ─── Emotion ────────────────────────────────────────────────────────────

export interface EmotionState {
  agent_id: string;
  valence: number;    // -1 ~ 1
  arousal: number;    // -1 ~ 1
  dominance: number;  // -1 ~ 1
  updated_at: string;
}

export interface EmotionHistoryEntry {
  agent_id: string;
  valence: number;
  arousal: number;
  dominance: number;
  trigger: string;
  timestamp: string;
}

// ─── Memory Scoring ─────────────────────────────────────────────────────

export interface ScoringCandidate {
  memory_id: string;
  score: number;
  summary: string;
  source: string;
}

export interface ScoringCandidatesResponse {
  totalMemories: number;
  maxEntries: number;
  candidates: ScoringCandidate[];
}

export interface PruneResponse {
  deletedCount: number;
  requestedCount: number;
}

/** GET /api/chat/agents/{agent_id}/myelination/stats — 髓鞘化引擎统计 */
export interface MyelinationStats {
  total_paths: number;
  by_stage: {
    novel: number;
    learning: number;
    consolidating: number;
    instinct: number;
  };
  cache_entry_count: number;
  llm_calls_saved: number;
  tokens_saved: number;
}

/** GET /api/chat/model/cost/stats — 全局模型调用成本统计 */
export interface GlobalCostStats {
  total_calls: number;
  by_tier: Record<string, number>;
  by_provider: Record<string, number>;
  total_tokens: number;
  estimated_cost: number;
  period_days: number;
}
