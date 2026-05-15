# HermesDigitalStudio v2

> 下一代 AI Agent 宿主系统 — 赋予 AI Agent 生命感

HermesDigitalStudio v2 不仅是一个 Agent 管理平台。它给每个 Agent 注入**心跳节律、能量管理、持续学习和个性化交互**，让它们像数字生命体一样呼吸、思考、成长和表达。

## 核心特性

| 特性 | 说明 | 状态 |
|------|------|------|
| **数字生命体心智架构** | 四层生命体系统：向量感知(Qdrant) → 神经电流(Neo4j) → DNA双链进化 → 行为生成(LLM+空间感知) | ⚠️ 计算层完整，端到端集成验证中 |
| **DNA 双链计算引擎** | 基因型/表现型双链编码，Promoter/Exon/Intron 功能分区，变异性累积与安全边界控制 | ✅ 已实现 |
| **神经电流传导模型** | 饱食度→电压→传导深度→焦耳热 公式驱动，享乐覆盖/情绪桥接/不应期过载保护 | ✅ 已实现 |
| **情绪蓄水池系统** | 指数平滑惯性 + 缓冲区爆发释放 + 稳态回归 + 基线漂移（性格缓慢演化） | ✅ 已实现 |
| **六状态情绪状态机** | CALM → ACTIVATED → PEAK → DECAYING → RECOVERING → REFRACTORY 全路径 | ✅ 已实现 |
| **内驱力博弈引擎** | 生理驱动(饱食度) vs 情绪驱动(PAD) 竞争，情绪可突破生理上限 overclock | ✅ 已实现 |
| **情绪表观遗传** | 长程情绪均值 → DNA 左链变异（≤8%），Promoter 区 70% 概率偏选碱基偏移 | ✅ 已实现 |
| **空间感知与行为生成** | Tiled 地图物品解析 → 环境感知文本 → LLM 动态空闲行为 → 环境→情绪闭环 | ⚠️ 计算层已实现，端到端未验证 |
| **心跳机制** | Agent 空闲时自主"胡思乱想"——基于知识图谱随机游走产生深度联想 | ⚠️ 基础实现可用，饱食度频率联动缺失 |
| **动态能量管理** | 饱食度 + 生物电流 双维度模型，能量影响推理速度和质量 | ✅ 已实现 |
| **四层记忆体系** | 会话记忆 → 持久记忆 → 向量记忆 → 知识图谱，模拟人类认知演化 | ⚠️ 会话/持久/向量/KG 层可用，自动淘汰+会话提取未实现 |
| **髓鞘化知识进化** | 高频知识路径自动固化为"本能"——学习→固化→本能 三阶段状态机 | ✅ 已实现 |
| **多 Agent 编排** | @agent 消息转发、对话委托、2D 办公场景可视化 | ✅ 已实现 |
| **多模型可配置** | OpenAI / Anthropic / Google Gemini / Ollama 自由切换 | ⚠️ 手动切换可用，按任务动态路由未实现 |

## 快速开始

### 前置条件

- Docker + Docker Compose
- Node.js 20+ (前端开发)
- Python 3.11+ (后端开发)
- Hermes CLI 已配置 (`~/.hermes/config.yaml` + `~/.hermes/.env`)

### Docker 启动

```bash
docker-compose up -d
```

服务启动后：
- 前端：http://localhost:5173
- 后端 API：http://localhost:9120
- Neo4j Browser：http://localhost:7474

### 本地开发

```bash
# 后端
cd backend
uv sync
uv run uvicorn src.backend.main:create_app --reload --port 9120

# 前端
cd frontend
npm install
npm run dev
```

## 项目结构

```
HermesDigitalStudio_v2/
├── backend/                # Python 后端 (FastAPI)
│   └── src/backend/
│       ├── api/            # API 路由层 (15 个模块)
│       │   └── mind.py             # 心智架构 API (DNA/情绪/神经/驱动/向量/空间)
│       ├── services/       # 业务逻辑层 (50+ 个模块，含心智架构)
│       │   ├── dna_service.py         # DNA 双链计算引擎
│       │   ├── neural_current.py      # 神经电流传导模型
│       │   ├── emotion_reservoir.py   # 情绪蓄水池系统
│       │   ├── cooling_buffer.py      # 冷却缓冲区
│       │   ├── emotion_state_machine.py # 六状态情绪状态机
│       │   ├── drive_competition.py   # 内驱力博弈引擎
│       │   ├── emotion_epigenetics.py # 情绪表观遗传
│       │   ├── spatial_perception.py  # 空间感知引擎
│       │   ├── vector_memory.py       # 向量感知服务 (3区MemOS分区)
│       │   └── environment_behavior.py # 环境驱动行为生成
│       ├── gateway/        # Agent 子进程管理
│       ├── db/             # DAO 数据访问层 (SQLite)
│       └── core/           # 配置、日志、异常
├── frontend/               # React + Phaser + TypeScript
│   └── src/
│       ├── components/     # UI 组件 (23 个)
│       ├── phaser/         # 2D 办公场景引擎
│       ├── stores/         # Zustand 状态管理 (12 个)
│       ├── api/            # HTTP 客户端
│       └── hooks/          # React Hooks
├── vendor/hermes-agent/    # Hermes Agent CLI (子进程引擎)
├── docs/                   # 设计文档
├── docker-compose.yml      # 容器编排 (Neo4j + Backend + Frontend)
└── skills/                 # Agent 技能包
```

## 文档

| 文档 | 说明 |
|------|------|
| [系统设计文档](docs/hermes-v2-system-design.md) | 完整系统架构和模块设计 |
| [产品需求文档 (PRD)](docs/hermes-v2-prd.md) | 7 大功能模块需求详述 |
| [架构升级报告](docs/hermes-v2-agent-upgrade-report.md) | 当前实现 vs 设计文档差距分析 |
| [重构规划书](docs/HermesDigitalStudio-重构规划书.md) | 代码质量改进路线 |

## 技术栈

**后端**: Python 3.11 · FastAPI · Neo4j 5 · MemOS 2.0 · Vosk STT · SQLite

**前端**: TypeScript · React 19 · Phaser 3.80 · Zustand 5 · Vite 6 · SSE

**基础设施**: Docker Compose · Qdrant (向量库) · sentence-transformers (嵌入)
