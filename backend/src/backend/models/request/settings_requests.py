"""Settings 页面的所有 Pydantic Request/Response 模型（对应 Spring Boot DTO）。"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


# ── 基础子模型 ─────────────────────────────────────────────────────────────

class AuxiliarySubModel(BaseModel):
    """所有 auxiliary.* 子配置槽位的通用字段形状。"""
    provider: str = "auto"
    model: str = ""
    baseUrl: str = ""
    apiKey: str = ""
    timeout: int = 30
    extraBody: dict = {}


class BrowserCamofoxRequest(BaseModel):
    model_config = ConfigDict(extra="allow")
    managedPersistence: bool = False


class BedrockGuardrailRequest(BaseModel):
    model_config = ConfigDict(extra="allow")
    guardrailIdentifier: str = ""
    guardrailVersion: str = ""
    streamProcessingMode: str = "async"
    trace: str = "disabled"


class BedrockDiscoveryRequest(BaseModel):
    model_config = ConfigDict(extra="allow")
    enabled: bool = True
    providerFilter: list[str] = []
    refreshInterval: int = 3600


class WebsiteBlocklistRequest(BaseModel):
    model_config = ConfigDict(extra="allow")
    enabled: bool = False
    domains: list[str] = []
    sharedFiles: list[str] = []


# ── Request Models ─────────────────────────────────────────────────────────────

class ModelEntryRequest(BaseModel):
    model_config = ConfigDict(extra="allow")
    id: str = ""
    provider: str = ""
    name: str = ""
    apiKey: str = ""
    baseUrl: str = ""
    isDefault: bool = False


class AgentSettingsRequest(BaseModel):
    model_config = ConfigDict(extra="allow")
    maxTurns: int = 90
    gatewayTimeout: int = 1800
    apiMaxRetries: int = 3
    toolUseEnforcement: str = "auto"
    imageInputMode: str = "auto"


class TerminalSettingsRequest(BaseModel):
    model_config = ConfigDict(extra="allow")
    backend: str = "local"
    cwd: str = "."
    timeout: int = 180
    persistentShell: bool = True
    dockerImage: str = "nikolaik/python-nodejs:python3.11-nodejs20"
    containerCpu: int = 1
    containerMemory: int = 5120


class TTSSettingsRequest(BaseModel):
    model_config = ConfigDict(extra="allow")
    enabled: bool = False
    provider: str = "edge"
    edgeVoice: str = "en-US-AriaNeural"
    elevenlabsVoiceId: str = "pNInz6obpgDQGcFmaJgB"


class STTSettingsRequest(BaseModel):
    model_config = ConfigDict(extra="allow")
    enabled: bool = False
    provider: str = "local"
    model: str = "base"


class DisplaySettingsRequest(BaseModel):
    model_config = ConfigDict(extra="allow")
    personality: str = "balanced"
    compact: bool = False
    showReasoning: bool = True
    streaming: bool = True
    finalResponseMarkdown: str = "always"


class SecuritySettingsRequest(BaseModel):
    model_config = ConfigDict(extra="allow")
    allowPrivateUrls: bool = False
    redactSecrets: bool = False
    tirithEnabled: bool = True


class AuxiliaryVisionRequest(BaseModel):
    model_config = ConfigDict(extra="allow")
    provider: str = "auto"
    model: str = ""
    baseUrl: str = ""
    apiKey: str = ""
    timeout: int = 120
    extraBody: dict = {}
    downloadTimeout: int = 30


class AuxiliaryWebExtractRequest(BaseModel):
    model_config = ConfigDict(extra="allow")
    provider: str = "auto"
    model: str = ""
    baseUrl: str = ""
    apiKey: str = ""
    timeout: int = 360
    extraBody: dict = {}


class AuxiliaryCompressionRequest(BaseModel):
    model_config = ConfigDict(extra="allow")
    provider: str = "auto"
    model: str = ""
    baseUrl: str = ""
    apiKey: str = ""
    timeout: int = 120
    extraBody: dict = {}


class AuxiliarySessionSearchRequest(BaseModel):
    model_config = ConfigDict(extra="allow")
    provider: str = "auto"
    model: str = ""
    baseUrl: str = ""
    apiKey: str = ""
    timeout: int = 30
    extraBody: dict = {}
    maxConcurrency: int = 3


class AuxiliarySkillsHubRequest(BaseModel):
    model_config = ConfigDict(extra="allow")
    provider: str = "auto"
    model: str = ""
    baseUrl: str = ""
    apiKey: str = ""
    timeout: int = 30
    extraBody: dict = {}


class AuxiliaryApprovalRequest(BaseModel):
    model_config = ConfigDict(extra="allow")
    provider: str = "auto"
    model: str = ""
    baseUrl: str = ""
    apiKey: str = ""
    timeout: int = 30
    extraBody: dict = {}


class AuxiliaryMcpRequest(BaseModel):
    model_config = ConfigDict(extra="allow")
    provider: str = "auto"
    model: str = ""
    baseUrl: str = ""
    apiKey: str = ""
    timeout: int = 30
    extraBody: dict = {}


class AuxiliaryTitleGenerationRequest(BaseModel):
    model_config = ConfigDict(extra="allow")
    provider: str = "auto"
    model: str = ""
    baseUrl: str = ""
    apiKey: str = ""
    timeout: int = 30
    extraBody: dict = {}


class AuxiliaryCuratorRequest(BaseModel):
    model_config = ConfigDict(extra="allow")
    provider: str = "auto"
    model: str = ""
    baseUrl: str = ""
    apiKey: str = ""
    timeout: int = 600
    extraBody: dict = {}


class BrowserSettingsRequest(BaseModel):
    model_config = ConfigDict(extra="allow")
    inactivityTimeout: int = 120
    commandTimeout: int = 30
    recordSessions: bool = False
    allowPrivateUrls: bool = False
    autoLocalForPrivateUrls: bool = True
    cdpUrl: str = ""
    dialogPolicy: str = "must_respond"
    dialogTimeoutS: int = 300
    camofox: BrowserCamofoxRequest = BrowserCamofoxRequest()


class DelegationSettingsRequest(BaseModel):
    model_config = ConfigDict(extra="allow")
    model: str = ""
    provider: str = ""
    baseUrl: str = ""
    apiKey: str = ""
    inheritMcpToolsets: bool = True
    maxIterations: int = 50
    childTimeoutSeconds: int = 600
    reasoningEffort: str = ""
    maxConcurrentChildren: int = 3
    maxSpawnDepth: int = 1
    orchestratorEnabled: bool = True
    subagentAutoApprove: bool = False


class DiscordSettingsRequest(BaseModel):
    model_config = ConfigDict(extra="allow")
    requireMention: bool = True
    freeResponseChannels: str = ""
    allowedChannels: str = ""
    autoThread: bool = True
    reactions: bool = True
    channelPrompts: dict = {}
    serverActions: str = ""


class TelegramSettingsRequest(BaseModel):
    model_config = ConfigDict(extra="allow")
    reactions: bool = False
    channelPrompts: dict = {}


class SlackSettingsRequest(BaseModel):
    model_config = ConfigDict(extra="allow")
    channelPrompts: dict = {}


class MattermostSettingsRequest(BaseModel):
    model_config = ConfigDict(extra="allow")
    channelPrompts: dict = {}


class SessionsSettingsRequest(BaseModel):
    model_config = ConfigDict(extra="allow")
    autoPrune: bool = False
    retentionDays: int = 90
    vacuumAfterPrune: bool = True
    minIntervalHours: int = 24


class LoggingSettingsRequest(BaseModel):
    model_config = ConfigDict(extra="allow")
    level: str = "INFO"
    maxSizeMb: int = 5
    backupCount: int = 3


class MemorySettingsRequest(BaseModel):
    model_config = ConfigDict(extra="allow")
    memoryEnabled: bool = True
    userProfileEnabled: bool = True
    memoryCharLimit: int = 2200
    userCharLimit: int = 1375
    provider: str = ""


class VoiceSettingsRequest(BaseModel):
    model_config = ConfigDict(extra="allow")
    recordKey: str = "ctrl+b"
    maxRecordingSeconds: int = 120
    autoTts: bool = False
    beepEnabled: bool = True
    silenceThreshold: int = 200
    silenceDuration: float = 3.0


class ContextSettingsRequest(BaseModel):
    model_config = ConfigDict(extra="allow")
    engine: str = "compressor"


class CheckpointsSettingsRequest(BaseModel):
    model_config = ConfigDict(extra="allow")
    enabled: bool = True
    maxSnapshots: int = 50
    autoPrune: bool = False
    retentionDays: int = 7
    deleteOrphans: bool = True
    minIntervalHours: int = 24


class CronSettingsRequest(BaseModel):
    model_config = ConfigDict(extra="allow")
    wrapResponse: bool = True
    maxParallelJobs: int | None = None


class SkillsSettingsRequest(BaseModel):
    model_config = ConfigDict(extra="allow")
    externalDirs: list[str] = []
    templateVars: bool = True
    inlineShell: bool = False
    inlineShellTimeout: int = 10
    guardAgentCreated: bool = False


class ApprovalsSettingsRequest(BaseModel):
    model_config = ConfigDict(extra="allow")
    mode: str = "manual"
    timeout: int = 60
    cronMode: str = "deny"
    mcpReloadConfirm: bool = True


class ModelCatalogSettingsRequest(BaseModel):
    model_config = ConfigDict(extra="allow")
    enabled: bool = True
    url: str = "https://hermes-agent.nousresearch.com/docs/api/model-catalog.json"
    ttlHours: int = 24
    providers: dict = {}


class NetworkSettingsRequest(BaseModel):
    model_config = ConfigDict(extra="allow")
    forceIpv4: bool = False


class ConfigStatusRequest(BaseModel):
    model_config = ConfigDict(extra="allow")
    configured: bool = False
    hasModel: bool = False
    hasApiKey: bool = False


class CommandAllowlistRequest(BaseModel):
    model_config = ConfigDict(extra="allow")
    commands: list[str] = []


class QuickCommandsRequest(BaseModel):
    model_config = ConfigDict(extra="allow")
    commands: dict = {}


class HooksRequest(BaseModel):
    model_config = ConfigDict(extra="allow")
    hooks: dict = {}
    hooksAutoAccept: bool = False


class PersonalitiesRequest(BaseModel):
    model_config = ConfigDict(extra="allow")
    personalities: dict = {}


class CodeExecutionRequest(BaseModel):
    model_config = ConfigDict(extra="allow")
    mode: str = "project"


class SessionResetRequest(BaseModel):
    model_config = ConfigDict(extra="allow")
    mode: str = "both"
    idleMinutes: int = 1440
    atHour: int = 4


class ToolOutputRequest(BaseModel):
    model_config = ConfigDict(extra="allow")
    maxBytes: int = 50000
    maxLines: int = 2000
    maxLineLength: int = 2000


class CompressionSettingsRequest(BaseModel):
    model_config = ConfigDict(extra="allow")
    enabled: bool = True
    threshold: float = 0.5
    targetRatio: float = 0.2
    protectLastN: int = 20
    hygieneHardMessageLimit: int = 400


class HumanDelaySettingsRequest(BaseModel):
    model_config = ConfigDict(extra="allow")
    mode: str = "off"
    minMs: int = 800
    maxMs: int = 2500


class DashboardSettingsRequest(BaseModel):
    model_config = ConfigDict(extra="allow")
    theme: str = "default"


class PrivacySettingsRequest(BaseModel):
    model_config = ConfigDict(extra="allow")
    redactPii: bool = False


class HonchoSettingsRequest(BaseModel):
    model_config = ConfigDict(extra="allow")
    honcho: dict = {}


class TimezoneSettingsRequest(BaseModel):
    model_config = ConfigDict(extra="allow")
    timezone: str = ""


class OnboardingSettingsRequest(BaseModel):
    model_config = ConfigDict(extra="allow")
    seen: dict = {}


class UpdatesSettingsRequest(BaseModel):
    model_config = ConfigDict(extra="allow")
    preUpdateBackup: bool = False
    backupKeep: int = 5


class BedrockSettingsRequest(BaseModel):
    model_config = ConfigDict(extra="allow")
    region: str = ""
    discovery: BedrockDiscoveryRequest = BedrockDiscoveryRequest()
    guardrail: BedrockGuardrailRequest = BedrockGuardrailRequest()


class OpenrouterSettingsRequest(BaseModel):
    model_config = ConfigDict(extra="allow")
    responseCache: bool = True
    responseCacheTtl: int = 300


class ToolLoopGuardrailsRequest(BaseModel):
    model_config = ConfigDict(extra="allow")
    warningsEnabled: bool = True
    hardStopEnabled: bool = False
    warnAfter: dict = {}
    hardStopAfter: dict = {}


class SecurityExtendedRequest(BaseModel):
    model_config = ConfigDict(extra="allow")
    allowPrivateUrls: bool = False
    redactSecrets: bool = False
    tirithEnabled: bool = True
    tirithPath: str = "tirith"
    tirithTimeout: int = 5
    tirithFailOpen: bool = True
    websiteBlocklist: WebsiteBlocklistRequest = WebsiteBlocklistRequest()


class FileReadMaxCharsRequest(BaseModel):
    model_config = ConfigDict(extra="allow")
    fileReadMaxChars: int = 100000


class PromptCachingRequest(BaseModel):
    model_config = ConfigDict(extra="allow")
    cacheTtl: int | str = "5m"


class ToolOutputSectionRequest(BaseModel):
    model_config = ConfigDict(extra="allow")
    maxBytes: int = 50000
    maxLines: int = 2000
    maxLineLength: int = 2000


class CheckpointsSectionRequest(BaseModel):
    model_config = ConfigDict(extra="allow")
    enabled: bool = True
    maxSnapshots: int = 50
    autoPrune: bool = False
    retentionDays: int = 7
    deleteOrphans: bool = True
    minIntervalHours: int = 24
    maxTotalSizeMb: int = 500
    maxFileSizeMb: int = 10


class DisplayExtendedRequest(BaseModel):
    model_config = ConfigDict(extra="allow")
    personality: str = "kawaii"
    compact: bool = False
    showReasoning: bool = False
    streaming: bool = False
    finalResponseMarkdown: str = "strip"
    resumeDisplay: str = "full"
    busyInputMode: str = "interrupt"
    tuiAutoResumeRecent: bool = False
    bellOnComplete: bool = False
    inlineDiffs: bool = True
    showCost: bool = False
    skin: str = "default"
    tuiStatusIndicator: str = "kaomoji"
    userMessagePreview: dict = {}
    interimAssistantMessages: bool = True
    toolProgressCommand: bool = False
    toolProgressOverrides: dict = {}
    toolPreviewLength: int = 0
    platforms: dict = {}
    runtimeFooter: dict = {}
    toolProgress: str = "all"
    language: str = "en"
    persistentOutput: bool = True
    persistentOutputMaxLines: int = 200
    ephemeralSystemTtl: int = 0
    copyShortcut: str = "auto"


class TTSExtendedRequest(BaseModel):
    model_config = ConfigDict(extra="allow")
    enabled: bool = True
    provider: str = "edge"
    edgeVoice: str = "en-US-AriaNeural"
    elevenlabsVoiceId: str = "pNInz6obpgDQGcFmaJgB"
    elevenlabsModelId: str = "eleven_multilingual_v2"
    openaiModel: str = "gpt-4o-mini-tts"
    openaiVoice: str = "alloy"
    xaiVoiceId: str = "eve"
    xaiLanguage: str = "en"
    xaiSampleRate: int = 24000
    xaiBitRate: int = 128000
    mistralModel: str = "voxtral-mini-tts-2603"
    mistralVoiceId: str = "c69964a6-ab8b-4f8a-9465-ec0925096ec8"
    neuttsRefAudio: str = ""
    neuttsRefText: str = ""
    neuttsModel: str = "neuphonic/neutts-air-q4-gguf"
    neuttsDevice: str = "cpu"
    piperVoice: str = "en_US-lessac-medium"


class STTExtendedRequest(BaseModel):
    model_config = ConfigDict(extra="allow")
    enabled: bool = True
    provider: str = "local"
    model: str = "base"
    language: str = ""
    openaiModel: str = "whisper-1"
    mistralModel: str = "voxtral-mini-latest"


# ── 完整保存请求模型 ─────────────────────────────────────────────────────────

class SettingsSaveRequest(BaseModel):
    """所有字段均为可选，支持部分保存；extra="allow" 接受前端任意额外字段。"""
    model_config = ConfigDict(extra="allow")
    models: list[ModelEntryRequest] = []
    agent: AgentSettingsRequest = AgentSettingsRequest()
    terminal: TerminalSettingsRequest = TerminalSettingsRequest()
    tts: TTSSettingsRequest = TTSSettingsRequest()
    stt: STTSettingsRequest = STTSettingsRequest()
    display: DisplaySettingsRequest = DisplaySettingsRequest()
    security: SecuritySettingsRequest = SecuritySettingsRequest()
    toolsets: list[str] = []
    auxiliaryVision: AuxiliaryVisionRequest | None = None
    auxiliaryWebExtract: AuxiliaryWebExtractRequest | None = None
    auxiliaryCompression: AuxiliaryCompressionRequest | None = None
    auxiliarySessionSearch: AuxiliarySessionSearchRequest | None = None
    auxiliarySkillsHub: AuxiliarySkillsHubRequest | None = None
    auxiliaryApproval: AuxiliaryApprovalRequest | None = None
    auxiliaryMcp: AuxiliaryMcpRequest | None = None
    auxiliaryTitleGeneration: AuxiliaryTitleGenerationRequest | None = None
    auxiliaryCurator: AuxiliaryCuratorRequest | None = None
    browser: BrowserSettingsRequest | None = None
    delegation: DelegationSettingsRequest | None = None
    discord: DiscordSettingsRequest | None = None
    telegram: TelegramSettingsRequest | None = None
    slack: SlackSettingsRequest | None = None
    mattermost: MattermostSettingsRequest | None = None
    sessions: SessionsSettingsRequest | None = None
    logging: LoggingSettingsRequest | None = None
    memory: MemorySettingsRequest | None = None
    voice: VoiceSettingsRequest | None = None
    context: ContextSettingsRequest | None = None
    checkpoints: CheckpointsSettingsRequest | None = None
    cron: CronSettingsRequest | None = None
    skills: SkillsSettingsRequest | None = None
    approvals: ApprovalsSettingsRequest | None = None
    modelCatalog: ModelCatalogSettingsRequest | None = None
    network: NetworkSettingsRequest | None = None
    commandAllowlist: list[str] | None = None
    quickCommands: dict | None = None
    hooks: HooksRequest | None = None
    personalities: dict | None = None
    codeExecution: CodeExecutionRequest | None = None
    sessionReset: SessionResetRequest | None = None
    toolOutput: ToolOutputRequest | None = None
    compression: CompressionSettingsRequest | None = None
    humanDelay: HumanDelaySettingsRequest | None = None
    dashboard: DashboardSettingsRequest | None = None
    privacy: PrivacySettingsRequest | None = None
    honcho: dict | None = None
    timezone: str = ""
    onboarding: OnboardingSettingsRequest | None = None
    updates: UpdatesSettingsRequest | None = None
    bedrock: BedrockSettingsRequest | None = None
    openrouter: OpenrouterSettingsRequest | None = None
    toolLoopGuardrails: ToolLoopGuardrailsRequest | None = None
    fileReadMaxChars: int | None = None
    promptCaching: PromptCachingRequest | None = None


class EnvVarUpdate(BaseModel):
    """更新（设置）环境变量的请求体。"""
    key: str = ""
    value: str = ""


class EnvVarDelete(BaseModel):
    """删除环境变量的请求体。"""
    key: str = ""
