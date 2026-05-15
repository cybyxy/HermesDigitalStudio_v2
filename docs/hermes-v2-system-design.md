# HermesDigitalStudio v2 — 系统设计文档

> **文档类型**: 系统设计文档 (System Design Document)  
> **版本**: v1.0  
> **日期**: 2026-05-14  
> **关联文档**:
> - [AI Agent 架构升级报告](./hermes-v2-agent-upgrade-report.md)（差距分析）
> - [产品需求文档 (PRD)](./hermes-v2-prd.md)（功能需求详述）
> - [四层记忆体系设计](../.qoder/specs/memory-layers-architecture.md)（运行时注入管道）
> - [重构规划书](./HermesDigitalStudio-重构规划书.md)（质量改进路线）
> - [详细设计文档](./hermes-v2-detailed-design.md)（类/模块/DDL/API/时序图）
> - [界面原型](./ui-prototype.html)（全系统交互式原型）

---

## 一、系统概述

### 1.1 定位

HermesDigitalStudio v2 是一个**下一代 AI Agent 宿主系统**。它不只是一个 Agent 聊天工具——它赋予每个被管理的 Agent **生命节律、自我意识、持续学习能力和个性化交互风格**，让 Agent 从"被动工具"蜕变为"数字生命体"。

### 1.2 核心设计理念

| 理念 | 说明 |
|------|------|
| **数字生命感** | 心跳机制让 Agent "活着"——空闲时自主思考（胡思乱想），有生物体般的能量节律（饱食度+生物电流） |
| **分层记忆体系** | 四层记忆：会话记忆 → 持久记忆 → 知识图谱 → 模式固化，模拟人类从"经历"到"经验"到"本能"的认知演化 |
| **可塑人格** | 每个 Agent 有独立人格（SOUL.md）和个性化交互风格（小心思、顶嘴、情绪表达），与用户建立平等关系 |
| **多模型灵活配置** | 支持 OpenAI / Anthropic / Google Gemini / Ollama 等多厂商模型，Agent 可根据任务动态切换 |

### 1.3 功能全景

```
HermesDigitalStudio v2
├── 01 心跳机制          ─ Agent "活着"的核心引擎
│   ├── 定时推理循环      ─ 基于 Neo4j 随机游走产生"胡思乱想"
│   ├── 空闲感知          ─ 检测 Agent 是否处于交互状态
│   ├── 预判过滤器        ─ 轻量级判定，低价值联想不触发 LLM
│   └── 能量联动          ─ 饱食度/生物电流影响心跳频率
├── 02 动态能量管理      ─ 双维度生物能量模型
│   ├── 饱食度 (Satiety) ─ 0-100，代表"生理能量"（吃、睡、恢复）
│   ├── 生物电流 (BioCurrent) ─ 0-10，代表"精神负荷"（多任务、深度思考）
│   ├── 阈值行为          ─ 饥饿状态下响应变慢，过载状态下推理质量下降
│   └── 回落/保护机制     ─ 空闲时渐恢复，电流>8触发过载保护
├── 03 知识管理体系      ─ 三层知识图谱 + 髓鞘化进化
│   ├── 知识图谱 (KG)     ─ LLM抽取图 + state.db共现图 + Neo4j度中心性
│   ├── 知识固化          ─ 重要性评分 → 自动淘汰 → 会话提取
│   └── 髓鞘化            ─ 学习→固化→本能 三阶段状态机
├── 04 多模型可配置      ─ 灵活切换 LLM 提供方
│   ├── 多厂商适配        ─ OpenAI / Anthropic / Google / Ollama
│   ├── 模型管理界面      ─ 前端 CRUD 面板
│   └── 动态切换          ─ 按任务/成本自动选择模型
├── 05 情绪与交互        ─ 个性表达的"灵魂"
│   ├── 情绪引擎          ─ PAD 三维情绪模型
│   ├── 小心思系统        ─ 基于历史行为预测 + 能量状态调整反应
│   ├── 顶嘴功能          ─ 委婉提醒 / 幽默吐槽 / 事实反驳
│   └── 自我模型          ─ 偏好/能力/行为模式 + 自我反思
├── 06 多 Agent 协作     ─ 办公场景管理
│   ├── 2D 办公场景       ─ Phaser 引擎驱动的可视化场景
│   ├── Agent 编排        ─ @agent 消息转发、对话委托
│   ├── 通道管理          ─ 飞书 / Telegram / Discord 消息平台集成
│   └── 技能管理          ─ SKILL.md 机制，可动态加载 Agent 能力
└── 07 平台基础设施
    ├── 配置中心          ─ ~/.hermes/config.yaml 统一管理
    ├── 语音识别          ─ Vosk 离线中文语音转文字
    └── 媒体管理          ─ 图片/音频/文件实时传输
```

---

## 二、系统架构

### 2.1 架构总览

```
┌─────────────────────────────────────────────────────────────────────┐
│                          Frontend (React 19 + Phaser 3.80)          │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────────────────┐│
│  │ UI Panels │  │ Zustand  │  │ SSE Hook │  │ Phaser 2D Office     ││
│  │ (23 comp) │  │ (12 stores) │  │ (实时流)  │  │ Scene (A* 寻路)     ││
│  └─────┬─────┘  └─────┬─────┘  └────┬─────┘  └──────────┬───────────┘│
│        │              │              │                    │           │
└────────┼──────────────┼──────────────┼────────────────────┼───────────┘
         │              │              │                    │
    HTTP/SSE         State Sync    Event Stream         Canvas
         │              │              │                    │
┌────────┼──────────────┼──────────────┼────────────────────┼───────────┐
│        ▼              ▼              ▼                    ▼           │
│                      Backend (Python 3.11 + FastAPI)                  │
│  ┌──────────────────────────────────────────────────────────────────┐│
│  │                      API Layer (14 routers)                       ││
│  │  /chat /agent /model /settings /env /channels /skill /plan ...   ││
│  └──────────────────────────────┬───────────────────────────────────┘│
│                                 │                                     │
│  ┌──────────────────────────────▼───────────────────────────────────┐│
│  │                   Service Layer (20+ modules)                     ││
│  │  agent  │ orchestrate │ chat │ heartbeat │ neo4j │ mem_os │ ...  ││
│  └──────┬──────────────────────────────┬────────────────────────────┘│
│         │                              │                              │
│  ┌──────▼──────────┐  ┌────────────────▼──────────────────────────┐  │
│  │  Gateway Manager │  │          DAO Layer (SQLite)               │  │
│  │  (子进程管理)     │  │  agent │ memory │ plan │ knowledge        │  │
│  │  JSON-RPC/stdio  │  └──────────────────────────────────────────┘  │
│  └──────┬───────────┘                                                │
│         │                                                            │
└─────────┼────────────────────────────────────────────────────────────┘
          │
    ┌─────▼───────────────────────────────────────────┐
    │         Hermes Agent 子进程 (vendor/)             │
    │  ┌─────────────────────────────────────────────┐ │
    │  │  Hermes Agent Runtime                       │ │
    │  │  ┌─────────┐  ┌──────────┐  ┌───────────┐  │ │
    │  │  │ LLM API │  │ Memory   │  │ Tool Mgr  │  │ │
    │  │  │ Client  │  │ Manager  │  │           │  │ │
    │  │  └─────────┘  └──────────┘  └───────────┘  │ │
    │  │  ┌──────────────────────────────────────┐   │ │
    │  │  │  <memory-context> 注入管道           │   │ │
    │  │  │  MemoryManager + StreamingScrubber   │   │ │
    │  │  └──────────────────────────────────────┘   │ │
    │  └─────────────────────────────────────────────┘ │
    └──────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│                      External Services                               │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────────────────┐│
│  │  Neo4j 5 │  │  Qdrant  │  │  Vosk    │  │  LLM Providers       ││
│  │ (图谱DB) │  │ (向量DB) │  │ (语音识别)│  │  OpenAI/Anthropic/...││
│  └──────────┘  └──────────┘  └──────────┘  └──────────────────────┘│
└─────────────────────────────────────────────────────────────────────┘
```

### 2.2 分层架构详解

| 层 | 目录 | 职责 |
|----|------|------|
| **API 层** | `backend/src/backend/api/` | HTTP 端点定义，请求验证，响应格式化。14 个路由模块，按领域拆分 |
| **服务层** | `backend/src/backend/services/` | 核心业务逻辑。Agent 生命周期、编排引擎、心跳、Neo4j、MemOS、记忆等 |
| **网关层** | `backend/src/backend/gateway/` | Agent 子进程管理。JSON-RPC-over-stdio 通信，消息路由，会话映射 |
| **DAO 层** | `backend/src/backend/db/` | SQLite 数据访问。Agent 配置、计划、知识图谱、记忆的 CRUD 封装 |
| **核心层** | `backend/src/backend/core/` | 配置管理、结构化日志、异常体系、DI 容器 |
| **模型层** | `backend/src/backend/models/` | Pydantic DTO，定义请求/响应数据结构 |

### 2.3 核心数据流

#### 对话流程

```
用户输入 → ChatPanel.tsx (React)
  → POST /api/chat/sessions/{sid}/completions
  → chat.py: 构建 context、检索记忆
  → agent_chat_bridge.py: submit_with_hint()
  → GatewayManager: 路由到 Agent 子进程
  → Agent JSON-RPC: 处理 + LLM 推理
  → SSE 事件流返回:
     ├── message.delta    → 前端逐字渲染
     ├── message.thinking → 前端显示推理过程
     ├── message.complete → 标注完成
     ├── tool.start/end   → 前端工具面板更新
     └── heartbeat.event  → 前端状态栏更新
  → 对话结束后:
     ├── orchestrate.py: 处理 @agent 转发
     ├── mem_os_service: 写入向量记忆
     └── knowledge.py: 更新知识图谱节点/边
```

#### 心跳推理流程

```
asyncio 定时器 (heartbeat.py)
  → 检查 Agent 空闲 + satiety/bio_current
  → Neo4j 随机游走 (neo4j_service.py)
    → 从当前 Agent 的知识图谱随机选取节点
    → 按边权重游走 3-5 步
    → 收集沿途节点信息
  → 预判过滤器 (heartbeat_prefilter.py)
    → 计算信息熵/新颖度
    → 低于阈值 → 跳过 LLM，记录跳过日志
    → 高于阈值 → 继续
  → LLM 推理
    → 提示词：基于已知信息做深度联想
    → 输出：有价值的洞察/疑问/建议
  → SSE 推送 → 前端气泡显示 "💭 {agent} 的思考"
  → 如果连接飞书 → 发布消息到飞书群
```

#### 记忆注入流程

```
用户发送消息时 (agent_chat_bridge.py):
  → build_turn_memory_context() 构建 <memory-context>:
     ├── personality_hint (来自 agent_personality 表)
     ├── peer_routing (联系人路由提示)
     ├── recent_session_summary (最近 3 个会话摘要)
     ├── all_session_titles (所有历史会话标题)
     ├── vector_memories (MemOS 向量搜索结果，如果用户提到未见内容)
     ├── knowledge_graph (知识图谱邻居节点)
     ├── compression_map (上次压缩的追踪 ID)
     └── conversation_state (本次会话状态)
  → 注入到 Agent 子进程的 System Prompt 管道
  → Agent 在推理时自动引用这些记忆
  → StreamingScrubber 确保用户看不到注入内容
```

---

## 三、核心模块设计

### 3.1 Agent 生命周期管理

```
[创建]
  agent.py: create_agent(name, profile)
    → GatewayManager: 启动 Hermes Agent 子进程
    → AgentAvatarDAO: 写入配置 (avatar, gender, model)
    → AgentPersonalityDAO: 初始化人格模板
    → agent_bootstrap.py: 启动引导
        → Step 1: MemOS 向量回忆
        → Step 2: state.db KG → Neo4j 导入
        → Step 3: Neo4j 剪枝 + 缓存图谱

[运行中]
  AgentSessionDAO: 绑定 session → 跟踪 last_used_at
  heartbeat.py: 定期心跳推理
  chat.py: 消息收发、SSE 流
  orchestrate.py: 多 Agent 编排

[关闭]
  agent.py: close_agent()
    → GatewayManager: 关闭子进程
    → 清理 MOS 缓存 (remove_mos_for_agent())
    → 停止心跳循环
    → 保存最新状态到 DB
```

### 3.2 知识图谱三路径设计

```
路径 1: LLM 抽取图 (knowledge_graph.py)
  记忆条目 → LLM extract_entities_relations() → kgnode_*/kgedge_* SQLite 表
  ├── build_graph_incremental(): 增量构建
  ├── query_knowledge_graph(): 邻居查询 → 注入 <memory-context>
  └── build_mermaid_graph(): Mermaid 可视化

路径 2: state.db 共现图 (agent_bootstrap.py)
  Agent 启动时: KnowledgeNodeDAO/KnowledgeEdgeDAO → Neo4j 批量导入
  └── 提供度中心性计算基础

路径 3: Neo4j 结构分析 (neo4j_service.py)
  ├── import_graph(): 批量导入到 Neo4j
  ├── random_walk(): 心跳游走 → 产生联想种子
  ├── prune_irrelevant(): 剪除低相关度节点
  └── degree_centrality(): 度中心性排序

三路径融合:
  共同汇聚到 Neo4j → 度中心性 + 节点类型标记区分来源
  → <memory-context> 注入时按来源权重混合检索
```

### 3.3 四层记忆体系

```
Layer 1: 会话记忆 (Session)
├── 存储: state.db sessions 表 + session_titles
├── 内容: 每轮对话的完整记录
├── 生命周期: Session 内可变，会话结束压缩 → 持久记忆
└── 注入方式: <memory-context> 中的 recent_summaries + session_titles

Layer 2: 持久记忆 (Persistent)
├── 存储: SOUL.md (人格，frozen) + MEMORY.md (事实，可更新)
├── 内容: Agent 的身份设定、关键事实、经验积累
├── 生命周期: 跨 Session 持久
└── 注入方式: System Prompt 的 SOUL.md + MEMORY.md snapshot

Layer 3: 向量记忆 (Vector)
├── 存储: MemOS/Qdrant (text-embedding-3-small, chunk_size=512, overlap=128)
├── 内容: 语义可检索的历史对话/文档片段
├── 生命周期: 永久 (重要性评分 → 自动淘汰)
└── 注入方式: 用户提及未见内容时自动向量检索 → 注入 <memory-context>

Layer 4: 结构化记忆 (Knowledge Graph)
├── 存储: SQLite kgnode_*/kgedge_* + Neo4j 图数据库
├── 内容: 实体关系、概念图谱、技能依赖
├── 生命周期: 永久 (剪枝剔除低关联度节点)
└── 注入方式: 按对话主题匹配 → 注入邻居节点信息到 <memory-context>
```

### 3.4 髓鞘化进化 (Myelination)

**设计文档中的核心概念**: 类比生物神经髓鞘化——高频使用的知识路径应"固化"为默认反应，无需 LLM 推理即可快速调用。

```
三阶段状态机:

  ┌──────────────┐    frequency > 3    ┌──────────────┐
  │   学习阶段   │ ──────────────────→ │   固化阶段   │
  │  (Learning)  │                     │  (Consolid-  │
  │  每次 LLM    │                     │   ation)     │
  │  推理生成    │                     │   建立索引   │
  └──────────────┘                     └──────┬───────┘
                                              │
                                         frequency > 10
                                              │
                                              ▼
                                       ┌──────────────┐
                                       │   本能阶段   │
                                       │  (Instinct)  │
                                       │  缓存命中    │
                                       │  跳过 LLM    │
                                       └──────────────┘

实现:
  快捷路径缓存 (myelination.py):
    ├── query → hash → cache lookup
    ├── 命中 → 直接返回 (算力降低 90%)
    ├── 未命中 → LLM 推理 → 写入缓存
    └── 知识更新 → 主动失效对应缓存 (TTL + 版本号)
```

### 3.5 多 Agent 编排 (Bungalow 模式)

```
消息流:

  用户 → Agent A
    ↓
  orchestrate.py 解析消息
    ├── 无 @ 标记 → Agent A 直接回复
    ├── @AgentB → Agent A 发送 delegation 事件
    │   → GatewayManager 路由到 Agent B
    │   → Agent B 回复 → 返回给 Agent A
    │   → Agent A 整合回复
    └── /relay 广播 → 所有活跃 Agent 收到

  转发控制:
    ├── delegate_gate: 防止无限递归 (max_depth=3)
    ├── handoff_parser: 解析 @agent | message 格式
    └── control_stream: 编排状态追踪
```

### 3.6 前端 2D 办公场景

```
Phaser 3.80 Canvas (z-index: 0)
  ├── OfficeScene.ts: 主场景管理
  ├── OfficeMap.ts: 地图渲染 (瓦片地图)
  ├── AgentSprites.ts: Agent 精灵管理 (站位 / 走动 / 跑步)
  ├── AgentMovement.ts: 移动动画 (A* 寻路)
  ├── EncounterManager.ts: 相遇交互 (Agent 碰撞 → 社交事件)
  └── bungalowOfficeLoader.ts: 办公室地图资源加载

React UI 覆盖层 (z-index: 1+)
  ├── AppShell.tsx: 主布局 (3 面板)
  ├── ChatPanel.tsx: 聊天面板 (浮于 Canvas 右侧)
  ├── AgentList.tsx: Agent 名册 (浮于 Canvas 左侧)
  ├── StatusBar.tsx: 状态栏 (底部)
  └── DockPanel.tsx: 可停靠面板 (右下)

双向通信:
  React → Phaser: 通过 Zustand stores (officeAgentPoseStore)
  Phaser → React: 通过 Zustand stores + CustomEvent
```

---

## 四、数据存储设计

### 4.1 存储分层

```
┌─────────────────────────────────────────────────────────┐
│  存储层                                                  │
├─────────────┬─────────────┬─────────────┬───────────────┤
│   SQLite    │    Neo4j    │   Qdrant    │   File System │
│ (关系/配置)  │  (知识图谱)  │  (向量记忆) │  (文本/状态)  │
├─────────────┼─────────────┼─────────────┼───────────────┤
│ Studio DB   │ Graph Nodes │ text-embed  │ SOUL.md       │
│ Agent 配置  │ Relations   │ ding-3-     │ MEMORY.md     │
│ Session 链  │ Centrality  │ small       │ USER.md       │
│ Plan 工件   │ Walk Paths  │ 512-chunk   │ state.db      │
│ 知识节点/边  │             │ 128-overlap │ sessions/     │
└─────────────┴─────────────┴─────────────┴───────────────┘
```

### 4.2 核心数据表 (HermesDigitalStudio.db)

| 表名 | 用途 | 关键字段 |
|------|------|----------|
| `agent_avatars` | Agent 外观和模型配置 | agent_id, avatar, gender, office_x/y, facing, model, model_provider, model_base_url |
| `agent_personality` | Agent 人格设定 | agent_id, personality, catchphrases, memes |
| `agent_sessions` | Session 绑定和链 | agent_id, session_id, session_key, parent_session_id, is_active, last_used_at |
| `plan_artifacts` | 计划工件 | plan_id, agent_id, title, status, steps_count |
| `plan_artifact_steps` | 计划步骤 | step_id, plan_id, title, status, order, result |
| `kgnode_{agent_id}` | 知识图谱节点 | id, label, type, summary, created_at |
| `kgedge_{agent_id}` | 知识图谱边 | id, source_id, target_id, relation, evidence |
| `smry_{agent_id}` | 会话摘要缓存 | session_id, summary, generated_at |
| `cmap_{agent_id}` | 压缩映射表 | compressed_id, original_session_id, compressed_at |

### 4.3 Neo4j 图数据库

- **版本**: Neo4j 5 Community Edition
- **连接**: `bolt://localhost:7687`
- **模型**: 每个 Agent 独立的子图，通过关系类型 `BELONGS_TO` 连接
- **节点**: 知识实体（标签、类型、来源路径）
- **边**: 实体间关系（来源、权重）
- **操作**: `import_graph()` / `random_walk()` / `degree_centrality()` / `prune_irrelevant()`

### 4.4 Qdrant 向量库 (通过 MemOS)

- **引擎**: text-embedding-3-small (384 维)
- **分块**: chunk_size=512, chunk_overlap=128
- **距离**: Cosine 距离
- **存储路径**: `.memos/qdrant/{agent_id}/`
- **生命周期**: 由 `MemOSService` 单例管理

---

## 五、技术栈

### 5.1 后端

| 技术 | 版本 | 用途 |
|------|------|------|
| **Python** | 3.11+ | 主语言 |
| **FastAPI** | 0.115+ | Web 框架 |
| **Uvicorn** | 0.34+ | ASGI 服务器 |
| **Neo4j Driver** | 5.x | 图数据库客户端 |
| **MemOS** | 2.0.15 | 记忆操作系统 (向量检索) |
| **sentence-transformers** | all-MiniLM-L6-v2 | 本地嵌入模型 |
| **Vosk** | 0.3.45+ | 离线语音识别 |
| **Hermes Agent CLI** | vendor/ | Agent 执行引擎 |

### 5.2 前端

| 技术 | 版本 | 用途 |
|------|------|------|
| **TypeScript** | 5.7 | 主语言 |
| **React** | 19.x | UI 框架 |
| **Phaser** | 3.80 | 2D 游戏引擎 |
| **Zustand** | 5.x | 状态管理 |
| **Vite** | 6.x | 构建工具 |
| **SSE** | 原生 Events | 实时数据流 |

### 5.3 基础设施

| 技术 | 用途 |
|------|------|
| **Docker Compose** | 容器编排 (Neo4j + Backend + Frontend) |
| **SQLite** | 配置和关系数据存储 |
| **YAML** | 用户配置 (~/.hermes/config.yaml) |

---

## 六、API 设计

### 6.1 主要端点一览

| 方法 | 路径 | 用途 |
|------|------|------|
| `GET` | `/api/chat/agents` | 列出所有 Agent |
| `POST` | `/api/chat/agents` | 创建 Agent |
| `GET` | `/api/chat/agents/{id}/memory` | 获取 Agent 记忆详情 |
| `GET` | `/api/chat/agents/{id}/memory/dual-stats` | 获取双重记忆统计数据 |
| `POST` | `/api/chat/sessions` | 创建会话 |
| `POST` | `/api/chat/sessions/{id}/completions` | 发送消息 (SSE 流式响应) |
| `PUT` | `/api/chat/sessions/{id}/approve` | 批准 Agent 操作 |
| `GET` | `/api/agent/poses/{id}` | 获取办公室姿态 |
| `POST` | `/api/agent/poses/{id}` | 更新办公室姿态 |
| `GET` | `/api/models` | 列出模型配置 |
| `POST` | `/api/models` | 添加模型提供方 |
| `GET` | `/api/memory/agents/{id}/search` | 向量记忆搜索 |
| `GET` | `/api/settings` | 获取全局配置 |
| `POST` | `/api/settings` | 更新全局配置 |
| `GET` | `/api/channels` | 列出消息通道 |
| `GET` | `/api/skills` | 列出可用技能 |
| `GET` | `/api/plans` | 列出计划工件 |

### 6.2 实时事件流 (SSE)

```
event: message.delta
data: {"session_id": "...", "text": "..."}

event: message.thinking
data: {"session_id": "...", "thinking": "..."}

event: message.complete
data: {"session_id": "...", "text": "...", "usage": {...}}

event: heartbeat.event
data: {"agent_id": "...", "snippet": "...", "satiety": 75, "bio_current": 3}

event: agent.social
data: {"agent_id": "...", "message": "...", "from_agent_id": "..."}

event: tool.start / tool.progress / tool.end
data: {"session_id": "...", "tool_name": "...", "input": {...}, "output": {...}}
```

---

## 七、部署架构

### 7.1 Docker Compose

```yaml
services:
  neo4j:
    image: neo4j:5-community
    ports: ["7474:7474", "7687:7687"]
    volumes:
      - neo4j_data:/data
      - neo4j_logs:/logs

  backend:
    build: backend/
    ports: ["9120:9120"]
    depends_on: [neo4j]
    volumes:
      - ~/.hermes:/root/.hermes           # Agent 配置和状态
      - backend/src:/app/src              # 源码挂载 (热重载)
    environment:
      - NEO4J_URI=bolt://neo4j:7687

  frontend:
    build: frontend/
    ports: ["5173:5173"]
    depends_on: [backend]
```

### 7.2 环境依赖

| 组件 | 要求 |
|------|------|
| Docker + Docker Compose | 容器运行 |
| Neo4j 5 Community | 知识图谱存储 (或使用嵌入式) |
| Python 3.11+ | 本地开发 |
| Node.js 20+ | 前端开发和构建 |
| `~/.hermes/config.yaml` | Agent 配置 (由 Hermes CLI 初始化) |
| `~/.hermes/.env` | LLM API Keys |

---

## 八、安全设计

| 方面 | 措施 |
|------|------|
| **API Key 管理** | 通过 `~/.hermes/.env` 统一管理，后端通过 hermes_cli 加载，不写入数据库 |
| **CSS 隔离** | UI 重用 `ModalPanel` 统一组件，主场景 EventSystem DOM 容器隔离 |
| **XML 过滤** | 前端聊天消息通过 `stripXmlTags()` 过滤，防止 XSS 注入 |
| **CORS** | 仅允许 `localhost:5173`（开发模式），生产部署通过 Nginx 反向代理 |

---

## 九、测试策略

| 层 | 测试方式 |
|----|----------|
| **单元测试** | Python `pytest`: DAO 层、Service 层独立函数（计划工件 CRUD、记忆评分、预判过滤器） |
| **核心模块测试** | 重点覆盖 `agent_bootstrap.py`（引导恢复流程）、`orchestrate.py`（编排逻辑）、`heartbeat.py`（定时循环） |
| **数据库测试** | 临时 `test_*.db` 文件，每个测试函数独立数据库 |
| **前端测试** | `data-testid` 属性 + 单一文件内多个 export 实现可测试性 |
| **集成测试** | Docker Compose 启动全套服务，HTTP 客户端 (httpx) 模拟用户操作 |

---

## 十、文档索引

| 文档 | 路径 | 用途 |
|------|------|------|
| 系统设计文档 (本文) | `docs/hermes-v2-system-design.md` | 系统架构和详细设计 |
| 产品需求文档 | `docs/hermes-v2-prd.md` | 7 大功能模块的需求详述 |
| 架构升级报告 | `docs/hermes-v2-agent-upgrade-report.md` | 当前实现 vs 设计文档差距分析 |
| 重构规划书 | `docs/HermesDigitalStudio-重构规划书.md` | 代码质量改进路线 |
| 四层记忆体系 | `.qoder/specs/memory-layers-architecture.md` | 运行时记忆注入管道设计 |
| 前端重构 spec | `.qoder/specs/refactor-frontend-to-v2.md` | 前端架构重构详细步骤 |
| 场景目录重构 | `.qoder/specs/refactor-scenes-directory.md` | Phaser 场景代码整改方案 |
| 详细设计文档 | `docs/hermes-v2-detailed-design.md` | 类设计、DDL、API契约、时序图、组件树 |
| 界面原型 | `docs/ui-prototype.html` | 全系统交互式HTML原型 |
