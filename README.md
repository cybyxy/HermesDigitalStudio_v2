# HermesDigitalStudio v2

> 下一代 AI Agent 宿主系统 — 赋予 AI Agent 生命感

HermesDigitalStudio v2 不仅是一个 Agent 管理平台。它给每个 Agent 注入**心跳节律、能量管理、持续学习和个性化交互**，让它们像数字生命体一样呼吸、思考、成长和表达。

## 核心特性

| 特性 | 说明 |
|------|------|
| **心跳机制** | Agent 空闲时自主"胡思乱想"——基于知识图谱随机游走产生深度联想 |
| **动态能量管理** | 饱食度 + 生物电流 双维度模型，能量影响推理速度和质量 |
| **四层记忆体系** | 会话记忆 → 持久记忆 → 向量记忆 → 知识图谱，模拟人类认知演化 |
| **髓鞘化知识进化** | 高频知识路径自动固化为"本能"——学习→固化→本能 三阶段状态机 |
| **情绪与个性表达** | PAD 三维情绪模型 + 小心思系统 + 顶嘴引擎，Agent 有自己的脾气 |
| **多 Agent 编排** | @agent 消息转发、对话委托、2D 办公场景可视化 |
| **多模型可配置** | OpenAI / Anthropic / Google Gemini / Ollama 自由切换 |

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
│       ├── api/            # API 路由层 (14 个模块)
│       ├── services/       # 业务逻辑层 (20+ 个模块)
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
