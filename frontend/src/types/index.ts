// Shared types for HermesDigitalStudio

export interface Attachment {
  url: string;
  filename: string;
  contentType: string;
  size: number;
}

export interface ToolCall {
  id: string;
  name: string;
  input: Record<string, unknown>;
  progress?: string;
  result?: string;
  status: 'generating' | 'progress' | 'complete' | 'error';
}

/** 结构化规划（与后端注入的 JSON schema 一致，camelCase 为前端存储形式） */
export type PlanConfidence = 'high' | 'medium' | 'low';

export interface PlanStep {
  id: number;
  title: string;
  action: string;
  filePath?: string;
  confidence: PlanConfidence;
}

export interface PlanArtifact {
  name: string;
  planSummary: string;
  steps: PlanStep[];
  /** 规划该任务的 Agent ID（来自 plan_artifacts.agent_id） */
  plannerAgentId?: string;
}

/** 左栏时间线执行状态（用户「开始」后推进；与某条助手规划消息的 timestamp 对齐） */
export type PlanTimelineStepStatus = 'pending' | 'active' | 'done';

export interface PlanTimelineRunState {
  planAnchorTs: number;
  sourceSessionId: string;
  stepStatuses: PlanTimelineStepStatus[];
  /** 交付物汇总（从 plan_chain.complete 事件中提取） */
  deliverable?: {
    text: string;
    files: string[];
    dirs: string[];
  };
}

/** 下方 process panel 的条目：每轮推理或每个工具调用合并为一个气泡 */
export interface ProcessRow {
  id: string;
  /** 'reasoning' | 'tool' */
  variant: 'reasoning' | 'tool';
  /** 显示在气泡标题行，如 "🔧 mcp_code_explorer" 或 "⏳ 思考中" */
  title: string;
  /** 累积的正文（推理文本 或 工具输入/结果） */
  body: string;
  /** 仅 variant=tool 时使用 */
  toolCalls?: ToolCall[];
  streaming?: boolean;
  timestamp?: number;
}

export type ChatRow =
  | { role: 'user'; text: string; attachments?: Attachment[]; timestamp?: number; userName?: string; userAvatar?: string; status?: string; errorText?: string }
  | {
      role: 'assistant';
      text: string;
      streaming?: boolean;
      thinking?: string;
      toolCalls?: ToolCall[];
      timestamp?: number;
      /** 会话所属 Agent，用于气泡头像朝向与场景 `agentFacing` 一致 */
      agentId?: string;
      agentName?: string;
      agentAvatar?: string;
      /** 从回复中解析的结构化规划，用于左栏时间线 */
      planArtifact?: PlanArtifact;
      /** 去掉开头规划 JSON 后的正文，用于右侧气泡展示；``text`` 仍保留完整原文 */
      bodyText?: string;
      /** ComfyUI / TTS 工具生成的音频文件 URL 列表（.mp3 / .ogg） */
      mediaUrls?: string[];
      /** 标记此消息来自语音输入，用于控制"🔊 播放"按钮的显示 */
      fromVoice?: boolean;
      /** 附加元数据（如顶嘴标记、强度等） */
      metadata?: Record<string, unknown>;
    };

/** 子进程 ``message.complete`` / ``session.info`` 中的 usage，用于状态栏 */
export interface SessionUsageSnapshot {
  /** 本会话累计 tokens（与子进程 session_total_tokens 一致） */
  total: number;
  contextUsed?: number;
  /** 配置/模型对应的上下文窗口（与子进程 context_compressor.context_length 一致） */
  contextMax?: number;
  contextPercent?: number;
  /** 触发自动压缩的阈值百分比（与 context_compressor.threshold_percent 一致） */
  thresholdPercent?: number;
}

export interface SessionState {
  id: string;
  agentId: string;
  title: string;
  messages: ChatRow[];
  /** 推理过程 / 工具调用（ProcessRow[]，合并后每轮一个气泡） */
  processRows: ProcessRow[];
  streaming: boolean;
  unread: boolean;
  /** 当前 Agent 子进程回报的上次用量（按会话维度） */
  lastUsage?: SessionUsageSnapshot;
}

/** 办公室场景人物头顶状态气泡（对齐 HermesBungalow ``AgentInferenceState``） */
export interface AgentSceneInferState {
  phase: 'idle' | 'thinking' | 'tool' | 'done' | 'social' | 'small_thought';
  /** 推理流摘要，用于气泡正文 */
  thinkingSnippet: string;
  /** 工具名或进度摘要 */
  toolSnippet: string;
  /** 回合结束短摘（约 10 字） */
  doneSnippet: string;
  doneExpiresAt: number;
  /** 路过碰面时的寒暄文案 */
  socialSnippet: string;
  socialExpiresAt: number;
  /** 小心思短摘 */
  smallThoughtSnippet: string;
  smallThoughtExpiresAt: number;
}

export interface AgentInfo {
  agentId: string;
  profile: string;
  displayName: string;
  /** 后端启动时为该 Agent 登记的默认会话（用于引导与转发） */
  defaultSessionId?: string;
  avatar?: string;
  gender?: string;
  personality?: string;
  catchphrases?: string;
  memes?: string;
  /** SOUL.md 解析内容 - ## Identity */
  identity?: string;
  /** SOUL.md 解析内容 - ## Style */
  style?: string;
  /** SOUL.md 解析内容 - ### Defaults */
  defaults?: string;
  /** SOUL.md 解析内容 - ### Avoid */
  avoid?: string;
  /** SOUL.md 解析内容 - ### Core Truths */
  coreTruths?: string;
  /** 办公室场景像素坐标与朝向（SQLite）；无记录时为 null */
  officePose?: { x: number; y: number; facing: string } | null;
  alive: boolean;
  createdAt: number;
  /** 当前 Agent 使用的模型 ID（从 hermes_home/config.yaml 读取） */
  model?: string;
  modelProvider?: string;
  modelBaseUrl?: string;
}

export interface PendingApproval {
  sessionId: string;
  payload: Record<string, unknown>;
}

export interface PendingClarify {
  sessionId: string;
  requestId: string;
  question: string;
  choices: unknown;
}

export interface HermesEventParams {
  session_id?: string;
  type?: string;
  payload?: Record<string, unknown>;
}

/** 通道信息（对应 Hermes gateway PlatformConfig + channel_directory）
 *
 * Hermes 通道实际分两层:
 * - PlatformConfig: 每个 platform 的连接配置 (enabled, token, extra 等)
 * - channel_directory: 各平台已发现的 channel 列表 (id, name, guild, type 等)
 */
export interface ChannelInfo {
  /** channel_directory 中的 platform 原生 ID */
  id: string;
  /** 通道名称 */
  name: string;
  /** Hermes Platform 枚举值: telegram | discord | slack | webhook | ... */
  platform: string;
  /** 连接状态 */
  status: 'connected' | 'disconnected' | 'error';
  /** 状态为 error 时由后端附带的简要原因（如 gateway_state.json 的 exit_reason） */
  statusDetail?: string;
  /** 消息发往的默认 chat_id (home_channel.chat_id) */
  chatId?: string;
  /** 回复模式: off | first | all */
  replyToMode?: string;
  /** Bot Token */
  token?: string;
  /** 是否启用 */
  enabled?: boolean;
  /** 平台 extra 配置（部分平台有） */
  extra?: Record<string, unknown>;
  /** Discord 服务器名（仅 Discord） */
  guild?: string;
  /** 通道类型: channel | forum | dm | private */
  channelType?: string;
  /** 上次消息时间 */
  lastMessageAt?: number;
  /** 绑定的 Agent ID（为空表示使用默认 Agent） */
  agentId?: string;
}

/** 模型配置信息（对齐 backend settings.py 的 models 列表） */
export interface ModelInfo {
  /** 唯一标识: "main" 表示主模型，"fallback-{i}" 表示备用模型 */
  id: string;
  /** 显示名称（仅主模型有，用户自定义） */
  name?: string;
  /** 模型 ID（如 gpt-4o, claude-3-5-sonnet-20241022） */
  model: string;
  /** 模型提供商: openai | anthropic | google | ollama | groq | deepseek | ... */
  provider: string;
  /** 是否默认模型 */
  isDefault?: boolean;
  /** API Base URL（可选，自定义端点） */
  baseUrl?: string;
  /** API Key（来自环境变量，只读展示） */
  apiKey?: string;
}

/** 模型厂家信息（对齐 backend PROVIDER_REGISTRY） */
export interface ProviderInfo {
  id: string;
  name: string;
  inferenceBaseUrl?: string;
  authType?: string;
}

/** 技能配置信息（对齐 backend skills settings 的 external_dirs） */
export interface SkillInfo {
  /** 技能目录名（唯一标识） */
  id: string;
  /** 技能显示名称（来自 SKILL.md 的 name 字段） */
  name: string;
  /** 技能描述（来自 SKILL.md 的 description 字段） */
  description?: string;
  /** 技能目录完整路径 */
  path: string;
  /** 技能分类（父目录名） */
  category?: string;
  /** 版本号 */
  version?: string;
  /** 作者 */
  author?: string;
  /** 许可协议 */
  license?: string;
  /** 支持平台 */
  platforms?: string[];
  /** 前置命令 */
  commands?: string[];
  /** 标签 */
  tags?: string[];
}

/** 按 Agent 分组的技能数据 */
export interface AgentSkills {
  agentId: string;
  agentName: string;
  profile: string;
  skills: SkillInfo[];
}
