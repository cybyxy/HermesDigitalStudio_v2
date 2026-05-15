# HermesDigitalStudio v2 — 详细设计文档

> **文档类型**: 详细设计文档 (Detailed Design Document)
> **版本**: v1.0
> **日期**: 2026-05-14
> **关联文档**:
> - [系统设计文档](./hermes-v2-system-design.md)（架构总览）
> - [产品需求文档 (PRD)](./hermes-v2-prd.md)（功能需求详述）
> - [AI Agent 架构升级报告](./hermes-v2-agent-upgrade-report.md)（差距分析）

---

## 一、类与模块设计

### 1.1 新增模块：能量管理系统

#### `EnergyService` — `backend/src/backend/services/energy.py`

```python
class EnergyService:
    """双维度能量管理：饱食度 (Satiety) + 生物电流 (BioCurrent)"""

    # ---- 配置常量 ----
    SATIETY_MAX: int = 100
    SATIETY_MIN: int = 0
    SATIETY_DEFAULT: int = 80
    SATIETY_LOW_THRESHOLD: int = 30      # 进入节能模式
    SATIETY_CRITICAL: int = 10            # 极度饥饿

    BIO_CURRENT_MAX: int = 10
    BIO_CURRENT_MIN: int = 0
    BIO_CURRENT_DEFAULT: int = 3
    BIO_CURRENT_SURGE: int = 8            # 电涌阈值
    BIO_CURRENT_FORCE_DISCHARGE: int = 10  # 强制放电
    BIO_CURRENT_DECAY_RATE: float = 1.0   # 每分钟回落

    BASE_SATIETY_DECAY_PER_HOUR: float = 5.0
    BASE_SATIETY_DECAY_PER_INFERENCE: float = 0.5

    # 热度-饱食度消耗倍率
    CURRENT_CONSUMPTION_MULTIPLIER: dict = {
        (0, 3): 1.0,
        (4, 6): 1.5,
        (7, 8): 2.0,
        (9, 10): 3.0,
    }

    # ---- 公开方法 ----
    def __init__(self, config: StudioConfig):
        """初始化，加载所有 Agent 的能量状态。"""

    async def get_energy(self, agent_id: str) -> EnergyState:
        """获取 Agent 当前能量状态。
        返回: {agent_id, satiety, bio_current, mode, updated_at}
        """

    async def update_satiety(self, agent_id: str, delta: float, reason: str) -> EnergyState:
        """更新饱食度（正数增加，负数减少）。
        - 叠加 bio_current 消耗倍率
        - 触发阈值检查 (mode 切换)
        - 写入 energy_log
        """

    async def update_bio_current(self, agent_id: str, delta: float, reason: str) -> EnergyState:
        """更新生物电流（正数增加，负数减少）。
        - 限制在 [0, 10] 范围
        - bio_current >= 10 触发强制放电
        - 写入 energy_log
        """

    async def reset_energy(self, agent_id: str, satiety: int,
                           bio_current: int, mode: str) -> EnergyState:
        """管理员重置能量状态。"""

    async def get_energy_logs(self, agent_id: str, limit: int = 50) -> list[EnergyLogEntry]:
        """查询能量变化日志。"""

    async def apply_idle_decay(self, agent_id: str, hours: float) -> EnergyState:
        """空闲衰减：satiety -= BASE * hours * current_multiplier"""

    async def apply_inference_cost(self, agent_id: str) -> EnergyState:
        """推理消耗：satiety -= BASE_PER_INFERENCE * current_multiplier;
           bio_current += 0.2"""

    async def apply_task_submit(self, agent_id: str, complexity: str) -> EnergyState:
        """任务提交：根据复杂度增加 bio_current (medium +5, large +8)"""

    async def apply_positive_interaction(self, agent_id: str,
                                         interaction_type: str) -> EnergyState:
        """正向交互恢复：task_complete +15, user_praise +10, encourage +5"""

    async def check_thresholds(self, agent_id: str) -> EnergyState:
        """检查阈值并触发模式切换：
        - satiety < 30 → mode=power_save (拒绝新任务)
        - bio_current > 8 → mode=surge
        - bio_current >= 10 → mode=forced_discharge, bio_current→5
        """

    async def decay_bio_current_loop(self) -> None:
        """后台循环：每分钟对所有 Agent 执行 bio_current 回落。"""

    async def start(self) -> None:
        """启动后台回落循环。"""

    async def stop(self) -> None:
        """停止后台循环。"""


@dataclass
class EnergyState:
    agent_id: str
    satiety: int           # 0-100
    bio_current: int       # 0-10
    mode: str              # 'normal' | 'power_save' | 'surge' | 'forced_discharge'
    updated_at: str

@dataclass
class EnergyLogEntry:
    metric: str            # 'satiety' | 'bio_current'
    reason: str            # 'task_completed' | 'user_praise' | 'idle_tick' 等
    delta: float
    value_before: int
    value_after: int
    timestamp: str
```

#### `EnergyDAO` — `backend/src/backend/db/energy.py`

```python
class EnergyDAO(Repository):
    def get_energy(self, agent_id: str) -> Optional[sqlite3.Row]:
        """SELECT * FROM agent_energy WHERE agent_id = ?"""

    def upsert_energy(self, agent_id: str, satiety: int,
                      bio_current: int, mode: str) -> None:
        """INSERT OR REPLACE INTO agent_energy ..."""

    def insert_log(self, agent_id: str, metric: str, reason: str,
                   delta: float, value_before: int, value_after: int) -> None:
        """INSERT INTO agent_energy_log ..."""

    def get_logs(self, agent_id: str, limit: int) -> list[sqlite3.Row]:
        """SELECT * FROM agent_energy_log WHERE agent_id = ? ORDER BY timestamp DESC LIMIT ?"""

    def get_all_agent_ids(self) -> list[str]:
        """SELECT agent_id FROM agent_energy"""
```

---

### 1.2 新增模块：情绪引擎

#### `EmotionEngine` — `backend/src/backend/services/emotion.py`

```python
class EmotionEngine:
    """PAD 三维情绪模型：Valence (愉悦度) / Arousal (唤醒度) / Dominance (支配度)"""

    # 情绪更新规则
    UPDATE_RULES: ClassVar[dict] = {
        'user_praise':     (+0.10, +0.05, -0.05),
        'user_criticism':  (-0.10, +0.10, +0.05),
        'complex_task':    ( 0.00, +0.15, -0.10),
        'task_complete':   (+0.05, -0.05, +0.10),
        'repeated_reject': (-0.05, -0.05, +0.10),
        'time_decay':      (-0.01, -0.01, -0.01),   # 每小时向 0 回归
    }

    def __init__(self, config: StudioConfig): ...

    async def get_emotion(self, agent_id: str) -> EmotionState:
        """获取当前情绪状态。"""

    async def update_emotion(self, agent_id: str, trigger: str) -> EmotionState:
        """根据触发事件更新情绪三维度。
        - 应用 UPDATE_RULES[trigger]
        - 限制在 [-1, 1] 范围
        - 写入 emotion_log
        """

    async def get_emotion_context_block(self, agent_id: str) -> str:
        """返回注入 <memory-context> 的情绪提示块：
        【当前情绪】愉悦度: 0.7 唤醒度: 0.3 支配度: 0.5
        """

    async def get_timeline(self, agent_id: str,
                           limit: int = 50) -> list[EmotionLogEntry]:
        """查询情绪变化时间线。"""

    async def apply_time_decay(self, agent_id: str, hours: float) -> None:
        """时间衰减：所有维度向 0 回归。"""

    async def start(self) -> None: ...
    async def stop(self) -> None: ...


@dataclass
class EmotionState:
    agent_id: str
    valence: float       # -1 ~ 1
    arousal: float       # -1 ~ 1
    dominance: float     # -1 ~ 1
    updated_at: str

@dataclass
class EmotionLogEntry:
    valence: float
    arousal: float
    dominance: float
    trigger: str         # 'user_praise' | 'user_criticism' | 'complex_task' | ...
    timestamp: str
```

---

### 1.3 新增模块：心跳预判过滤器

#### `HeartbeatPrefilter` — `backend/src/backend/services/heartbeat_prefilter.py`

```python
class HeartbeatPrefilter:
    """轻量级预判过滤器：在 LLM 推理前评估 Neo4j 游走节点的信息价值"""

    def __init__(self, config: StudioConfig):
        self.entropy_threshold: float = 0.3     # 信息熵阈值
        self.novelty_threshold: float = 0.2     # 新颖度阈值

    def calculate_entropy(self, walked_nodes: list[dict]) -> float:
        """计算游走节点的信息熵：
        - 统计节点类型分布
        - 计算香农熵 normalized to [0, 1]
        """

    def calculate_novelty(self, walked_nodes: list[dict],
                          recent_nodes: list[str]) -> float:
        """计算新颖度：
        - 游走节点中有多少比例未在最近 N 分钟内出现过
        - 返回 [0, 1]
        """

    def should_invoke_llm(self, walked_nodes: list[dict],
                          recent_node_ids: list[str]) -> tuple[bool, str]:
        """核心判定方法：
        - 信息熵 < threshold OR 新颖度 < threshold → skip
        - 否则 → invoke LLM
        返回: (should_invoke: bool, skip_reason: str)
        """

    async def record_skip(self, agent_id: str, reason: str,
                          node_ids: list[str]) -> None:
        """记录被跳过的游走，用于校准阈值。"""

    async def get_skip_stats(self, agent_id: str) -> dict:
        """返回预判统计：总检查次数、跳过次数、跳过率。"""
```

---

### 1.4 新增模块：髓鞘化引擎

#### `MyelinationEngine` — `backend/src/backend/services/myelination.py`

```python
class MyelinationEngine:
    """三阶段状态机：Learning → Consolidating → Instinct"""

    STAGE_THRESHOLDS: ClassVar[dict] = {
        'learning_to_consolidating': 2,    # >= 2 次 access 进入固化
        'consolidating_to_instinct': 4,    # >= 4 次 access 进入本能
        'instinct_downgrade_days': 7,      # 7 天无访问降级
        'cache_hit_rate_threshold': 0.9,   # 命中率 > 90% 保留
    }

    def __init__(self, config: StudioConfig): ...

    async def get_path_stage(self, agent_id: str,
                             query_embedding: list[float]) -> str:
        """查询知识路径当前阶段。"""

    async def record_access(self, agent_id: str, query_embedding: list[float],
                            query_text: str) -> str:
        """记录一次访问：total_access++, access_7d++, last_access 更新。
        根据 access 次数自动推进阶段。
        """

    async def get_cache(self, agent_id: str,
                        query_embedding: list[float]) -> Optional[str]:
        """获取 instinct 阶段的缓存答案。
        - 仅 stage='instinct' 时返回
        - 检查 TTL (24h)
        """

    async def set_cache(self, agent_id: str, query_embedding: list[float],
                        answer: str) -> None:
        """设置缓存答案。"""

    async def invalidate_cache(self, agent_id: str,
                               related_topics: list[str]) -> None:
        """知识更新时主动失效相关缓存。"""

    async def run_maintenance(self, agent_id: str) -> None:
        """维护循环：
        - 检查 instinct 路径的 7 天无访问 → 降级
        - 检查缓存命中率 < 50% → 降级回 learning
        """

    async def get_stats(self, agent_id: str) -> MyelinationStats:
        """获取统计：总路径数、三阶段分布、节省 LLM 调用数、节省 token 数"""

    async def generate_path_description(self, agent_id: str,
                                        path_id: str) -> str:
        """生成人类可读的路径描述。"""


@dataclass
class MyelinationStats:
    total_paths: int
    learning_count: int
    consolidating_count: int
    instinct_count: int
    llm_calls_saved: int
    tokens_saved: int
```

---

### 1.5 新增模块：记忆评分引擎

#### `MemoryScoringEngine` — `backend/src/backend/services/memory_scoring.py`

```python
class MemoryScoringEngine:
    """四维度加权记忆评分"""

    DEFAULT_WEIGHTS: ClassVar[dict] = {
        'recency': 0.3,
        'reinforcement': 0.3,
        'source': 0.2,
        'access_count': 0.2,
    }

    def __init__(self, weights: Optional[dict] = None):
        self.weights = weights or self.DEFAULT_WEIGHTS

    def calculate_score(self, memory_entry: dict) -> float:
        """计算单条记忆的重要性分数：
        score = w_r × recency_norm + w_f × reinforcement_norm
              + w_s × source_norm + w_a × access_count_norm

        各维度归一化到 [0, 1]：
        - recency: 基于 created_at 的指数衰减
        - reinforcement: min(reinforcement_count / 10, 1.0)
        - source: LLM抽取=1.0, 用户显式=0.9, 对话提取=0.5, 启动恢复=0.3
        - access_count: log(access_count + 1) / log(max_access + 2)
        """

    async def rank_memories(self, agent_id: str) -> list[tuple[str, float]]:
        """返回按分数降序排列的记忆 ID 列表。"""

    async def get_candidates_for_pruning(self, agent_id: str, limit: int,
                                          max_entries: int = 200) -> list[str]:
        """返回建议淘汰的记忆 ID 列表（分数最低的 N 条）。"""

    async def detect_conflicts(self, agent_id: str, new_memory_text: str,
                                existing_memories: list[dict],
                                similarity_threshold: float = 0.85) -> Optional[ConflictResult]:
        """检测新旧记忆矛盾：
        1. 向量相似度检索 > 0.85 的已有记忆
        2. LLM 判断是否矛盾
        3. 矛盾时标记 conflict_with 字段
        """


@dataclass
class ConflictResult:
    existing_memory_id: str
    existing_text: str
    new_text: str
    conflict_reason: str  # LLM 判断的矛盾原因
```

---

### 1.6 新增模块：模型路由器

#### `ModelRouter` — `backend/src/backend/services/model_router.py`

```python
class ModelRouter:
    """多模型智能路由决策引擎"""

    PRIVACY_KEYWORDS: ClassVar[set[str]] = {
        '密码', '密钥', '身份证', '手机号', '银行卡', '私钥', 'token',
        'password', 'secret', 'credential', 'private key'
    }

    COMPLEXITY_KEYWORDS: ClassVar[set[str]] = {
        '分析', '设计', '评估', '解释', '总结', '优化', '重构',
        'analyze', 'design', 'evaluate', 'explain', 'optimize'
    }

    def __init__(self, config: StudioConfig): ...

    def assess_complexity(self, text: str,
                          context_length: int) -> ComplexityScore:
        """任务复杂度评估：
        - 计算输入长度、上下文深度
        - 检测复杂度关键词
        - 返回 complexity_score: float [0, 1] + reasoning: str
        """

    def has_privacy_sensitive_content(self, text: str) -> bool:
        """检测是否包含隐私敏感关键词。"""

    async def route(self, agent_id: str, text: str,
                    context_length: int) -> RoutingDecision:
        """路由决策主方法：
        1. 隐私关键词命中 → force local
        2. agent preferred_tier = local → local
        3. agent preferred_tier = cloud → cloud (if online)
        4. complexity > threshold → cloud
        5. 成本预算耗尽 → local
        6. 断网 → fallback local
        返回: {selected_tier, reason, fallback}
        """

    async def get_routing_stats(self, agent_id: str,
                                period_days: int = 7) -> RoutingStats:
        """路由统计：local/cloud 调用次数、token 消耗、费用估算。"""


@dataclass
class ComplexityScore:
    score: float        # 0.0 ~ 1.0
    reasoning: str      # 打分原因

@dataclass
class RoutingDecision:
    selected_tier: str  # 'local' | 'cloud'
    reason: str         # 路由原因
    fallback: bool      # 是否已降级

@dataclass
class RoutingStats:
    local_calls: int
    cloud_calls: int
    local_tokens: int
    cloud_tokens: int
    estimated_cost: float
```

---

### 1.7 新增模块：个性化交互

#### `InternalThoughtsService` — `backend/src/backend/services/internal_thoughts.py`

```python
class InternalThoughtsService:
    """小心思生成器：空闲时基于历史行为产生主动性推测"""

    TRIGGER_CONDITIONS: ClassVar[dict] = {
        'satiety_range': (40, 70),    # 饱食度在此区间时触发
        'trigger_probability': 0.3,   # 触发概率
        'min_confidence': 0.5,        # 最小置信度
    }

    def __init__(self, config: StudioConfig): ...

    async def should_generate(self, agent_id: str) -> bool:
        """判断是否应该生成小心思：
        - satiety 在 40-70 区间
        - 随机概率 < 0.3
        """

    async def generate(self, agent_id: str) -> Optional[SmallThought]:
        """生成小心思：
        1. 获取最近 10 条消息 + 用户画像
        2. 轻量级 LLM 生成 1-2 句推测
        3. 置信度过滤
        4. 非负面 + 非重复 → 推送
        """

    async def evaluate_quality(self, thought: str,
                               recent_thoughts: list[str]) -> tuple[bool, float]:
        """评估小心思质量：
        - 相关性置信度
        - 非负面检测
        - 非重复检测
        """


@dataclass
class SmallThought:
    content: str
    confidence: float
    timestamp: str
```

#### `BacktalkEngine` — `backend/src/backend/services/backtalk.py`

```python
class BacktalkEngine:
    """顶嘴引擎：检测触发条件 + 生成分层回复策略"""

    INTENSITY_LEVELS: ClassVar[dict] = {
        0: 'silent',       # 闭嘴不顶嘴
        1: 'gentle',       # 温和提醒
        2: 'humorous',     # 幽默吐槽
        3: 'direct',       # 直率反驳
    }

    TRIGGER_TYPES: ClassVar[list[str]] = [
        'unreasonable_request',   # 不合理请求
        'repeated_mistake',       # 重复错误 >= 3 次
        'different_opinion',      # 知识矛盾
    ]

    def __init__(self, config: StudioConfig): ...

    async def detect_triggers(self, agent_id: str, user_message: str,
                              context: list[dict]) -> list[TriggerResult]:
        """检测触发条件：
        1. LLM 判断请求是否不合理
        2. 检查最近对话中是否有 >= 3 次相同错误模式
        3. 检查 Agent 知识与用户陈述是否矛盾
        """

    async def generate_response(self, agent_id: str, trigger: TriggerResult,
                                intensity: int) -> Optional[str]:
        """生成顶嘴回复：
        - intensity=0: return None
        - intensity=1: "也许可以考虑..." 风格
        - intensity=2: "哈哈你又忘了..." 风格
        - intensity=3: "我不同意，因为..." 风格
        """

    async def run_personality_audit(self, agent_id: str) -> AuditResult:
        """人格一致性审计：每 50 轮对话执行一次。
        检查 Agent 回复是否与 personality 设定一致。
        """


@dataclass
class TriggerResult:
    trigger_type: str
    confidence: float
    evidence: str
    suggested_action: str

@dataclass
class AuditResult:
    is_consistent: bool
    inconsistencies: list[str]
    recommendations: list[str]
```

---

### 1.8 增强模块：心跳服务

#### `HeartbeatService`（增强）— `backend/src/backend/services/heartbeat.py`

```python
class HeartbeatService:
    """增强版心跳服务：集成预判过滤 + 能量联动 + 小心思推送"""

    def __init__(self, config: StudioConfig,
                 gateway_manager: GatewayManager,
                 neo4j_service: Neo4jService,
                 prefilter: HeartbeatPrefilter,
                 energy_service: EnergyService,
                 internal_thoughts: InternalThoughtsService): ...

    async def start(self) -> None:
        """启动心跳循环：
        - 周期 = get_heartbeat_interval_for_agent(agent_id)
        - 调度器：ScheduledTaskPool 管理每个 Agent 的定时任务
        """

    async def stop(self) -> None: ...

    async def _heartbeat_for_agent(self, agent_id: str) -> None:
        """核心心跳流程：
        1. 检查 Agent 是否空闲 (idle_timeout)
        2. 读取 satiety / bio_current
        3. Neo4j random_walk(agent_id, depth=bio_current)
           - depth 受边权重制约：每条边消耗 1/weight 单位电流
        4. prefilter.should_invoke_llm(walked_nodes)
           - 跳过 → 记录 heartbeat.skipped 日志
           - 通过 → 继续
        5. LLM 推理 (基于游走节点做深度联想)
        6. SSE 推送 → heartbeat.event
        7. 飞书/Telegram 消息发布 (如果通道启用)
        8. energy.apply_inference_cost(agent_id)
        9. 随机触发 internal_thoughts.generate()
           - 如果生成 → SSE 推送 heartbeat.small_thought
        """

    def get_heartbeat_interval_for_agent(self, agent_id: str) -> float:
        """饱食度联动频率计算：
        satiety < 30  → 90s
        satiety 30-60 → 60s
        satiety 60-80 → 30s
        satiety > 80  → 15s
        bio_current > 8 → 频率减半
        可通过 HERMES_HEARTBEAT_SATIETY_MAP 环境变量覆盖
        """
```

---

### 1.9 增强模块：Agent Chat Bridge

#### `submit_with_hint()`（增强）— `backend/src/backend/services/agent_chat_bridge.py`

```python
async def submit_with_hint(
    session_id: str,
    text: str,
    attachments: Optional[list[str]] = None,
    # --- 新增参数 ---
    energy_service: Optional[EnergyService] = None,
    emotion_engine: Optional[EmotionEngine] = None,
    backtalk_engine: Optional[BacktalkEngine] = None,
    myelination_engine: Optional[MyelinationEngine] = None,
    model_router: Optional[ModelRouter] = None,
) -> dict:
    """
    增强版提交函数流程：
    1. 能量检查：satiety < 30 → 返回 429 + mode=power_save
    2. 模型路由：model_router.route(agent_id, text, context_length)
    3. 情绪更新：emotion_engine.update_emotion(agent_id, trigger)
    4. 顶嘴检测：backtalk_engine.detect_triggers(...) → 注入 top-of-chat
    5. 髓鞘化缓存检查：myelination_engine.get_cache(...) → 命中直接返回
    6. 构建 <memory-context>：
       - personality_hint (来自 agent_personality)
       - peer_routing (联系人路由)
       - emotion_context (情绪提示块) [新增]
       - recent_session_summary
       - all_session_titles
       - vector_memories
       - knowledge_graph (深度=bio_current, 边权重制约) [增强]
       - compression_map
       - myelination_cache_hint (如果有缓存) [新增]
       - conversation_state
    7. GatewayManager.submit_prompt(session_id, text, attachments)
    8. 能量消耗：energy.apply_inference_cost(agent_id)
    """
```

---

### 1.10 现有核心模块摘要

以下为已有模块的关键接口，供详细设计参考：

| 模块 | 路径 | 核心类/函数 | 关键方法 |
|------|------|------------|---------|
| **GatewayManager** | `gateway/gateway_manager.py` | `GatewayManager` | `create_agent()`, `submit_prompt()`, `close_agent()`, `shutdown_all()`, `register_session()`, `ensure_default_session()` |
| **SubprocessGateway** | `gateway/subprocess_gateway.py` | `SubprocessGateway` | `start()`, `close()`, `call(method, params)`, `on_event(handler)`, `submit_prompt()`, `interrupt()`, `create_session()` |
| **ChatService** | `services/chat.py` | 模块函数 | `create_session()`, `submit_prompt()`, `sse_generate()`, `interrupt_session()`, `start_plan_chain()` |
| **Orchestrator** | `services/orchestrate.py` | 模块函数 | `orchestrated_chat_sync()`, `start_orchestrated_background_run()`, `orchestrated_control_stream()`, `notify_delegation_ready()` |
| **Neo4jService** | `services/neo4j_service.py` | `Neo4jService` | `import_graph()`, `random_walk()`, `degree_centrality()`, `prune_irrelevant()`, `is_connected()` |
| **MemOSService** | `services/mem_os_service.py` | 模块函数 | `get_mos_for_agent()`, `mos_search()`, `mos_add_text()`, `remove_mos_for_agent()` |
| **AgentService** | `services/agent.py` | 模块函数 | `create_agent()`, `close_agent()`, `list_agents()`, `update_agent()`, `get_agent_memory()` |
| **KnowledgeGraph** | `services/knowledge_graph.py` | 模块函数 | `build_graph_incremental()`, `build_mermaid_graph()`, `query_knowledge_graph()` |
| **AgentBootstrap** | `services/agent_bootstrap.py` | 模块函数 | `bootstrap_all_agents()` |
| **SelfModel** | `services/self_model.py` | 模块函数 | `get_self_model_for_agent()`, `update_self_model_field()`, `delete_self_model()` |
| **PlanChain** | `services/plan_chain.py` | 模块函数 | `start_plan_chain_background()`, `cancel_plan_chain()` |

---

## 二、数据库 DDL

### 2.1 新增表：能量系统

```sql
-- Agent 能量状态表
CREATE TABLE IF NOT EXISTS agent_energy (
    agent_id    TEXT PRIMARY KEY,
    satiety     INTEGER NOT NULL CHECK (satiety BETWEEN 0 AND 100) DEFAULT 80,
    bio_current INTEGER NOT NULL CHECK (bio_current BETWEEN 0 AND 10) DEFAULT 3,
    mode        TEXT NOT NULL CHECK (mode IN ('normal', 'power_save', 'surge', 'forced_discharge'))
                DEFAULT 'normal',
    updated_at  TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (agent_id) REFERENCES agent_avatars(agent_id) ON DELETE CASCADE
);

-- 能量变化日志表
CREATE TABLE IF NOT EXISTS agent_energy_log (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_id     TEXT NOT NULL,
    metric       TEXT NOT NULL CHECK (metric IN ('satiety', 'bio_current')),
    reason       TEXT NOT NULL,
    delta        REAL NOT NULL,
    value_before INTEGER NOT NULL,
    value_after  INTEGER NOT NULL,
    timestamp    TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (agent_id) REFERENCES agent_energy(agent_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_energy_log_agent ON agent_energy_log(agent_id, timestamp DESC);
```

### 2.2 新增表：情绪系统

```sql
-- Agent 情绪状态表
CREATE TABLE IF NOT EXISTS agent_emotion (
    agent_id   TEXT PRIMARY KEY,
    valence    REAL NOT NULL DEFAULT 0.0 CHECK (valence BETWEEN -1.0 AND 1.0),
    arousal    REAL NOT NULL DEFAULT 0.0 CHECK (arousal BETWEEN -1.0 AND 1.0),
    dominance  REAL NOT NULL DEFAULT 0.0 CHECK (dominance BETWEEN -1.0 AND 1.0),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (agent_id) REFERENCES agent_avatars(agent_id) ON DELETE CASCADE
);

-- 情绪变化日志表
CREATE TABLE IF NOT EXISTS agent_emotion_log (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_id  TEXT NOT NULL,
    valence   REAL NOT NULL,
    arousal   REAL NOT NULL,
    dominance REAL NOT NULL,
    trigger   TEXT NOT NULL,
    timestamp TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (agent_id) REFERENCES agent_emotion(agent_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_emotion_log_agent ON agent_emotion_log(agent_id, timestamp DESC);
```

### 2.3 扩展已有表：记忆评分字段

```sql
-- 为每个 Agent 的 memos 表增加字段（在 MemOS 内部或 SQLite 中）
-- 此 Migration 在 MemOS 初始化时执行
ALTER TABLE memos_{agent_id} ADD COLUMN importance_score    REAL    DEFAULT 0.0;
ALTER TABLE memos_{agent_id} ADD COLUMN reinforcement_count INTEGER DEFAULT 0;
ALTER TABLE memos_{agent_id} ADD COLUMN access_count        INTEGER DEFAULT 0;
ALTER TABLE memos_{agent_id} ADD COLUMN conflict_with       TEXT;  -- JSON array of memory IDs
ALTER TABLE memos_{agent_id} ADD COLUMN score_updated_at    TEXT;
```

### 2.4 新增表：髓鞘化系统

```sql
-- 髓鞘化路径表（每个 Agent 独立）
CREATE TABLE IF NOT EXISTS myelination_path_{agent_id} (
    path_id         TEXT PRIMARY KEY,
    path_text       TEXT NOT NULL,
    stage           TEXT NOT NULL CHECK (stage IN ('learning', 'consolidating', 'instinct'))
                    DEFAULT 'learning',
    total_access    INTEGER DEFAULT 0,
    access_7d       INTEGER DEFAULT 0,
    last_access     TEXT,
    cached_answer   TEXT,
    llm_calls_saved INTEGER DEFAULT 0,
    tokens_saved    INTEGER DEFAULT 0,
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_myelination_stage_{agent_id}
    ON myelination_path_{agent_id}(stage);
CREATE INDEX IF NOT EXISTS idx_myelination_last_access_{agent_id}
    ON myelination_path_{agent_id}(last_access);
```

### 2.5 新增表：路由统计

```sql
-- 模型路由统计表
CREATE TABLE IF NOT EXISTS model_routing_stats (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_id    TEXT NOT NULL,
    session_id  TEXT NOT NULL,
    tier        TEXT NOT NULL CHECK (tier IN ('local', 'cloud')),
    model_name  TEXT NOT NULL,
    tokens_in   INTEGER DEFAULT 0,
    tokens_out  INTEGER DEFAULT 0,
    complexity  REAL,          -- 任务复杂度评分
    reason      TEXT NOT NULL, -- 路由原因
    fallback    INTEGER DEFAULT 0,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_routing_stats_agent
    ON model_routing_stats(agent_id, created_at DESC);
```

### 2.6 现有表结构（参考）

```sql
-- agent_avatars: Agent 外观和模型配置
CREATE TABLE IF NOT EXISTS agent_avatars (
    agent_id        TEXT PRIMARY KEY,
    avatar          TEXT NOT NULL DEFAULT 'badboy',
    gender          TEXT NOT NULL DEFAULT 'male',
    office_x        REAL,
    office_y        REAL,
    facing          TEXT,
    model           TEXT,
    model_provider  TEXT,
    model_base_url  TEXT
);

-- agent_personality: Agent 人格设定
CREATE TABLE IF NOT EXISTS agent_personality (
    agent_id     TEXT PRIMARY KEY,
    personality  TEXT NOT NULL DEFAULT '',
    catchphrases TEXT NOT NULL DEFAULT '',
    memes        TEXT NOT NULL DEFAULT ''
);

-- agent_sessions: Session 绑定和链
CREATE TABLE IF NOT EXISTS agent_sessions (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_id           TEXT NOT NULL,
    session_id         TEXT NOT NULL,
    session_key        TEXT,
    created_at         REAL NOT NULL,
    last_used_at       REAL NOT NULL,
    is_active          INTEGER NOT NULL DEFAULT 1,
    parent_session_id  TEXT,
    reflected_turn_count INTEGER DEFAULT 0,
    UNIQUE(agent_id, session_id)
);

-- plan_artifacts: 计划工件
CREATE TABLE IF NOT EXISTS plan_artifacts (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id   TEXT NOT NULL,
    agent_id     TEXT NOT NULL,
    name         TEXT NOT NULL DEFAULT '',
    plan_summary TEXT NOT NULL DEFAULT '',
    steps_json   TEXT NOT NULL DEFAULT '[]',
    raw_text     TEXT,
    status       TEXT NOT NULL DEFAULT 'pending',
    current_step INTEGER NOT NULL DEFAULT -1,
    created_at   REAL NOT NULL
);

-- plan_artifact_steps: 计划步骤
CREATE TABLE IF NOT EXISTS plan_artifact_steps (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    artifact_id  INTEGER NOT NULL,
    step_index   INTEGER NOT NULL DEFAULT 0,
    step_id      INTEGER NOT NULL DEFAULT 0,
    title        TEXT NOT NULL DEFAULT '',
    action       TEXT NOT NULL DEFAULT '',
    file_path    TEXT,
    executor     TEXT,
    session_id   TEXT,
    status       TEXT NOT NULL DEFAULT 'pending',
    error        TEXT,
    completed_at REAL,
    result       TEXT,
    FOREIGN KEY (artifact_id) REFERENCES plan_artifacts(id) ON DELETE CASCADE
);

-- 每个 Agent 的知识图谱节点表
CREATE TABLE IF NOT EXISTS kgnode_{agent_id} (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    label      TEXT NOT NULL UNIQUE,
    type       TEXT NOT NULL,
    summary    TEXT,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);

-- 每个 Agent 的知识图谱边表
CREATE TABLE IF NOT EXISTS kgedge_{agent_id} (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id  INTEGER NOT NULL,
    target_id  INTEGER NOT NULL,
    relation   TEXT NOT NULL,
    evidence   TEXT,
    created_at REAL NOT NULL,
    UNIQUE(source_id, target_id, relation)
);

-- 每个 Agent 的会话摘要缓存表
CREATE TABLE IF NOT EXISTS smry_{agent_id} (
    session_id TEXT PRIMARY KEY,
    summary    TEXT NOT NULL,
    token_count INTEGER DEFAULT 0,
    generated_at REAL NOT NULL,
    model      TEXT
);

-- 每个 Agent 的压缩映射表
CREATE TABLE IF NOT EXISTS cmap_{agent_id} (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    compressed_session_id TEXT NOT NULL,
    original_session_id   TEXT NOT NULL,
    message_range_start   INTEGER,
    message_range_end     INTEGER,
    summary               TEXT,
    key_topics            TEXT,
    compressed_at         REAL NOT NULL,
    UNIQUE(compressed_session_id, original_session_id)
);
```

---

## 三、API 契约

### 3.1 已有端点汇总

| 方法 | 路径 | 用途 | 模块 |
|------|------|------|------|
| `GET` | `/api/health` | 健康检查 | `api/health.py` |
| `GET` | `/api/chat/agents` | 列出所有 Agent | `api/agent.py` |
| `POST` | `/api/chat/agents` | 创建 Agent | `api/agent.py` |
| `GET` | `/api/chat/agents/{id}` | 获取 Agent 详情 | `api/agent.py` |
| `PUT` | `/api/chat/agents/{id}` | 更新 Agent | `api/agent.py` |
| `DELETE` | `/api/chat/agents/{id}` | 删除 Agent | `api/agent.py` |
| `POST` | `/api/chat/agents/office-poses` | 保存办公室姿态 | `api/agent.py` |
| `GET` | `/api/chat/agents/{id}/memory` | 获取记忆详情 | `api/agent.py` |
| `POST` | `/api/chat/agents/{id}/memory/summarize` | 记忆摘要 | `api/agent.py` |
| `GET` | `/api/chat/agents/{id}/memory/dual-stats` | 双重记忆统计 | `api/agent.py` |
| `GET` | `/api/chat/agents/{id}/model` | 获取 Agent 模型 | `api/agent.py` |
| `PUT` | `/api/chat/agents/{id}/model` | 设置 Agent 模型 | `api/agent.py` |
| `GET` | `/api/chat/agents/{id}/memory/knowledge-graph` | 知识图谱数据 | `api/agent.py` |
| `GET` | `/api/chat/agents/{id}/memory/knowledge-graph/mermaid` | Mermaid 可视化 | `api/agent.py` |
| `POST` | `/api/chat/agents/{id}/memory/knowledge-graph/rebuild` | 重建知识图谱 | `api/agent.py` |
| `GET` | `/api/chat/agents/{id}/self-model` | 获取自我模型 | `api/agent.py` |
| `PUT` | `/api/chat/agents/{id}/self-model` | 更新自我模型 | `api/agent.py` |
| `POST` | `/api/chat/agents/{id}/self-model/reflect` | 触发自我反思 | `api/agent.py` |
| `GET` | `/api/chat/agents/{id}/self-model/history` | 自我模型历史 | `api/agent.py` |
| `POST` | `/api/chat/sessions` | 创建会话 | `api/chat.py` |
| `GET` | `/api/chat/sessions` | 列出所有会话 | `api/chat.py` |
| `DELETE` | `/api/chat/sessions/{id}` | 关闭会话 | `api/chat.py` |
| `DELETE` | `/api/chat/sessions/{id}/delete` | 永久删除会话 | `api/chat.py` |
| `POST` | `/api/chat/sessions/{id}/resume` | 恢复会话 | `api/chat.py` |
| `GET` | `/api/chat/sse/{id}` | SSE 事件流 | `api/chat.py` |
| `POST` | `/api/chat/prompt` | 发送消息 | `api/chat.py` |
| `POST` | `/api/chat/interrupt/{id}` | 中断会话 | `api/chat.py` |
| `POST` | `/api/chat/orchestrated` | 同步编排 | `api/chat.py` |
| `POST` | `/api/chat/orchestrated/run` | 异步编排运行 | `api/chat.py` |
| `GET` | `/api/chat/orchestrated/stream` | 编排控制流 | `api/chat.py` |
| `POST` | `/api/chat/orchestrated/delegation_ready` | 委托就绪通知 | `api/chat.py` |
| `GET` | `/api/chat/orchestrated/pending` | 编排待处理 | `api/chat.py` |
| `POST` | `/api/chat/plan-chain/start` | 启动计划链 | `api/chat.py` |
| `POST` | `/api/chat/plan-chain/cancel/{id}` | 取消计划链 | `api/chat.py` |
| `POST` | `/api/chat/approval` | 批准操作 | `api/chat.py` |
| `POST` | `/api/chat/clarify` | 澄清回复 | `api/chat.py` |
| `POST` | `/api/chat/upload` | 上传文件 | `api/chat.py` |
| `GET` | `/api/chat/history/{id}` | 会话历史 | `api/chat.py` |
| `GET` | `/api/chat/sessions/last-active` | 最近活跃会话 | `api/chat.py` |
| `GET` | `/api/chat/sessions/{id}/chain-history` | 链式历史 | `api/chat.py` |
| `GET` | `/api/chat/sessions/{id}/chain` | 会话链 | `api/chat.py` |
| `GET` | `/api/chat/gateway-bridge/sse` | 网关桥接 SSE | `api/chat.py` |
| `GET` | `/api/chat/gateway-bridge/token` | 桥接令牌 | `api/chat.py` |
| `GET` | `/api/chat/heartbeat/sse` | 心跳 SSE | `api/chat.py` |
| `GET` | `/api/chat/feishu/sessions` | 飞书会话列表 | `api/chat.py` |
| `GET` | `/api/chat/feishu/sessions/{id}/messages` | 飞书消息 | `api/chat.py` |
| `GET` | `/api/chat/sessions-files/{agent_id}` | 会话文件列表 | `api/chat.py` |
| `GET` | `/api/chat/session-file/{agent_id}/{file_name}` | 会话文件内容 | `api/chat.py` |
| `GET` | `/api/chat/plans` | 计划 CRUD (见 Plan 模块) | `api/plan.py` |
| `GET` | `/api/chat/skills` | 技能 CRUD (见 Skill 模块) | `api/skill.py` |
| `GET` | `/api/models` | 模型列表 | `api/model.py` |
| `POST` | `/api/models` | 创建模型 | `api/model.py` |
| `PUT` | `/api/models/{id}` | 更新模型 | `api/model.py` |
| `DELETE` | `/api/models/{id}` | 删除模型 | `api/model.py` |
| `GET` | `/api/providers` | 提供商列表 | `api/model.py` |
| `POST` | `/api/provider-models` | 探测提供商模型 | `api/model.py` |
| `GET` | `/api/providers/{provider}/envkey` | 获取环境变量 | `api/model.py` |
| `GET` | `/api/model/list` | 模型分配列表 | `api/model.py` |
| `POST` | `/api/model/assign` | 分配模型 | `api/model.py` |
| `GET` | `/api/channels` | 通道列表 | `api/channels.py` |
| `POST` | `/api/channels` | 创建通道 | `api/channels.py` |
| `PUT` | `/api/channels/{platform}` | 更新通道 | `api/channels.py` |
| `PATCH` | `/api/channels/{platform}` | 局部更新通道 | `api/channels.py` |
| `DELETE` | `/api/channels/{platform}` | 删除通道 | `api/channels.py` |
| `GET` | `/api/platform-gateway/status` | 网关状态 | `api/platform_gateway.py` |
| `POST` | `/api/platform-gateway/start` | 启动网关 | `api/platform_gateway.py` |
| `POST` | `/api/platform-gateway/stop` | 停止网关 | `api/platform_gateway.py` |
| `GET` | `/api/settings` | 获取设置 | `api/settings.py` |
| `PUT` | `/api/settings` | 保存设置 | `api/settings.py` |
| `GET` | `/api/settings/env-vars` | 环境变量 | `api/settings.py` |
| `PUT` | `/api/settings/env-vars` | 更新环境变量 | `api/settings.py` |
| `DELETE` | `/api/settings/env-vars` | 删除环境变量 | `api/settings.py` |
| `GET` | `/api/env` | 获取环境 | `api/env.py` |
| `PUT` | `/api/env` | 更新环境 | `api/env.py` |
| `GET` | `/api/memory/agents/{id}/search` | 向量记忆搜索 | `api/memory.py` |
| `WS` | `/api/stt/ws` | 语音识别 WebSocket | `api/stt.py` |

### 3.2 新增端点：能量管理 (F2)

```
GET  /api/agent/{agent_id}/energy
  Response 200:
  {
    "code": 0,
    "data": {
      "agent_id": "alice",
      "satiety": 75,
      "bio_current": 4,
      "mode": "normal",
      "updated_at": "2026-05-14T10:30:00Z"
    }
  }

GET  /api/agent/{agent_id}/energy/logs?limit=50
  Response 200:
  {
    "code": 0,
    "data": {
      "logs": [
        {
          "metric": "satiety",
          "reason": "task_completed",
          "delta": 15.0,
          "value_before": 60,
          "value_after": 75,
          "timestamp": "2026-05-14T10:25:00Z"
        },
        ...
      ]
    }
  }

POST /api/agent/{agent_id}/energy/reset
  Request:
  {
    "satiety": 100,
    "bio_current": 3,
    "mode": "normal"
  }
  Response 200: { "code": 0, "data": { "agent_id": "alice", "satiety": 100, ... } }
```

### 3.3 新增端点：情绪管理 (F6)

```
GET  /api/agent/{agent_id}/emotion
  Response 200:
  {
    "code": 0,
    "data": {
      "agent_id": "alice",
      "valence": 0.7,
      "arousal": 0.3,
      "dominance": 0.5,
      "updated_at": "2026-05-14T10:30:00Z"
    }
  }

GET  /api/agent/{agent_id}/emotion/timeline?limit=50
  Response 200:
  {
    "code": 0,
    "data": {
      "timeline": [
        {
          "valence": 0.7, "arousal": 0.3, "dominance": 0.5,
          "trigger": "user_praise",
          "timestamp": "2026-05-14T10:25:00Z"
        },
        ...
      ]
    }
  }
```

### 3.4 新增端点：模型路由 (F5)

```
GET  /api/models/routing/preference/{agent_id}
  Response 200:
  {
    "code": 0,
    "data": {
      "agent_id": "alice",
      "preferred_tier": "cloud",
      "current_tier": "local"
    }
  }

POST /api/models/routing/preference/{agent_id}
  Request: { "preferred_tier": "local" }    // "local" | "cloud" | "hybrid"
  Response 200: { "code": 0, "data": { "agent_id": "alice", "preferred_tier": "local" } }

GET  /api/models/routing/stats?agent_id={id}&period=7d
  Response 200:
  {
    "code": 0,
    "data": {
      "local_calls": 45,
      "cloud_calls": 23,
      "local_tokens": 12000,
      "cloud_tokens": 8000,
      "estimated_cost": 0.15
    }
  }
```

### 3.5 新增端点：髓鞘化统计 (F4)

```
GET  /api/agent/{agent_id}/myelination/stats
  Response 200:
  {
    "code": 0,
    "data": {
      "total_paths": 156,
      "learning_count": 120,
      "consolidating_count": 28,
      "instinct_count": 8,
      "llm_calls_saved": 45,
      "tokens_saved": 23400
    }
  }
```

### 3.6 新增端点：记忆评分 (F3)

```
GET  /api/agent/{agent_id}/memory/scoring/candidates
  Response 200:
  {
    "code": 0,
    "data": {
      "total_memories": 185,
      "suggested_prune": [
        { "memory_id": "mem_001", "score": 0.12, "summary": "..." },
        { "memory_id": "mem_045", "score": 0.18, "summary": "..." },
        ...
      ],
      "max_entries": 200
    }
  }

POST /api/agent/{agent_id}/memory/scoring/prune
  Request: { "memory_ids": ["mem_001", "mem_045"] }
  Response 200: { "code": 0, "data": { "deleted_count": 2 } }
```

### 3.7 SSE 事件类型完整目录

| 事件类型 | 触发时机 | 数据字段 |
|---------|---------|---------|
| `message.start` | Agent 开始生成回复 | `{session_id, agent_id}` |
| `message.delta` | 回复逐字流式输出 | `{session_id, text}` |
| `message.complete` | 回复生成完成 | `{session_id, text, usage}` |
| `thinking.delta` | Agent 内部推理增量 | `{session_id, thinking}` |
| `tool.start` | 工具调用开始 | `{session_id, tool_name, input}` |
| `tool.progress` | 工具执行进度 | `{session_id, tool_name, progress}` |
| `tool.complete` | 工具执行完成 | `{session_id, tool_name, output}` |
| `tool.error` | 工具执行失败 | `{session_id, tool_name, error}` |
| `heartbeat.event` | 心跳推理结果 | `{agent_id, snippet, satiety, bio_current}` |
| `heartbeat.small_thought` | 小心思推送 [新增] | `{agent_id, content, confidence, timestamp}` |
| `heartbeat.skipped` | 预判过滤器跳过 [新增] | `{agent_id, reason, node_ids}` |
| `agent.social` | Agent 社交事件 | `{agent_id, message, from_agent_id}` |
| `session.info` | 会话信息更新 | `{session_id, title, ...}` |
| `session.switch` | 上下文压缩切换 | `{old_session_id, new_session_id}` |
| `approval.request` | 请求用户批准 | `{session_id, question, choices}` |
| `clarify.request` | 请求用户澄清 | `{session_id, question, choices}` |
| `plan_chain.step_begin` | 计划步骤开始 | `{session_id, step_id, title}` |
| `plan_chain.step_end` | 计划步骤完成 | `{session_id, step_id, result}` |
| `plan_chain.complete` | 计划链完成 | `{session_id, plan_summary}` |
| `energy.update` | 能量变化通知 [新增] | `{agent_id, satiety, bio_current, mode}` |
| `emotion.update` | 情绪变化通知 [新增] | `{agent_id, valence, arousal, dominance}` |
| `error` | 错误事件 | `{session_id, message}` |

---

## 四、时序图

### 4.1 用户消息流

```
用户输入 → ChatPanel.tsx
  │
  ├─ 1. POST /api/chat/orchestrated/run {sessionId, text}
  │     ├─ orchestrate.start_orchestrated_background_run()
  │     │   ├─ 2. energy.check_thresholds(agent_id)
  │     │   │   └─ if satiety < 30 → return 429 power_save
  │     │   ├─ 3. model_router.route(agent_id, text, ctx_len)
  │     │   │   └─ select tier: local | cloud
  │     │   ├─ 4. backtalk.detect_triggers(agent_id, text, context)
  │     │   │   └─ if triggered → inject backtalk hint
  │     │   ├─ 5. emotion.update_emotion(agent_id, 'task_submit')
  │     │   │   └─ valence/arousal/dominance ± delta
  │     │   ├─ 6. myelination.get_cache(agent_id, query_embedding)
  │     │   │   └─ if stage='instinct' → return cached (skip LLM)
  │     │   ├─ 7. agent_chat_bridge.submit_with_hint(session_id, text)
  │     │   │   └─ build <memory-context>:
  │     │   │       personality + emotion + vector_memory + kg(depth=bio_current) + ...
  │     │   │   └─ GatewayManager.submit_prompt(session_id, text)
  │     │   │       └─ SubprocessGateway.call('prompt.submit', {text})
  │     │   │           └─ JSON-RPC over stdin → Agent 子进程
  │     │   ├─ 8. energy.apply_inference_cost(agent_id)
  │     │   │   └─ satiety -= 0.5 × current_multiplier, bio_current += 0.2
  │     │   └─ 9. return run_id
  │     │
  │     └─ 返回 {ok, run_id}
  │
  ├─ 10. GET /api/chat/orchestrated/stream?run_id=xxx (SSE)
  │      └─ orchestrated_control_stream(run_id) — async generator
  │          ├─ yield message.start → 前端 ChatBubble 显示
  │          ├─ yield message.delta → 逐字渲染
  │          ├─ yield message.thinking / tool.* → AgentToolPanel 更新
  │          ├─ yield energy.update → StatusBar 能量条更新 [新增]
  │          ├─ yield emotion.update → StatusBar 情绪指示器更新 [新增]
  │          ├─ yield message.complete → 标注完成
  │          └─ yield plan_chain.* → PlanTimeline 更新
  │
  └─ 11. 对话结束后
         ├─ orchestrate.py: 处理 @agent 转发
         ├─ mem_os_service.mos_add_text() → 写入向量记忆
         ├─ emotion.update_emotion(agent_id, 'task_complete')
         ├─ energy.apply_positive_interaction(agent_id, 'task_complete')
         └─ knowledge_graph.build_graph_incremental() → 更新知识图谱
```

### 4.2 心跳推理流

```
HeartbeatService._heartbeat_for_agent(agent_id)
  │
  ├─ 1. 检查 Agent 空闲状态 (idle_timeout)
  │     └─ if session active → skip
  │
  ├─ 2. 读取能量状态
  │     ├─ energy.get_energy(agent_id)
  │     └─ interval = get_heartbeat_interval_for_agent(agent_id)
  │         └─ satiety → interval map: <30→90s, 30-60→60s, 60-80→30s, >80→15s
  │         └─ bio_current > 8 → interval *= 2
  │
  ├─ 3. Neo4j 随机游走
  │     ├─ neo4j.random_walk(agent_id, depth=bio_current)
  │     │   └─ 游走过程中每条边消耗 1/weight 单位深度预算
  │     │   └─ 低权重边消耗更多，实际深度 < bio_current
  │     └─ walked_nodes: list[{label, type, relation, weight}]
  │
  ├─ 4. 预判过滤器
  │     ├─ prefilter.calculate_entropy(walked_nodes)
  │     ├─ prefilter.calculate_novelty(walked_nodes, recent_node_ids)
  │     └─ should_invoke_llm() ?
  │         ├─ NO → prefilter.record_skip()
  │         │        yield heartbeat.skipped → SSE
  │         │        return
  │         └─ YES → continue
  │
  ├─ 5. LLM 推理
  │     ├─ prompt = "基于以下知识碎片做深度联想: {walked_nodes}"
  │     └─ result: {insight, question, suggestion}
  │
  ├─ 6. SSE 推送
  │     ├─ yield heartbeat.event → 前端 StatusBar 显示 "💭 {agent} 的思考"
  │     └─ if 通道启用 → 推送飞书/Telegram
  │
  ├─ 7. 能量消耗
  │     └─ energy.apply_inference_cost(agent_id)
  │
  └─ 8. 小心思触发 (随机)
        ├─ if internal_thoughts.should_generate(agent_id)
        │   └─ thought = internal_thoughts.generate(agent_id)
        └─ if thought:
            yield heartbeat.small_thought → SSE
```

### 4.3 启动引导流

```
main.py: lifespan
  │
  ├─ 1. _preload_all_models()
  │     ├─ Vosk 中文 STT 模型
  │     ├─ sentence-transformer all-MiniLM-L6-v2
  │     └─ Neo4j 连接初始化
  │
  ├─ 2. ensure_agent_db_schema()
  │     └─ 创建所有表（包括 agent_energy, agent_emotion 等新增表）
  │
  ├─ 3. GatewayManager 初始化
  │
  ├─ 4. _bootstrap_agents_background(mgr)
  │     └──> agent_bootstrap.bootstrap_all_agents(mgr)
  │          │
  │          ├─ Step 1: MemOS 向量回忆
  │          │   └─ 检查 Qdrant collection 是否存在、数据完整性
  │          │
  │          ├─ Step 2: state.db KG → Neo4j 导入
  │          │   ├─ KnowledgeNodeDAO.get_all_nodes(agent_id)
  │          │   ├─ KnowledgeEdgeDAO.get_all_edges(agent_id)
  │          │   └─ neo4j.import_graph(agent_id, nodes, edges)
  │          │
  │          └─ Step 3: Neo4j 剪枝 + 缓存图谱
  │              ├─ neo4j.prune_irrelevant(agent_id)
  │              └─ neo4j.degree_centrality(agent_id) → 缓存
  │
  └─ 5. heartbeat_svc.start()
       ├─ 为每个 Agent 创建心跳定时任务
       └─ energy.decay_bio_current_loop()     [新增]
       └─ emotion.apply_time_decay()          [新增]
```

### 4.4 多 Agent 编排流 (Bungalow 模式)

```
用户: "@Bob 帮我分析一下这个项目的安全性"
  ↓
POST /api/chat/orchestrated/run
  ↓
orchestrate.py: start_orchestrated_background_run()
  │
  ├─ 1. handoff_parser.parse_user_handoff_prefix(text)
  │     └─ result: {action: "delegate", target: "Bob", message: "帮我分析..."}
  │
  ├─ 2. Agent A (当前) 收到 delegation 请求
  │     ├─ energy 检查 → OK
  │     ├─ emotion 更新 → arousal +0.1 (复杂任务感知)
  │     └─ Agent A: "好的，我来帮你转达给 Bob"
  │         ├─ SSE → message.delta / message.complete
  │         └─ 发送 delegation 事件
  │
  ├─ 3. delegation → GatewayManager 路由
  │     ├─ GatewayManager.find_agent_by_session(Bob_session)
  │     └─ Agent B (Bob) 收到 prompt: "帮我分析一下这个项目的安全性"
  │         ├─ energy 更新 → bio_current += 5 (中型任务)
  │         ├─ emotion 更新 → arousal +0.15
  │         ├─ build <memory-context> with depth=bio_current
  │         ├─ LLM 推理
  │         └─ 回复 → SSE → 返回给 Agent A
  │
  ├─ 4. Agent A 收到 Agent B 的回复
  │     └─ 整合回复: "Bob 的分析如下：..."
  │         └─ SSE → message.complete
  │
  └─ 5. 编排结束
       ├─ energy.apply_positive_interaction(agent_a, 'task_complete')
       └─ energy.apply_positive_interaction(agent_b, 'task_complete')
```

### 4.5 能量更新流

```
事件触发 (task_submit / inference / idle / user_praise)
  ↓
EnergyService.update_satiety(agent_id, delta, reason)
  │
  ├─ 1. 读取当前 satiety + bio_current
  │
  ├─ 2. 如果是消耗操作 (delta < 0):
  │     └─ actual_delta = delta × current_multiplier(bio_current)
  │         └─ bio_current 0-3: ×1.0, 4-6: ×1.5, 7-8: ×2.0, 9-10: ×3.0
  │
  ├─ 3. 计算 new_value = clamp(value + actual_delta, 0, 100)
  │
  ├─ 4. EnergyDAO.insert_log(...)
  │
  ├─ 5. EnergyDAO.upsert_energy(agent_id, new_satiety, bio_current, mode)
  │
  ├─ 6. check_thresholds(agent_id)
  │     ├─ satiety < 30:
  │     │   └─ mode = 'power_save'
  │     │   └─ SSE → frontend: 状态栏红色警告
  │     ├─ bio_current > 8:
  │     │   └─ mode = 'surge'
  │     │   └─ 响应延迟 +50%
  │     └─ bio_current >= 10:
  │         └─ mode = 'forced_discharge'
  │         └─ bio_current → 5
  │         └─ 暂停任务处理 5 分钟
  │
  └─ 7. SSE 推送 → energy.update
       └─ {agent_id, satiety, bio_current, mode}
       └─ 前端 StatusBar EnergyBar 更新
```

---

## 五、前端组件树与数据流

### 5.1 完整组件树

```
App (main.tsx)
└── PhaserGameProvider (context/PhaserGameContext.tsx)
    ├── <div id="phaser-container" style="zIndex:0">
    │   └── Phaser.Game (PhaserCanvas.tsx)
    │       ├── BootScene
    │       └── OfficeScene
    │           ├── AgentSprites (per Agent)
    │           │   ├── Sprite (animated 3-frame pixel art)
    │           │   ├── NameLabel (Text)
    │           │   ├── InferBubble (Graphics + Text) ─ 情绪/状态气泡
    │           │   └── EnergyIndicator (particles) [新增]
    │           └── EncounterManager (碰撞检测 + 社交事件)
    │
    └── <div id="react-ui" style="zIndex:1, pointerEvents:none">
        └── AppShell (AppShell.tsx)
            ├── LeftPanel (toggle, 260px)
            │   └── PlanTimeline (PlanTimeline.tsx)
            │       ├── PlanHeader (agent chips + summary)
            │       ├── StepRows (rail + dot + connector)
            │       └── DeliverableSection (files + dirs)
            │
            ├── CenterArea (Phaser pass-through, pointerEvents:none)
            │
            ├── RightPanel (toggle, ≤380px)
            │   └── ChatPanel (ChatPanel.tsx)
            │       ├── ChatBubble[] (ChatBubble.tsx)
            │       │   └── AvatarCanvas (animated sprite)
            │       ├── AgentToolPanel (AgentToolPanel.tsx)
            │       │   └── ProcessPanel[] (ProcessPanel.tsx)
            │       │       ├── ReasoningRow
            │       │       └── ToolCallRow
            │       └── StreamingIndicator (pulsing dot + "思考中…")
            │
            ├── BottomBar (zIndex:10, pointerEvents:all)
            │   └── StatusBar (StatusBar.tsx)
            │       ├── EnergyBar [新增] ─ 双色条（饱食度绿→红，生物电流蓝→橙）
            │       ├── EmotionIndicator [新增] ─ 三色圆点 (PAD)
            │       ├── HeartbeatMessage ─ "💭 alice 的思考: ..."
            │       ├── MenuButtons (Agent | Tasks | Channels | Models | Skills | Memory)
            │       ├── Textarea (input)
            │       └── SendButton | VoiceToggle
            │
            ├── DockPanel (DockPanel.tsx, slides up 20vh)
            │   ├── AgentList (AgentList.tsx)
            │   ├── TaskList (TaskList.tsx)
            │   ├── ChannelList (ChannelList.tsx)
            │   ├── ModelList (ModelList.tsx)
            │   ├── SkillList (SkillList.tsx)
            │   └── MemoryList (MemoryList.tsx)
            │
            ├── Modals (pointerEvents:all)
            │   ├── AgentEditForm (PersonaTab + RoleTab + AvatarPicker)
            │   ├── ChannelEditForm (15 platform options)
            │   ├── ModelEditForm (provider select + auto-probe)
            │   ├── MemoryDetailModal (DualMemoryTab + KnowledgeGraphTab + MyelinationTab [新增])
            │   ├── ClarifyPrompt
            │   ├── ReasoningResultModal
            │   └── SkillDetailModal
```

### 5.2 状态管理架构 — Store 依赖图

```
┌────────────────────────────────────────────────────────────────┐
│                        Zustand Stores                          │
├──────────────┬──────────────┬──────────────┬──────────────────┤
│  appStore    │ sessionStore │  agentStore  │   uiStore        │
│  ─────────── │ ──────────── │ ──────────── │   ───────────    │
│  initialized │ sessions[]   │ agents[]     │   dockContent    │
│  wsConnected │ activeId     │ agentScene   │   show* toggles  │
│  heartbeat   │ input        │   Infer[]    │                  │
│  attachments │ sending      │ reasoning    │                  │
│              │ approval     │   Modal      │                  │
│              │ clarify      │ agentLast    │                  │
│              │ isRestoring  │   Plan[]     │                  │
├──────────────┼──────────────┼──────────────┼──────────────────┤
│  planStore   │ channelStore │  modelStore  │   skillStore     │
│  ─────────── │ ──────────── │ ──────────── │   ───────────    │
│  timelineRun │ channels[]   │ models[]     │   skills[]       │
│  taskList[]  │ editingId    │ providers[]  │                  │
│  selectedId  │ showModal    │ editingId    │                  │
│              │              │ showModal    │                  │
├──────────────┼──────────────┼──────────────┼──────────────────┤
│ feishuStore  │ officeAgent  │  chatStore   │                  │
│ ───────────  │   PoseStore  │ (legacy)     │                  │
│ mirror rows  │ poses{}      │ monolithic   │                  │
│              │ dirty        │ (deprecated  │                  │
│              │              │  re-exports) │                  │
└──────────────┴──────────────┴──────────────┴──────────────────┘
```

**Store → Component 消费关系**：

| Store | 消费组件 |
|-------|---------|
| `appStore` | StatusBar (heartbeat, attachments) |
| `sessionStore` | ChatPanel, ChatBubble, AgentToolPanel, StatusBar, AppShell |
| `agentStore` | AgentList, AgentEditForm, OfficeScene, StatusBar, AppShell |
| `uiStore` | AppShell (dockContent, show* toggles) |
| `planStore` | PlanTimeline, TaskList |
| `channelStore` | ChannelList, ChannelEditForm |
| `modelStore` | ModelList, ModelEditForm |
| `skillStore` | SkillList |
| `officeAgentPoseStore` | OfficeScene (Phaser ↔ React bridge) |
| `feishuStore` | ChatPanel (mirror mode) |

### 5.3 SSE → Store → Component 数据流

```
Server-Sent Events (api/chat.ts → createEventSource)
  │
  └── useSseSession hook (exponential backoff reconnection)
      └── useSseEventHandler hook (event type dispatcher)
          │
          ├── message.start
          │   ├─ sessionStore.appendChat(sessionId, msg)
          │   └─ agentStore.setInferState(agentId, 'thinking', ...)
          │       └─ OfficeScene → AgentSprites.drawInferBubble('thinking')
          │
          ├── message.delta
          │   └─ sessionStore.appendDelta(sessionId, text)
          │       └─ ChatPanel → ChatBubble (re-render with incremental text)
          │
          ├── message.complete
          │   ├─ sessionStore.finalizeMessage(sessionId, text, usage)
          │   └─ agentStore.setInferState(agentId, 'done', snippet)
          │
          ├── thinking.delta / reasoning.delta
          │   ├─ agentStore.appendReasoning(agentId, text)
          │   └─ sessionStore.appendReasoningDelta(sessionId, text)
          │       └─ AgentToolPanel → ProcessPanel (reasoning variant)
          │
          ├── tool.start / tool.progress / tool.complete
          │   ├─ sessionStore.appendToolCall / updateToolProgress / completeTool
          │   └─ agentStore.setInferState(agentId, 'tool', ...)
          │       └─ AgentToolPanel → ProcessPanel (tool variant)
          │
          ├── heartbeat.event
          │   ├─ appStore.setHeartbeatMessage({agentId, content, timestamp})
          │   └─ appStore.setHeartbeatThinking('...')
          │       └─ StatusBar → heartbeat message display
          │
          ├── heartbeat.small_thought [新增]
          │   └─ appStore.setSmallThought({agentId, content, confidence})
          │       └─ StatusBar → SmallThoughtBubble (floating popup) [新增]
          │
          ├── heartbeat.skipped [新增]
          │   └─ appStore.setHeartbeatMessage({agentId, content: '🦗 跳过...', ...})
          │
          ├── energy.update [新增]
          │   └─ appStore.setAgentEnergy(agentId, {satiety, bio_current, mode})
          │       └─ StatusBar → EnergyBar (re-render bars)
          │       └─ OfficeScene → AgentSprites EnergyIndicator (particles)
          │
          ├── emotion.update [新增]
          │   └─ appStore.setAgentEmotion(agentId, {valence, arousal, dominance})
          │       └─ StatusBar → EmotionIndicator (re-render dots)
          │
          ├── plan_chain.step_begin / step_end / complete
          │   └─ planStore.setPlanTimelineRun(...)
          │       └─ PlanTimeline → step status + progress bar updates
          │
          ├── approval.request
          │   └─ sessionStore.setApproval({sessionId, payload})
          │
          └── clarify.request
              └─ sessionStore.setClarify({sessionId, question, choices})
```

### 5.4 新增前端组件设计

#### `EnergyBar` — `frontend/src/components/EnergyBar.tsx`

```typescript
interface EnergyBarProps {
  agentId: string;
  satiety: number;        // 0-100
  bioCurrent: number;     // 0-10
  mode: string;           // 'normal' | 'power_save' | 'surge' | 'forced_discharge'
}

// 渲染:
// ┌─────────────────────────────────────────┐
// │ 🍞 饱食度 ████████████░░░░░░ 75% [正常] │  ← green→yellow→red gradient
// │ ⚡ 电流   ████░░░░░░░░░░░░ 4/10 [正常]  │  ← blue→orange→red gradient
// │ 模式: 正常                              │
// └─────────────────────────────────────────┘
//
// mode='power_save': 脉搏跳动动画
// mode='surge': 电光闪烁动画
// mode='forced_discharge': 红色警报闪烁
```

#### `EmotionIndicator` — `frontend/src/components/EmotionIndicator.tsx`

```typescript
interface EmotionIndicatorProps {
  valence: number;    // -1 ~ 1
  arousal: number;    // -1 ~ 1
  dominance: number;  // -1 ~ 1
}

// 渲染: 三个彩色圆点
// 🟢 愉悦度 (valence)  — 绿→灰→红
// 🟡 唤醒度 (arousal)  — 蓝→灰→橙
// 🔵 支配度 (dominance) — 大→小

// hover: 显示精确数值
// click: 展开情绪时间线 mini-chart (最近 20 条日志)
```

#### `SmallThoughtBubble` — `frontend/src/components/SmallThoughtBubble.tsx`

```typescript
interface SmallThoughtBubbleProps {
  agentId: string;
  content: string;
  confidence: number;
  onDismiss: () => void;
}

// 渲染: 浮动气泡，从 StatusBar 弹出
// ┌────────────────────────────────┐
// │ 💭 alice 的小心思               │
// │ "我在想，主人最近总是在周五晚   │
// │  加班，也许我可以提前帮整理     │
// │  周报？"                       │
// │                     置信度: 72% │
// └────────────────────────────────┘

// 动画: fadeIn + slideUp, 5s 后自动消失
// 样式: 半透明玻璃 morphism, zIndex: 2000
```

#### `MyelinationTab` — `MemoryDetailModal` 新增 Tab

```typescript
interface MyelinationTabProps {
  agentId: string;
  stats: MyelinationStats;
}

// 渲染:
// ┌─────────────────────────────────────────────┐
// │  髓鞘化进化                                  │
// │  ┌──────────┬──────────┬──────────────────┐ │
// │  │ Learning │ Consolid │ Instinct         │ │
// │  │   120    │    28    │    8             │ │
// │  │  ⬤⬤⬤⬤⬤  │  ⬤⬤     │  ⬤              │ │
// │  └──────────┴──────────┴──────────────────┘ │
// │                                              │
// │  饼图: [Learning 77%] [Consolidating 18%]    │
// │        [Instinct 5%]                         │
// │                                              │
// │  节省资源:                                    │
// │  - 跳过 LLM 调用: 45 次                       │
// │  - 节省 Token: 23,400                        │
// │  - 估算节省费用: $0.12                        │
// └─────────────────────────────────────────────┘
```

### 5.5 前端 Hook 扩展

在 `appStore` 中新增状态字段：

```typescript
interface AppState {
  // ... 已有字段 ...

  // ---- 新增字段 ----
  agentEnergy: Record<string, {
    satiety: number;
    bioCurrent: number;
    mode: string;
    updatedAt: string;
  }>;
  agentEmotion: Record<string, {
    valence: number;
    arousal: number;
    dominance: number;
    updatedAt: string;
  }>;
  smallThought: {
    agentId: string;
    content: string;
    confidence: number;
    timestamp: number;
  } | null;

  // ---- 新增 Actions ----
  setAgentEnergy: (agentId: string, energy: AgentEnergy) => void;
  setAgentEmotion: (agentId: string, emotion: AgentEmotion) => void;
  setSmallThought: (thought: SmallThought | null) => void;
  dismissSmallThought: () => void;
}
```

---

## 六、文档版本

| 版本 | 日期 | 变更内容 |
|------|------|----------|
| v1.0 | 2026-05-14 | 初稿：类设计、DDL、API 契约、时序图、前端组件树 |

---

## 七、文档索引

| 文档 | 路径 | 用途 |
|------|------|------|
| 详细设计文档 (本文) | `docs/hermes-v2-detailed-design.md` | 类设计、DDL、API契约、时序图、组件树 |
| 系统设计文档 | `docs/hermes-v2-system-design.md` | 系统架构与技术栈总览 |
| 产品需求文档 | `docs/hermes-v2-prd.md` | 7 大功能模块需求详述 |
| 架构升级报告 | `docs/hermes-v2-agent-upgrade-report.md` | 当前实现 vs 设计文档差距分析 |
| 四层记忆体系 | `.qoder/specs/memory-layers-architecture.md` | 运行时记忆注入管道设计 |
| 界面原型 | `docs/ui-prototype.html` | 全系统交互式HTML原型 |
