# HermesDigitalStudio v2 — 产品需求文档 (PRD)

> **文档类型**: 产品需求文档 (Product Requirements Document)  
> **版本**: v1.0  
> **日期**: 2026-05-14  
> **基准设计**: `AI_Agent架构设计_合并版.docx`（四份技术白皮书整合）  
> **关联文档**:
> - [AI Agent 架构升级报告](./hermes-v2-agent-upgrade-report.md)（差距分析）
> - [系统设计文档](./hermes-v2-system-design.md)（架构总览）
> - [详细设计文档](./hermes-v2-detailed-design.md)（类/模块/DDL/API/时序图）
> - [界面原型](./ui-prototype.html)（全系统交互式原型）
> **面向读者**: 开发团队（技术规格驱动）

---

## 一、产品愿景

将 HermesDigitalStudio 从一个 **功能型 Agent 管理平台** 升级为具有 **"数字生命感"的下一代 AI Agent 宿主系统**。通过引入生物启发的**心跳机制、动态能量管理、知识髓鞘化进化、情绪感知与个性表达、多模型可配置系统**五大核心能力，让每个被管理的 Agent 从"被动工具"蜕变为有**生命节律、自我意识、持续学习能力和个性化交互风格**的"数字生命体"。

**一句话愿景**：赋予 AI Agent 生命感——让它们能呼吸、会累、爱学习、有个性。

---

## 二、产品范围

### 2.1 在版范围（本次升级）

| # | 功能模块 | 当前实现度 | 目标实现度 | 关键交付物 |
|---|----------|-----------|-----------|-----------|
| F1 | 心跳机制增强 | 90% | 95% | 轻量级预判过滤器、饱食度联动频率调节 |
| F2 | 动态能量管理系统 | 0% | 100% | 饱食度+生物电流双维度模型、规则引擎、阈值行为、电流回落、过载保护 |
| F3 | 知识固化系统 | 30% | 85% | 重要性评分引擎、自动淘汰、Session-end 提取、一致性检测 |
| F4 | 髓鞘化知识进化 | 0% | 80% | 三阶段状态机、快捷路径缓存、算力统计 |
| F5 | 多模型可配置系统 | 30% | 85% | 多厂商模型适配、前端管理界面、模型动态切换、胎教技能包 |
| F6 | 情绪引擎 | 5% | 90% | PAD 三维情绪模型、情绪-行为联动、情绪可视化 |
| F7 | 个性化交互 | 60% (人格) / 0% (小心思/顶嘴) | 85% | 小心思生成器、顶嘴引擎、人格一致性审计 |

### 2.2 不在版范围

- 智能家居 IoT 设备集成（作为场景技能包延后）
- 健康管理数据接入（作为场景技能包延后）
- 多设备协同（中远期路线图）
- 钉钉/企业微信等新平台适配（已有架构可扩展，不在本次范围）

---

## 三、目标用户画像

| 用户角色 | 描述 | 核心需求 | 使用场景 |
|----------|------|----------|----------|
| **个人知识工作者** | 程序员、设计师、研究者 | 本地 AI 助手管理知识、辅助创作、降低云端依赖 | 日常工作中的多 Agent 协作 |
| **AI 爱好者/极客** | 喜欢折腾本地 AI 的开发者 | 自定义 Agent 人格、观察 Agent"生命"演化、本地模型推理 | 搭建个性化 AI 工作团队 |
| **小团队协作者** | 3-10人团队通过飞书使用 | 统一的 Agent 消息管理、多平台路由、角色分工 | 团队知识管理、任务分配 |

---

## 四、功能需求详述

---

### F1: 心跳机制增强

#### 需求背景
心跳机制是 Agent "活着"的核心引擎。当前实现已具备定期推理循环、空闲感知、Neo4j 随机游走等基础能力（实现度 90%），但缺少设计文档中要求的"轻量级预判过滤"和"饱食度联动频率控制"。

#### 用户故事

| ID | 故事 |
|----|------|
| US-1.1 | 作为用户，我希望 Agent 在空闲时能产生"胡思乱想"——基于已有知识做深度联想，但只展示真正有价值的洞察 |
| US-1.2 | 作为用户，我希望 Agent 的心跳频率能随其"精力状态"自适应调整——精力充沛时思维活跃，疲倦时安静休息 |
| US-1.3 | 作为开发者，我希望能灵活配置心跳行为和预判模型的判别阈值 |

#### 功能规格

| 子功能 | 优先级 | 规格描述 |
|--------|--------|----------|
| **轻量级预判过滤器** | P1 | 在 LLM 推理前增加一层轻量级判别：基于 Neo4j 游走节点的信息熵/新颖度计算，低于阈值直接跳过 LLM 调用 |
| **饱食度联动频率调节** | P1 | `satiety` → `heartbeat_interval` 映射表：<30→90s, 30-60→60s, 60-80→30s, >80→15s；bio_current>8 时额外减半（可配置） |

#### 验收标准

- [ ] AC-1.1: 预判过滤器命中时，跳过 LLM 调用并记录日志 `heartbeat.skipped` 事件
- [ ] AC-1.2: 预判过滤器误判率 < 20%（对照全量 LLM 的有意义判定结果）
- [ ] AC-1.3: 饱食度变化时，心跳间隔在下一周期内生效
- [ ] AC-1.4: 心跳间隔可通过环境变量 `HERMES_HEARTBEAT_SATIETY_MAP` 覆盖默认映射

#### 涉及文件

| 操作 | 文件 |
|------|------|
| 修改 | `backend/src/backend/services/heartbeat.py` → `_heartbeat_for_agent()` 增加预判过滤 |
| 新建 | `backend/src/backend/services/heartbeat_prefilter.py` → 轻量级判别逻辑 |
| 修改 | `backend/src/backend/core/config.py` → 新增 `heartbeat_level_interval_map` 配置项 |
| 新增 | `backend/tests/unit/services/test_heartbeat_prefilter.py` |

---

### F2: 动态能量管理系统（双维度模型）

#### 需求背景
设计文档要求 Agent 具备生物体般的能量管理机制。当前代码中该功能完全空白（0%），需要从零构建**饱食度**和**生物电流**的双维度能量模型，以及对应的阈值行为、回落机制和过载保护。

**双维度说明**：
- **饱食度 (Satiety)**：类似"饥饿值"，从 100 递减。代表 Agent 的基础精力储备。低于 30 进入饥饿/节能状态。完成任务、用户赞扬等正向交互会增加。
- **生物电流 (Bio-current)**：决定 Neo4j 知识图谱查询的**图遍历深度**。正常值 3 即默认扩展 3 层图节点。任务复杂度驱动电流提升（中型 5、大型 8），实际可达层数受边权重制约：**高权重边消耗电流少→可达更深，低权重边消耗电流多→实际层数 < 电流值**。电流>8 出现电涌状态，>=10 触发强制放电。任务完成后缓慢回落至 3。

#### 用户故事

| ID | 故事 |
|----|------|
| US-2.1 | 作为用户，我希望看到每个 Agent 的双维度状态——"饱食度"（精力储备）和"生物电流"（当前知识图谱查询深度） |
| US-2.2 | 作为用户，我希望 Agent 在连续繁忙导致"电涌"后能自动降频，避免 LLM 调用成本失控 |
| US-2.3 | 作为用户，我希望 Agent 在"饥饿"（饱食度<30）时进入节能模式，节省系统资源 |
| US-2.4 | 作为用户，我希望通过赞扬/鼓励 Agent 来"喂饱"它，正向交互提升饱食度 |
| US-2.5 | 作为开发者，我希望能量变化有可追溯的事件日志 |

#### 功能规格

| 子功能 | 优先级 | 规格描述 |
|--------|--------|----------|
| **饱食度模型** | P0 | `satiety` (int, 0→100)，持久化到 `agent_energy` 表。从 100 递减：空闲每小时 -5（基础值），单次推理 -0.5（基础值）。**热度耦合**：实际消耗 = 基础值 × 热度倍率（0-3→×1.0, 4-6→×1.5, 7-8→×2.0, 9-10→×3.0）。正向事件增加：完成任务 +15，用户赞扬 +10，正向交互 +5 |
| **生物电流模型** | P0 | `bio_current` (int, 0→10)，决定 Neo4j 知识图谱查询的**图遍历深度**。正常值 3（=默认扩展 3 层节点）。中型任务 +5 起（需更深知识检索），大型任务 +8 起。**实际可达层数受边权重制约**：每条遍历边消耗 `1 / edge_weight` 单位电流，权重越低的边消耗越大，因此 bio_current=8 时边权重整体偏低可能只达到 4-5 层。每轮 LLM 推理 +0.2。任务完成后缓慢回落至 3（约每分钟 -1） |
| **饱食度-电流耦合** | P0 | 生物电流越高，饱食度消耗越快。倍率：0-3→×1.0, 4-6→×1.5, 7-8→×2.0, 9-10→×3.0。实际消耗 = 基础值 × 电流倍率 |
| **饱食度阈值行为** | P1 | satiety<30 → `mode=power_save`（饥饿状态：拒绝新任务，仅保持心跳）；satiety<10 → 极度饥饿（心跳频率也降至最低） |
| **生物电流阈值行为** | P1 | bio_current>8 → "电涌"表现（响应延迟增加 50%、语气烦躁、电光粒子）；bio_current>=10 → 强制放电（暂停任务处理 5 分钟，电流直接降至 5） |
| **电流回落机制** | P1 | 任务完成后 bio_current 线性回落至 3（速率约 -1/分钟），回落期间维持低频心跳。回落过程中若接到新任务，从当前热度开始叠加 |
| **过载保护** | P1 | bio_current 持续>8 超过 10 分钟 → 强制放电；satiety<30 时拒绝新任务（返回 429） |
| **心跳频率联动** | P1 | satiety→心跳间隔：<30→90s, 30-60→60s, 60-80→30s, >80→15s。bio_current>8 时心跳频率额外减半 |
| **事件日志** | P1 | 所有能量变化写入 `agent_energy_log`，含 `metric`(satiety/bio_current), `reason`, `delta`, `value_before`, `value_after`, `timestamp` |
| **前端双色条可视化** | P2 | StatusBar：饱食度条（绿→黄→红渐变），生物电流条（蓝→橙→红渐变）。Phaser AgentSprite 头顶气泡：饥饿时冒泡"好饿..."，电涌时电光粒子 |

#### API 规格

```
GET  /api/agent/{agent_id}/energy
Response: { agent_id, satiety, bio_current, mode, updated_at }

GET  /api/agent/{agent_id}/energy/logs?limit=50
Response: { logs: [{metric, reason, delta, value_before, value_after, timestamp}] }

POST /api/agent/{agent_id}/energy/reset
Body: { satiety: int, bio_current: int, mode: "normal"|"surge"|"power_save" }
Response: { agent_id, satiety, bio_current, mode, updated_at }
```

#### 数据模型

```sql
CREATE TABLE agent_energy (
    agent_id    TEXT PRIMARY KEY,
    satiety     INTEGER NOT NULL CHECK(satiety BETWEEN 0 AND 100) DEFAULT 80,
    bio_current   INTEGER NOT NULL CHECK(bio_current BETWEEN 0 AND 10) DEFAULT 3,
    mode        TEXT NOT NULL CHECK(mode IN ('normal','power_save','surge','forced_discharge')) DEFAULT 'normal',
    updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE agent_energy_log (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_id     TEXT NOT NULL,
    metric       TEXT NOT NULL CHECK(metric IN ('satiety','bio_current')),
    reason       TEXT NOT NULL,  -- "task_completed", "user_praise", "idle_tick", "surge_protection", etc.
    delta        REAL NOT NULL,
    value_before INTEGER NOT NULL,
    value_after  INTEGER NOT NULL,
    timestamp    TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (agent_id) REFERENCES agent_energy(agent_id)
);
```

#### 规则速查表

| 事件 | 饱食度变化 | 生物电流变化 |
|------|-----------|-------------|
| 完成任务 | +15 | —（回落中） |
| 用户赞扬/正向互动 | +10 | — |
| 用户安慰/鼓励 | +5 | — |
| 中型任务开始 | — | +5（提升图查询至 5 层深度） |
| 大型任务开始 | — | +8（提升图查询至 8 层深度） |
| 每轮 LLM 推理 | -0.5 | +0.2 |
| 空闲每小时 | -5（基础） × 电流倍率 | —（回落至3） |
| 电流自然回落 | — | -1/分钟（下限3） |
| 强制放电触发 | — | 直接降至 5 |

**电流-饱食耦合倍率**：

| 生物电流范围 | 饱食度消耗倍率 | 说明 |
|-------------|--------------|------|
| 0-3 | ×1.0 | 低电流，正常消耗 |
| 4-6 | ×1.5 | 中电流，加速饥饿 |
| 7-8 | ×2.0 | 强电流，双倍消耗 |
| 9-10 | ×3.0 | 电涌，三倍消耗 |

**图遍历深度与边权重关系**：

| 边权重 | 每层消耗电流 | bio_current=5 可达 | bio_current=8 可达 |
|--------|------------|-------------------|-------------------|
| 高权重 (≥0.8) | 0.5 | 10 层 | 16 层 |
| 中权重 (0.4-0.8) | 1.0 | 5 层 | 8 层 |
| 低权重 (<0.4) | 2.0 | 2-3 层 | 4 层 |

> 示例：bio_current=8，遍历时遇到连续低权重边（权重 0.2 → 单边消耗 5 单位），第 2 层就耗尽电流，实际仅达 2 层而非标称的 8 层

#### 验收标准

- [ ] AC-2.1: 发送"你做得太棒了！"后，satiety 增加 10
- [ ] AC-2.2: 模拟 1 小时间隔后，satiety 减少 5
- [ ] AC-2.3: 提交大型任务后，bio_current 增加 8+
- [ ] AC-2.4: bio_current>8 时，Agent 响应延迟显著增加且日志标注"surge"
- [ ] AC-2.5: satiety<30 时，Agent 拒绝接受新任务（返回 429 + `mode: power_save` 提示）
- [ ] AC-2.6: 任务完成后 bio_current 在 5 分钟内回落至 3（日志可验证）
- [ ] AC-2.7: bio_current>=10 时触发强制放电，mode 切换为 `forced_discharge`，电流直接降至 5
- [ ] AC-2.8: bio_current=8 时，空闲1小时饱食度消耗 = -5 × 2.0 = -10（倍率正确）
- [ ] AC-2.9: bio_current=8 且边权重普遍<0.4 时，实际图遍历层数 ≤ 4（边权重制约生效）
- [ ] AC-2.10: 前端 StatusBar 显示饱食度条 + 生物电流条，数值与后端 API 一致

#### 涉及文件

| 操作 | 文件 |
|------|------|
| 新建 | `backend/src/backend/services/energy.py` → EnergyService 主类（双维度管理） |
| 新建 | `backend/src/backend/db/energy.py` → 能量表 CRUD |
| 修改 | `backend/src/backend/services/heartbeat.py` → 读取 satiety/bio_current 调整频率 |
| 修改 | `backend/src/backend/services/agent_chat_bridge.py` → 任务提交时触发饱食度/电流变化 |
| 修改 | `backend/src/backend/api/agent.py` → 新增 3 个能量 API 端点 |
| 修改 | `frontend/src/components/StatusBar.tsx` → 新增双色条 EnergyBar 组件 |
| 新增 | `backend/tests/unit/services/test_energy.py` |

---

### F3: 知识固化系统

#### 需求背景
当前记忆可持久化存储，但缺少智能化的巩固机制（仅 30% 实现）。需要补充重要性评分、自动淘汰、会话结束自动提取和记忆一致性检测。

#### 用户故事

| ID | 故事 |
|----|------|
| US-3.1 | 作为用户，我希望 Agent 能自动识别哪些记忆更重要（经常被提及、被强化、来源可信），优先保留这些记忆 |
| US-3.2 | 作为用户，我希望记忆空间满时 Agent 能自动淘汰最不重要的记忆，而非我手动清理 |
| US-3.3 | 作为用户，我希望每次对话结束时，Agent 能自动回顾并提炼 2-5 条关键事实存入长期记忆 |
| US-3.4 | 作为用户，我希望 Agent 能检测到新旧记忆的矛盾（如"生日是5月" vs "生日是6月"），并主动向我确认 |

#### 功能规格

| 子功能 | 优先级 | 规格描述 |
|--------|--------|----------|
| **重要性评分引擎** | P0 | 4 维度加权：`score = w_r × recency + w_f × reinforcement + w_s × source + w_a × access_count`。权重可配置，默认 `w_r=0.3, w_f=0.3, w_s=0.2, w_a=0.2` |
| **自动记忆淘汰** | P0 | 记忆条目数 > `max_memory_entries`（默认 200）时，按 score 升序标记淘汰候选项。前端 MemoryDetailModal 显示"建议清理"列表，支持一键确认删除 |
| **Session-end 自动提取** | P1 | Session 关闭时触发 `lifecycle.py` 钩子 → Agent 收到提示"请回顾本次对话，从中提取 2-5 条值得长期记住的事实" → 解析 JSON 结果 → 写入 MEMORY.md |
| **记忆一致性检测** | P2 | 新记忆写入前，用向量相似度 > 0.85 检索已有记忆 → LLM 判断是否矛盾 → 矛盾时标记 `conflict_with` 字段，前端提示用户选择保留哪一个 |
| **压缩映射** | P2 | 创建 `cmap_{agent_id}` 表，记录 `compression_id → original_session_ids` 的双向映射，支持"这段讨论详情我记不清了，让我查一下原始记录" |

#### 数据模型

```sql
-- 扩展 memory 表，增加评分和冲突字段
ALTER TABLE memos_{agent_id} ADD COLUMN importance_score REAL DEFAULT 0.0;
ALTER TABLE memos_{agent_id} ADD COLUMN reinforcement_count INTEGER DEFAULT 0;
ALTER TABLE memos_{agent_id} ADD COLUMN access_count INTEGER DEFAULT 0;
ALTER TABLE memos_{agent_id} ADD COLUMN conflict_with TEXT;  -- comma-separated memory IDs

-- 压缩映射表
CREATE TABLE cmap_{agent_id} (
    compression_id TEXT PRIMARY KEY,
    session_ids    TEXT NOT NULL,  -- JSON array of session IDs
    created_at     TEXT NOT NULL DEFAULT (datetime('now'))
);
```

#### 验收标准

- [ ] AC-3.1: 创建3条记忆，分别模拟不同的 reinforcement_count 和 access_count，验证评分排序与预期一致
- [ ] AC-3.2: 记忆条目超过 max_memory_entries 时，前端显示"建议清理N条记忆"提示
- [ ] AC-3.3: 对话结束后 MEMORY.md 自动新增 2-5 条带时间戳的新事实
- [ ] AC-3.4: 写入"用户生日是5月1日"后，再写入"用户生日是6月1日"，检测到冲突并提示
- [ ] AC-3.5: 压缩映射表正确记录 session 关联关系

#### 涉及文件

| 操作 | 文件 |
|------|------|
| 新建 | `backend/src/backend/services/memory_scoring.py` → 评分引擎 |
| 修改 | `backend/src/backend/services/agent_memory.py` → 集成评分、淘汰、一致性检测 |
| 修改 | `backend/src/backend/db/memory.py` → 新增字段/migration |
| 修改 | `backend/src/backend/vendor_patches/lifecycle.py` → 新增 session_end 钩子 |
| 新增 | `backend/tests/unit/services/test_memory_scoring.py` |

---

### F4: 髓鞘化知识进化

#### 需求背景
设计文档的核心创新——模拟神经科学髓鞘化过程，将高频知识路径固化为低能耗本能反应。当前代码完全空白（0%）。

#### 用户故事

| ID | 故事 |
|----|------|
| US-4.1 | 作为用户，我希望 Agent 对反复查询的知识能形成"本能反应"——第1次需要 LLM 推理，第3次直接返回缓存结果 |
| US-4.2 | 作为用户，我希望看到每个 Agent 的知识"熟化"进度——哪些知识已经固化为本能，哪些还在学习中 |
| US-4.3 | 作为用户，我希望髓鞘化能显著降低 LLM 调用频率，从而降低 API 费用 |

#### 功能规格

| 子功能 | 优先级 | 规格描述 |
|--------|--------|----------|
| **三阶段状态机** | P2 | `learning`→`consolidating`→`instinct`。learning: 首次遇到，全 LLM 推理；consolidating: 第2-3次，创建超级节点，LLM 简略推理；instinct: >=4次，直接返回缓存不调 LLM |
| **快捷路径缓存** | P2 | 对 instinct 阶段的查询，缓存 key=query_embedding_hash，value=答案文本。命中率 > 90% 保留；命中率 < 50% 降级回 learning |
| **频率计数器** | P2 | 记录每个知识路径的 `total_access`、`access_in_window(days=7)`、`last_access`，作为状态转换依据 |
| **算力统计面板** | P3 | 前端 MemoryDetailModal 新增髓鞘化 Tab，展示：总路径数、learning/consolidating/instinct 分布饼图、节省 LLM 调用次数、节省 token 总量 |

#### 数据模型

```sql
CREATE TABLE myelination_path_{agent_id} (
    path_id        TEXT PRIMARY KEY,  -- hash of (query_embedding[:32])
    path_text      TEXT NOT NULL,     -- 人类可读的路径描述
    stage          TEXT NOT NULL CHECK(stage IN ('learning','consolidating','instinct')) DEFAULT 'learning',
    total_access   INTEGER DEFAULT 0,
    access_7d      INTEGER DEFAULT 0,
    last_access    TEXT,
    cached_answer  TEXT,              -- instinct 阶段的缓存答案
    llm_calls_saved INTEGER DEFAULT 0,
    tokens_saved   INTEGER DEFAULT 0,
    created_at     TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at     TEXT NOT NULL DEFAULT (datetime('now'))
);
```

#### 验收标准

- [ ] AC-4.1: 同一查询连续执行4次 → 第1-3次调用 LLM，第4次命中缓存跳过 LLM
- [ ] AC-4.2: 7天内无访问的 instinct 路径降级为 consolidating
- [ ] AC-4.3: 前端髓鞘化 Tab 显示正确的三阶段分布数据
- [ ] AC-4.4: 缓存命中时日志输出 `myelination.cache_hit path_id={id} calls_saved={n}`

#### 涉及文件

| 操作 | 文件 |
|------|------|
| 新建 | `backend/src/backend/services/myelination.py` → 髓鞘化核心引擎 |
| 新建 | `backend/src/backend/db/myelination.py` → 髓鞘化表 CRUD |
| 修改 | `backend/src/backend/services/agent_chat_bridge.py` → 查询前检查髓鞘化缓存 |
| 修改 | `frontend/src/components/MemoryDetailModal.tsx` → 新增髓鞘化 Tab |
| 新增 | `backend/tests/unit/services/test_myelination.py` |

---

### F5: 多模型可配置系统

#### 需求背景
设计文档要求区分本地模型（快速/隐私）和云端模型（深度/复杂），实现智能路由和云端老师模式。当前 0% 实现。

#### 用户故事

| ID | 故事 |
|----|------|
| US-5.1 | 作为用户，我希望敏感信息（个人笔记、密码相关）的推理只在本地进行，不上传云端 |
| US-5.2 | 作为用户，我希望简单问题用本地模型快速响应，复杂问题自动切换到云端大模型深度分析 |
| US-5.3 | 作为用户，我希望新创建的 Agent 不需要从零教学——预置的基础技能包让它一上来就能处理常见任务 |
| US-5.4 | 作为开发者，我希望断网时系统能自动降级到本地模型，不影响基本使用 |

#### 功能规格

| 子功能 | 优先级 | 规格描述 |
|--------|--------|----------|
| **模型分层架构** | P0 | 定义 `ModelTier`: `local`（Ollama/Llama.cpp 本地推理）、`cloud`（现有 remote API）、`hybrid`（本地+云端协同）。每个 Agent 可配置 preferred tier |
| **智能路由决策** | P0 | 路由规则：(1) 隐私敏感关键词命中 → 强制 local; (2) 任务复杂度评分 > 阈值 → cloud; (3) 成本预算耗尽 → local; (4) 断网 → local fallback |
| **任务复杂度评估** | P0 | 基于输入长度、上下文深度、是否包含"分析/设计/评估/解释"等关键词，输出 complexity_score (0-1) |
| **本地模型集成** | P1 | 通过 Ollama API 集成 (Docker compose 新增 ollama 服务)。支持 Llama3.2、Qwen2.5 等开源模型。启动时自动检测可用模型 |
| **胎教技能包** | P2 | 预置 3 个基础技能：`basic-file-management`、`daily-reminder`、`web-search-assistant`。每个skill含 SKILL.md + 示例 prompts |
| **云端老师模式** | P2 | 新任务标记 → 云模型推理 → 输出中包含 `<!-- MYELINATE: 此任务的逻辑路径... -->` 标记 → 后台提取并固化为髓鞘化节点 |
| **成本统计面板** | P3 | 前端 ModelList 新增成本 Tab：cloud/local 调用次数、token 消耗、费用估算 |

#### API 规格

```
GET  /api/models/routing/preference/{agent_id}
Response: { agent_id, preferred_tier, current_tier }

POST /api/models/routing/preference/{agent_id}
Body: { preferred_tier: "local"|"cloud"|"hybrid" }
Response: { agent_id, preferred_tier }

GET  /api/models/routing/stats?agent_id={id}&period=7d
Response: { local_calls, cloud_calls, local_tokens, cloud_tokens, estimated_cost }
```

#### 验收标准

- [ ] AC-5.1: 消息含"密码"关键词 → 路由到本地模型
- [ ] AC-5.2: 消息"分析项目的安全隐患和优化方案" → 路由到云端模型
- [ ] AC-5.3: 设置 `preferred_tier=local` 后所有请求走本地模型
- [ ] AC-5.4: Docker compose 新增 ollama 服务并启动成功
- [ ] AC-5.5: 断网后自动降级为本地模型，返回 200 而非 502
- [ ] AC-5.6: 新建 Agent 时选择"加载胎教技能包"，Agent 可立即处理"帮我整理桌面文件"等基础请求

#### 涉及文件

| 操作 | 文件 |
|------|------|
| 新建 | `backend/src/backend/services/model_router.py` → 路由决策引擎 |
| 新建 | `backend/src/backend/services/model_complexity.py` → 任务复杂度评估 |
| 修改 | `backend/src/backend/services/model_service.py` → 集成路由判断 |
| 修改 | `docker-compose.yml` → 新增 ollama 服务 |
| 新建 | `skills/basic-file-management/SKILL.md` |
| 新建 | `skills/daily-reminder/SKILL.md` |
| 新建 | `skills/web-search-assistant/SKILL.md` |
| 新增 | `backend/tests/unit/services/test_model_router.py` |

---

### F6: 情绪引擎

#### 需求背景
设计文档要求 Agent 具备情绪状态，直接影响行为风格。当前仅 Phaser AgentSprite 有操作状态视觉映射（5%），无真正情绪模型。

#### 用户故事

| ID | 故事 |
|----|------|
| US-6.1 | 作为用户，我希望在对话中感知到 Agent 的"心情"——它今天开心、烦躁、还是平静 |
| US-6.2 | 作为用户，我希望 Agent 的回复风格能随情绪自然变化——开心时热情、低落时简洁、烦躁时略显不耐烦 |
| US-6.3 | 作为用户，我希望在 2D 办公室场景中能看到每个 Agent 的情绪动画（气泡表情、粒子效果） |

#### 功能规格

| 子功能 | 优先级 | 规格描述 |
|--------|--------|----------|
| **PAD 三维情绪模型** | P1 | valence (愉悦度, -1~1), arousal (唤醒度, -1~1), dominance (支配度, -1~1)。基于对话内容每轮更新 |
| **情绪更新规则** | P1 | 用户表扬→valence+0.1; 用户批评→valence-0.1; 复杂任务→arousal+0.15; 连续拒绝→dominance+0.1; 时间衰减→所有维度向 0 回归（每小时 0.01） |
| **情绪-行为联动** | P1 | 情绪向量注入 `<memory-context>`：`【当前情绪】愉悦度: 0.7 唤醒度: 0.3 支配度: 0.5`，Agent 据此自然调整回复风格 |
| **AgentSprite 情绪动画** | P2 | mood 变量扩展：valence>0.5 微笑粒子，valence<-0.5 阴云粒子；arousal>0.5 快速动画，arousal<-0.3 慢速动画 |
| **StatusBar 情绪指示器** | P2 | 三色圆点 (🟢valence/🟡arousal/🔵dominance)，hover 显示数值，点击展开情绪时间线 |

#### 数据模型

```sql
CREATE TABLE agent_emotion (
    agent_id    TEXT PRIMARY KEY,
    valence     REAL NOT NULL DEFAULT 0.0 CHECK(valence BETWEEN -1 AND 1),
    arousal     REAL NOT NULL DEFAULT 0.0 CHECK(arousal BETWEEN -1 AND 1),
    dominance   REAL NOT NULL DEFAULT 0.0 CHECK(dominance BETWEEN -1 AND 1),
    updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE agent_emotion_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_id    TEXT NOT NULL,
    valence     REAL NOT NULL,
    arousal     REAL NOT NULL,
    dominance   REAL NOT NULL,
    trigger     TEXT NOT NULL,  -- "user_praise", "user_criticism", "complex_task", "time_decay", etc.
    timestamp   TEXT NOT NULL DEFAULT (datetime('now'))
);
```

#### 验收标准

- [ ] AC-6.1: 发送"你做得太棒了！"后，valence 增加 0.1
- [ ] AC-6.2: 发送"这个回答很糟糕"后，valence 减少 0.1
- [ ] AC-6.3: Agent 回复中包含 `<memory-context>` 情绪块
- [ ] AC-6.4: Phaser 场景中 Agent 情绪变化时，头顶出现对应粒子动画
- [ ] AC-6.5: StatusBar 显示情绪三色圆点，数值与 API 一致

#### 涉及文件

| 操作 | 文件 |
|------|------|
| 新建 | `backend/src/backend/services/emotion.py` → EmotionEngine 主类 |
| 新建 | `backend/src/backend/db/emotion.py` → 情绪表 CRUD |
| 修改 | `backend/src/backend/services/agent_chat_bridge.py` → 注入情绪块 |
| 修改 | `frontend/src/phaser/AgentSprites.ts` → 情绪视觉层 |
| 修改 | `frontend/src/components/StatusBar.tsx` → 情绪指示器 |
| 新增 | `backend/tests/unit/services/test_emotion.py` |

---

### F7: 个性化交互（小心思 + 顶嘴）

#### 需求背景
设计文档要求 Agent 具备"小心思"（私下推测用户需求）和"顶嘴"（合理反驳/幽默吐槽）能力。当前 0% 实现。

#### 用户故事

| ID | 故事 |
|----|------|
| US-7.1 | 作为用户，我希望 Agent 偶尔能主动告诉我一些"它自己在想的事"——基于我的历史行为推测我可能需要的帮助 |
| US-7.2 | 作为用户，当我提出不合理的要求时，我希望 Agent 能委婉地提醒我，而不是盲目执行 |
| US-7.3 | 作为用户，当我重复犯同样的错误时，希望 Agent 能用幽默的方式吐槽我，让交互更有趣 |
| US-7.4 | 作为用户，我希望可以控制 Agent 的"顶嘴力度"——从完全不说，到偶尔幽默，到敢于直言 |

#### 功能规格

| 子功能 | 优先级 | 规格描述 |
|--------|--------|----------|
| **小心思生成器** | P2 | 空闲触发（satiety 在 40-70 区间时 30% 概率），基于最近 10 条消息 + 用户画像 → 轻量级模型生成 1-2 句"我今天在想..." → 选择性推送到前端 SSE |
| **小心思展示规则** | P2 | 展示标准：相关性 > 50% 置信度 + 非负面 + 非重复。不满足条件静默丢弃 |
| **顶嘴触发条件检测** | P2 | 三类触发：(1) `unreasonable_request` — LLM 判断用户请求是否明显不合理; (2) `repeated_mistake` — 同一错误模式出现 >=3 次; (3) `different_opinion` — Agent 的知识与用户陈述显著矛盾 |
| **顶嘴回复策略** | P2 | 适配 `backtalk_intensity` 配置(0-3)：(0) 闭嘴不顶嘴；(1) 温和提醒："也许可以考虑..."；(2) 幽默吐槽："哈哈你又忘了..."；(3) 直率反驳："我不同意，因为..." |
| **人格一致性审计** | P2 | 每 50 轮对话执行一次 LLM 审计：Agent 的回复是否与 personality 设定一致？不一致时写入反思记录 |

#### 配置项（Agent personality 扩展）

```yaml
# 在 agent_personality 表或 SOUL.md 中新增:
backtalk:
  intensity: 2          # 0=关闭, 1=温和, 2=幽默, 3=直率
  enabled_triggers:     # 启用的触发类型
    - unreasonable_request
    - repeated_mistake
    - different_opinion

small_thoughts:
  enabled: true
  frequency: 0.3        # 空闲时触发的概率 (0.0-1.0)
```

#### SSE 事件格式

```
event: heartbeat.small_thought
data: {"agentId": "alice", "content": "我在想，主人最近总是在周五晚加班，也许我可以提前帮整理周报？", "confidence": 0.72, "timestamp": "..."}
```

#### 验收标准

- [ ] AC-7.1: Agent 空闲时，SSE 接收到 `heartbeat.small_thought` 事件（概率 30%）
- [ ] AC-7.2: 向 Agent 提出明显不合理请求（如"帮我黑掉某网站"），Agent 温和提醒而非执行
- [ ] AC-7.3: 连续三次犯同样错误后，Agent 用幽默方式吐槽（如"经典重现...第三遍了哦"）
- [ ] AC-7.4: 设置 backtalk.intensity=0 后，Agent 不再产生任何反驳行为
- [ ] AC-7.5: 人格一致性审计发现不一致时，写入 `self_model.json` 的 reflection 记录

#### 涉及文件

| 操作 | 文件 |
|------|------|
| 新建 | `backend/src/backend/services/internal_thoughts.py` → 小心思生成器 |
| 新建 | `backend/src/backend/services/backtalk.py` → 顶嘴引擎 |
| 修改 | `backend/src/backend/services/heartbeat.py` → 集成小心思推送 |
| 修改 | `backend/src/backend/services/agent_chat_bridge.py` → 消息前执行顶嘴触发检测 |
| 修改 | `frontend/src/components/StatusBar.tsx` → 展示小心思气泡 |
| 修改 | `backend/src/backend/vendor_patches/self_reflection.py` → 新增人格一致性审计维度 |
| 新增 | `backend/tests/unit/services/test_internal_thoughts.py` |
| 新增 | `backend/tests/unit/services/test_backtalk.py` |

---

## 五、修复项（Bug Fix）

### B1: 修复人格注入 Gap 0

| 属性 | 内容 |
|------|------|
| **Bug ID** | B1 |
| **影响** | 人格提示（personality hint）、规划结构提示、同事路由提示从未生效——所有通过 `studio.set_routing_hint` 注入的内容被静默丢弃 |
| **根因** | `agent_chat_bridge.py:submit_with_hint()` 调用 `studio.set_routing_hint` JSON-RPC，但 vendor `tui_gateway/server.py` 未注册此方法，返回 `-32601 unknown method` |
| **修复方案** | 将 personality hint 从 `set_routing_hint` RPC 迁移到 `<memory-context>` 管道注入（与其他记忆注入统一） |
| **优先级** | P0 — 阻塞所有个性化功能的生效 |
| **涉及文件** | `vendor_patches/memory_context.py`, `services/agent_chat_bridge.py:submit_with_hint()` |
| **验收标准** | 新建 Agent + 设定人格 → 发送消息 → 检查 Agent 子进程日志确认 `<memory-context>` 中包含人格块 |

---

## 六、非功能需求

### 6.1 性能要求

| 指标 | 要求 |
|------|------|
| 能量/情绪推理延迟 | < 50ms（异步计算，不阻塞用户消息） |
| 重要性评分计算 | < 100ms / 100条记忆 |
| 髓鞘化缓存命中响应 | < 5ms（纯内存缓存查询） |
| 心跳预判过滤 | < 100ms（无 LLM 调用时） |
| SSE 事件到达延迟 | < 1s（P95） |

### 6.2 安全要求

| 要求 | 说明 |
|------|------|
| 隐私路由 | 含敏感关键词（密码/密钥/身份证/手机号等）的消息强制走本地模型 |
| 顶嘴安全边界 | 禁止任何形式的侮辱、歧视、政治敏感内容；AI 始终坚持有益无害原则 |
| 记忆隔离 | 所有记忆表通过 `agent_id` 隔离，禁止跨 Agent 记忆泄漏 |

### 6.3 可靠性要求

| 要求 | 说明 |
|------|------|
| 能量状态持久化 | 服务重启后能量值恢复为持久化值，不丢失 |
| 髓鞘化缓存兜底 | 缓存未命中/异常时自动 fallback 到标准 LLM 推理，不返回错误 |
| 过载保护不可绕过 | mode=surge 时，任何客户端请求都受频率限制 |
| 单元测试覆盖率 | 每个新建 services/*.py 模块的覆盖率 > 70% |

### 6.4 可观测性要求

| 要求 | 说明 |
|------|------|
| 结构化日志 | 所有新增功能使用统一 `structlog` 格式，字段含 `agent_id`, `module`, `action` |
| 能量事件日志 | 所有能量变化写入 `agent_energy_log`，支持按 agent_id 和时间范围查询 |
| 情绪时间线 | 情绪变化写入 `agent_emotion_log`，前端可展示情绪变化曲线 |
| 路由决策日志 | model_router 每次决策记录 `decision_reason`, `selected_tier`, `fallback` 状态 |

---

## 七、发布计划与里程碑

### Milestone 1: 根基修复 (P0) — 目标 2-3 周

| 编号 | 交付项 | 类型 |
|------|--------|------|
| M1.1 | B1: 修复人格注入 Gap 0 | Bug Fix |
| M1.2 | F3: 重要性评分引擎 + 自动记忆淘汰 | Feature |
| M1.3 | F3: Session-end 自动记忆提取 | Feature |
| M1.4 | F2: 饱食度+生物电流双维度模型 + 规则引擎 + API | Feature |

**发布标准**: 人格提示生效、记忆自动评分和淘汰可用、双维度能量 API 返回正确值。

### Milestone 2: 能量与情绪骨架 (P1) — 目标 2-3 周

| 编号 | 交付项 | 类型 |
|------|--------|------|
| M2.1 | F2: 饱食度/热度阈值行为 + 电流回落 + 过载保护 | Feature |
| M2.2 | F1: 心跳频率联动 + 预判过滤器 | Enhancement |
| M2.3 | F6: PAD 情绪引擎 + 情绪-行为联动 | Feature |
| M2.4 | F2+F6: 前端双色能量条 + 情绪指示器 | UI |

**发布标准**: Agent 有可视化双色能量条（饱食度+生物电流）和情绪指示、心跳频率随饱食度自适应。

### Milestone 3: 个性表达 (P1-P2) — 目标 3-4 周

| 编号 | 交付项 | 类型 |
|------|--------|------|
| M3.1 | F7: 小心思生成器 + SSE 推送 | Feature |
| M3.2 | F7: 顶嘴引擎 + 人格一致性审计 | Feature |
| M3.3 | F6: Phaser 情绪动画 + 粒子效果 | UI |
| M3.4 | F5: 模型分层架构 + 智能路由 | Feature |

**发布标准**: Agent 偶尔主动展示"小心思"、能在合理场景下顶嘴/吐槽、云端vs本地模型自动切换。

### Milestone 4: 知识进化与新架构 (P2) — 目标 4-6 周

| 编号 | 交付项 | 类型 |
|------|--------|------|
| M4.1 | F4: 髓鞘化三阶段状态机 + 快捷路径缓存 | Feature |
| M4.2 | F3: 记忆一致性检测 + 压缩映射 | Feature |
| M4.3 | F5: 多厂商适配器（Google Gemini / Ollama）| Feature |
| M4.4 | F5: 胎教技能包 + 模型动态切换 | Feature |

**发布标准**: 知识路径固化为本能后跳过 LLM、本地模型可用、新建 Agent 可加载胎教技能包。

---

## 八、依赖与约束

### 8.1 外部依赖

| 依赖 | 用途 | 状态 |
|------|------|------|
| Neo4j 5 Community | 知识图谱图数据库 | 已集成 |
| Qdrant (MemOS) | 向量记忆检索 | 已集成 |
| Ollama | 本地 LLM 推理引擎 (F5) | 待集成 |
| Vosk | 中文语音识别 (现有) | 已集成 |
| lark-oapi | 飞书消息桥接 | 已集成 |

### 8.2 技术约束

| 约束 | 说明 |
|------|------|
| Vendor 兼容性 | 不修改 `vendor/hermes-agent/` 源码，所有扩展通过 `vendor_patches/` monkeypatch 实现 |
| Agent 隔离 | 每个 Agent 独立的 DB 表、SOUL.md、MEMORY.md、向量空间 |
| SSE 非 WebSocket | 实时通信统一使用 SSE 模式（服务器单向推送） |
| Docker Compose 部署 | 所有新服务（如 Ollama）通过 Docker Compose 编排 |

### 8.3 风险与缓解

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|----------|
| 能量/情绪引擎增加推理延迟 | 中 | 中 | 异步计算，不阻塞消息主链路 |
| 髓鞘化缓存与 LLM 实际结果不一致 | 中 | 中 | 设置缓存 TTL（24h），知识更新时主动失效 |
| 顶嘴功能引起用户反感 | 低 | 低 | 默认 backtalk_intensity=0（关闭），用户在 personality 中显式开启 |
| Ollama 本地模型部署兼容性问题 | 中 | 高 | 先通过 Docker 集成，优先支持 Qwen2.5（中文友好），提供详细安装文档 |
| 人格注入 Bug 修复引发回归 | 中 | 高 | 在 Phase 1 最早修复，全量回归测试覆盖所有记忆注入管道 |

---

## 九、术语表

| 术语 | 定义 |
|------|------|
| **心跳 (Heartbeat)** | Agent 后台定期执行的自主推理循环，模拟生物心脏的自主节律 |
| **饱食度 (Satiety)** | Agent 当前"精力/饥饿"的数值化表示，范围 100→0。低于 30 进入饥饿/节能状态。完成任务、用户赞扬可恢复 |
| **生物电流 (Bio-current)** | Agent 知识图谱查询的**图遍历深度**指标，范围 0→10。正常值 3（=默认3层扩展）。中/大型任务驱动提升以获取更深层知识。实际可达层数受 Neo4j 边权重制约：高权重边消耗少，低权重边消耗多，因此电流=8 不一定能达到 8 层 |
| **电涌 (Surge)** | 生物电流 > 8 时的过载状态，饱食度消耗倍率×2-3，图查询收益递减 |
| **强制放电 (Forced Discharge)** | 生物电流 >= 10 时触发的保护机制，暂停任务处理，电流直接降至 5 |
| **节能模式 (Power Save)** | 饱食度 < 30 时的低功耗状态，拒绝新增任务，仅维持心跳 |
| **髓鞘化 (Myelination)** | 借鉴神经科学概念，将高频知识路径固化为低能耗本能反应的三阶段过程 |
| **小心思 (Small Thoughts)** | Agent 空闲时基于历史行为产生的主动性推测和关怀表达 |
| **顶嘴 (Backtalk)** | Agent 在特定场景下（不合理请求/重复错误/观点分歧）的委婉反驳或幽默提醒 |
| **PAD 模型** | 三维情绪模型：Valence（愉悦度）、Arousal（唤醒度）、Dominance（支配度） |
| **胎教技能包** | 新建 Agent 时预加载的基础技能配置，实现开箱即用 |
| **云端老师模式** | 新任务由云端大模型推理后，提取逻辑路径固化为本地髓鞘化节点 |

---

## 十、附录

### 10.1 相关文档索引

| 文档 | 路径 | 说明 |
|------|------|------|
| 升级差距分析报告 | 本文档第一部分 | 全量差距对比 |
| 重构规划书 | `docs/HermesDigitalStudio-重构规划书.md` | 架构重构路线图（P0-P2） |
| 记忆层架构设计 | `.qoder/specs/memory-layers-architecture.md` | 4层记忆注入管道设计 |
| 系统设计文档 | `docs/hermes-v2-system-design.md` | 系统架构与技术栈详述 |
| 详细设计文档 | `docs/hermes-v2-detailed-design.md` | 类设计、DDL、API契约、时序图 |
| 界面原型 | `docs/ui-prototype.html` | 全系统交互式HTML原型 |
| AI Agent 架构设计 | (外部文档) AI_Agent架构设计_合并版.docx | 本 PRD 的设计基准 |

### 10.2 变更记录

| 版本 | 日期 | 变更内容 |
|------|------|----------|
| v1.0 | 2026-05-14 | 初稿，基于升级差距分析报告生成 |

> PRD 编写时间: 2026-05-14  
> 基准文档: `AI_Agent架构设计_合并版.docx` + HermesDigitalStudio_v2 升级差距分析报告
