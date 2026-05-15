# HermesDigitalStudio 重构规划书

> 版本: v1.0  
> 日期: 2026-05-10  
> 目标: 基于当前项目深度分析，制定可执行的三阶段重构路线图

---

## 一、项目现状概览

### 1.1 总体数据

| 维度 | 数据 |
|------|------|
| 后端 Python | ~28 文件, ~10,100 行 |
| 前端 TS/TSX | ~32 文件, ~12,100 行 |
| 文档 | 2 个 .md |
| 测试覆盖 | 0 |
| CI/CD | 无 |
| Docker | 无 |

### 1.2 技术栈

| 层 | 技术 |
|----|------|
| 后端框架 | FastAPI + Uvicorn (端口 9120) |
| 数据库 | SQLite (WAL 模式) |
| Agent 引擎 | Hermes Agent (subprocess + JSON-RPC-over-stdio) |
| 前端游戏引擎 | Phaser 3.80 (Canvas 渲染) |
| 前端 UI | React 19 (仅 JSX 编译, 无运行时) + DOM API |
| 状态管理 | Zustand 5 |
| 构建工具 | Vite 6 + TypeScript 5.7 |
| 实时通信 | SSE (Server-Sent Events) |
| 消息集成 | 飞书 (lark-oapi) |
| Python 包管理 | uv + hatchling |

### 1.3 当前架构

```
backend/ (三层架构)
  main.py → src/backend/main.py (应用工厂 + lifespan)
    ├── api/          Controller — 11 个路由模块, ~60 个端点
    ├── services/     Service — 15 个文件, 核心业务逻辑
    ├── gateway/      Gateway — 子进程管理 (JSON-RPC-over-stdio)
    ├── db/           DAO — 纯 SQL, SQLite 操作
    ├── models/       DTO — Pydantic 请求/响应模型 (response 近乎空)
    └── hermes_subagent_ext.py — 723 行 monkeypatch 单体

frontend/ (Phaser Mixin + DOM API)
  main.ts → Phaser.Game
    ├── scenes/       UIMainScene (1349行) + 6 个 Mixin 文件
    ├── api/          apiClient.ts (806行, 单体)
    ├── stores/       chatStore.ts (430行, 单体) + officeAgentPoseStore
    ├── components/   15 个 class-based DOM 渲染器
    ├── lib/          10 个工具模块
    ├── phaser/       A* 寻路 + Tiled 地图渲染
    ├── styles/       12 个独立 CSS 文件
    └── types/        共享类型定义
```

---

## 二、核心架构问题

### 2.1 后端问题诊断

| # | 问题 | 涉及文件 | 严重度 |
|---|------|----------|--------|
| 1 | **services/ 层过于臃肿** — agent.py(1001行), settings.py(916行) 等文件过大, 职责边界模糊 | `services/agent.py`, `settings.py` | P0 |
| 2 | **API 层缺少统一异常处理** — 各路由自行 try/catch, 错误响应格式不统一 | 所有 `api/*.py` | P0 |
| 3 | **配置源分散** — settings.py 读 config.yaml, env.py 读 .env, 多处硬编码环境变量名 | `services/settings.py`, `api/env.py`, 各处 `os.environ` | P0 |
| 4 | **DB 无连接池** — 每次调用新建 sqlite3.connect() | `db/connection.py` | P0 |
| 5 | **services 间依赖混乱** — 模块级 `_get_manager()` 单例函数, 隐性循环依赖 | 所有 `services/*.py` | P1 |
| 6 | **Monkeypatch 脆弱** — 723 行单体文件, 7 个独立 patch 混合, vendor 升级困难 | `hermes_subagent_ext.py` | P1 |
| 7 | **Gateway 层三合一** — json_rpc + 子进程管理 + 事件分发 混杂在 850 行文件 | `gateway/gateway.py` | P1 |
| 8 | **飞书逻辑分散** — 4 个文件处理飞书相关功能, 无统一集成目录 | `services/feishu_transcript.py`, `platform_gateway.py`, `gateway_studio_bridge.py`, `extensions/feishu_bridge/` | P1 |
| 9 | **Response Models 缺失** — API 直接返回 dict, 无类型安全 | `models/response/` (空) | P1 |
| 10 | **无任何测试覆盖** | 无 `tests/` | P1 |
| 11 | **无日志体系** — 仅 PID 文件 + stdout 重定向 | 无 `core/logging.py` | P2 |
| 12 | **编排与计划链耦合** — orchestrate.py(612行) 与 plan_chain.py(273行) 逻辑混合 | `services/orchestrate.py`, `plan_chain.py` | P2 |

### 2.2 前端问题诊断

| # | 问题 | 涉及文件 | 严重度 |
|---|------|----------|--------|
| 1 | **Mixin 模式非标准** — `assignMixinPrototype` 运行时复制原型, IDE 无法追踪方法归属 | `UIMainScene.ts` + 6 个 Mixin | P0 |
| 2 | **apiClient.ts 单体** — 806 行包含所有 API 调用, 未按模块拆分 | `api/apiClient.ts` | P0 |
| 3 | **chatStore.ts 单体** — 430 行管理 10+ 域的状态 (sessions/agents/models/channels/skills/plans/modals/feishu/infer) | `stores/chatStore.ts` | P0 |
| 4 | **React 未充分利用** — 仅用于 JSX 编译, 实际渲染通过 class + DOM API 手动操作 | 所有 `components/*.ts` | P1 |
| 5 | **CSS 管理松散** — 12 个独立文件, 无设计 Token, 无 CSS Modules | 所有 `styles/*.css` | P1 |
| 6 | **类型安全不足** — Mixin 模式导致跨文件类型引用脆弱 | `UIMainScene*.ts` | P1 |
| 7 | **无任何测试覆盖** | 无 `tests/` | P1 |
| 8 | **Phaser 与 DOM 渲染冲突** — 同一场景既管理 Canvas 又管理 DOM | `UIMainScene.ts` | P2 |

---

## 三、重构目标

1. **可维护性** — 每个文件 <400 行, 职责单一, 依赖清晰
2. **可测试性** — 各层可独立测试, 覆盖率 >60%
3. **可扩展性** — 新增平台集成(钉钉/企微)只需新增一个目录
4. **类型安全** — 全链路 TypeScript + Pydantic Response Models
5. **开发体验** — React 组件体系, Hot Module Replacement, IDE 类型推断
6. **部署友好** — Docker 容器化, CI/CD 自动化

---

## 四、重构后目录架构

```
HermesDigitalStudio/
├── backend/
│   ├── src/backend/
│   │   ├── core/                        ← 核心基础设施 (新增)
│   │   │   ├── config.py                ← Pydantic BaseSettings 统一配置
│   │   │   ├── exceptions.py            ← AppException 异常体系
│   │   │   ├── error_handlers.py        ← 全局异常处理器
│   │   │   └── di.py                    ← 依赖注入容器
│   │   ├── api/                         ← Controller (保留, 统一异常)
│   │   │   ├── agent.py
│   │   │   ├── chat.py
│   │   │   ├── model.py
│   │   │   ├── plan.py
│   │   │   ├── channels.py
│   │   │   ├── settings.py
│   │   │   ├── skill.py
│   │   │   ├── env.py
│   │   │   ├── health.py
│   │   │   └── platform_gateway.py
│   │   ├── services/                    ← Service 层 (轻量化拆分)
│   │   │   ├── agent.py                 ← ~500 行 (纯 CRUD + Manager 管理)
│   │   │   ├── soul_md.py               ← 新: SOUL.md 解析/写入
│   │   │   ├── profile_scanner.py       ← 新: Profile 扫描/迁移
│   │   │   ├── office_pose.py           ← 新: Office 位姿持久化
│   │   │   ├── chat.py                  ← ~400 行 (会话/SSE)
│   │   │   ├── settings.py              ← ~350 行 (配置 CRUD)
│   │   │   ├── model_config.py          ← 新: 模型/Provider 查询
│   │   │   ├── config_file.py           ← 新: config.yaml 读写
│   │   │   ├── orchestrate.py           ← 重构 (编排逻辑, SSE 外移)
│   │   │   ├── plan.py
│   │   │   ├── plan_chain.py
│   │   │   ├── channel.py
│   │   │   ├── skill.py
│   │   │   ├── session.py
│   │   │   └── handoff_parser.py
│   │   ├── repositories/               ← 新: Repository 存储层
│   │   │   ├── base.py                  ← BaseRepository 抽象
│   │   │   ├── agent_repository.py
│   │   │   ├── plan_repository.py
│   │   │   └── session_repository.py
│   │   ├── gateway/                     ← Gateway 层 (职责拆分)
│   │   │   ├── gateway.py               ← GatewayManager 聚合层
│   │   │   ├── json_rpc.py              ← 新: JSON-RPC 协议封装
│   │   │   ├── process_manager.py       ← 新: 子进程生命周期
│   │   │   ├── event_router.py          ← 新: 事件分发
│   │   │   └── image_utils.py           ← 新: 图片格式检测
│   │   ├── integrations/                ← 新: 统一集成目录
│   │   │   ├── feishu/
│   │   │   │   ├── bridge.py
│   │   │   │   ├── transcript.py
│   │   │   │   ├── gateway.py
│   │   │   │   └── infer_emitter.py
│   │   │   └── __init__.py
│   │   ├── vendor_patches/              ← 新: 友好化 monkeypatch
│   │   │   ├── patcher.py
│   │   │   ├── session_search_patch.py
│   │   │   ├── delegate_tool_patch.py
│   │   │   └── aiagent_patch.py
│   │   ├── models/
│   │   │   ├── request/                 ← 保留
│   │   │   └── response/                ← 补全 (新增每个域的 response models)
│   │   ├── db/
│   │   │   ├── connection.py            ← 精简: 仅连接管理 + Schema
│   │   ├── hermes_subagent_ext.py       ← 精简: Patch 加载器
│   │   ├── hermes_vendor_ref.py         ← 保留
│   │   └── main.py                      ← 修改: 注册全局异常处理器
│   ├── main.py                          ← 保留
│   ├── pyproject.toml
│   └── tests/                           ← 新增
│       ├── conftest.py
│       ├── unit/services/
│       ├── unit/gateway/
│       └── integration/
│
├── frontend/
│   ├── src/
│   │   ├── api/                         ← 按模块拆分
│   │   │   ├── types.ts                 ← 共享类型
│   │   │   ├── agents.ts
│   │   │   ├── chat.ts
│   │   │   ├── settings.ts
│   │   │   ├── models.ts
│   │   │   ├── channels.ts
│   │   │   ├── plans.ts
│   │   │   └── skills.ts
│   │   ├── stores/                      ← 按域拆分
│   │   │   ├── appStore.ts
│   │   │   ├── sessionStore.ts
│   │   │   ├── agentStore.ts
│   │   │   ├── uiStore.ts
│   │   │   ├── channelStore.ts
│   │   │   ├── modelStore.ts
│   │   │   ├── skillStore.ts
│   │   │   ├── feishuStore.ts
│   │   │   ├── planStore.ts
│   │   │   ├── inferStore.ts
│   │   │   └── index.ts                 ← 统一导出
│   │   ├── components/                  ← React 组件 (逐步替换)
│   │   │   ├── AppShell.tsx             ← 主布局
│   │   │   ├── PhaserCanvas.tsx          ← Phaser Game React wrapper
│   │   │   ├── panels/
│   │   │   │   ├── LeftPanel.tsx
│   │   │   │   ├── RightPanel.tsx
│   │   │   │   └── StatusBar.tsx
│   │   │   ├── chat/
│   │   │   │   ├── ChatBubble.tsx
│   │   │   │   ├── ChatMessageList.tsx
│   │   │   │   └── ProcessPanel.tsx
│   │   │   ├── dock/
│   │   │   │   ├── DockPanel.tsx
│   │   │   │   ├── AgentList.tsx
│   │   │   │   ├── TaskList.tsx
│   │   │   │   ├── ChannelList.tsx
│   │   │   │   ├── ModelList.tsx
│   │   │   │   └── SkillList.tsx
│   │   │   ├── modals/
│   │   │   │   ├── ModalPanel.tsx
│   │   │   │   ├── AgentEditForm.tsx
│   │   │   │   ├── ChannelEditForm.tsx
│   │   │   │   ├── ModelEditForm.tsx
│   │   │   │   ├── SkillEditForm.tsx
│   │   │   │   ├── ApprovalModal.tsx
│   │   │   │   ├── ClarifyModal.tsx
│   │   │   │   └── SettingsModal.tsx
│   │   │   ├── plan/
│   │   │   │   └── PlanTimeline.tsx
│   │   │   └── shared/                  ← 通用 UI 原子组件
│   │   │       ├── Button.tsx
│   │   │       ├── Input.tsx
│   │   │       ├── Spinner.tsx
│   │   │       └── Avatar.tsx
│   │   ├── scenes/                      ← 精简 (仅 Phaser Canvas 逻辑)
│   │   │   ├── BootScene.ts             ← 保留
│   │   │   ├── UIMainScene.ts           ← 仅 Phaser 2D 场景逻辑 (从 1349 行降至 ~500 行)
│   │   │   ├── UIMainScene_Office.ts    ← 保留 (办公室渲染 + 人物)
│   │   │   └── UIMainScene_Constants.ts ← 保留
│   │   ├── phaser/                      ← 保留
│   │   ├── lib/                         ← 保留
│   │   ├── ui/                          ← 保留
│   │   ├── styles/
│   │   │   ├── design-tokens.css        ← 设计 Token
│   │   │   ├── globals.css
│   │   │   └── modules/                 ← CSS Modules
│   │   ├── hooks/                       ← 新增: React Hooks
│   │   │   ├── useChatSession.ts
│   │   │   ├── useAgentList.ts
│   │   │   └── useSseEvent.ts
│   │   ├── types/
│   │   │   ├── index.ts                 ← 精简
│   │   │   └── direction.ts
│   │   ├── App.tsx                      ← React 根组件
│   │   └── main.ts                      ← 渲染 React 根组件
│   ├── tests/
│   │   ├── unit/stores/
│   │   ├── unit/api/
│   │   ├── unit/lib/
│   │   └── integration/
│   ├── index.html
│   ├── vite.config.ts
│   ├── tsconfig.json
│   └── package.json
│
├── extensions/                          ← 清理 (已迁移到 backend/integrations/)
├── vendor/hermes-agent/                 ← 保留
├── skills/                              ← 保留
├── docs/                                ← 保留
├── .github/workflows/                   ← 新: CI/CD
├── docker-compose.yml                   ← 新
├── Dockerfile                           ← 新
└── scripts/                             ← 保留
```

相比当前架构的**关键变化**:
- `backend/core/` — 新增基础设施层 (配置/异常/DI)
- `backend/repositories/` — 新增存储层 (替代 db/ DAO)
- `backend/gateway/` — 拆分为 5 个职责单一的文件
- `backend/integrations/` — 新增统一集成目录
- `backend/vendor_patches/` — 新增友好化 patch 系统
- `frontend/components/` — 从 15 个 class 文件变为 React 组件树
- `frontend/stores/` — 从 2 个变为 10+ 个独立 store
- `frontend/api/` — 从 1 个变为 8 个模块
- `frontend/hooks/` — 新增 React Hooks 目录

---

## 五、三阶段实施计划

### 阶段 1 — P0 紧急重构 (约 3 周)

目标: 消除阻碍继续开发的架构问题, 统一数据访问和 API 规范。

#### P0-1: 后端统一异常处理与响应格式

**修改文件:**
- 新建 `backend/src/backend/core/exceptions.py`
- 新建 `backend/src/backend/core/error_handlers.py`
- 修改 `backend/src/backend/main.py` (注册全局异常处理器)
- 修改 `api/*.py` (10 个文件, 去除 try/catch 模版代码)

**方案:**
1. 定义 `AppException` 基类和子类 (`NotFoundError`, `ValidationError`, `GatewayError`), 统一格式: `{"ok": false, "error": {"code": "...", "message": "...", "detail": ...}}`
2. 全局处理器: `@app.exception_handler(AppException)` + Pydantic `RequestValidationError` 处理器
3. 所有 API 路由去除 `try/except HTTPException`, 让异常向上传播

**预期收益:**
- 前端 `apiClient.ts` 统一解析错误格式, 无需为每个端点单独写错误处理
- 新增路由不再重复 try/catch

**风险:** 低。纯新增文件 + 机械替换。

---

#### P0-2: 后端 services/agent.py (1001行) 职责拆分

**修改文件:**
- 保留 `services/agent.py` (~500 行: GatewayManager + agent CRUD)
- 新建 `services/soul_md.py` — SOUL.md 解析/写入
- 新建 `services/profile_scanner.py` — Profile 扫描/legacy migration
- 新建 `services/office_pose.py` — Office 位姿持久化

**方案:**
| 提取方法 | 目标文件 |
|----------|----------|
| `_parse_soul_md()`, `_write_soul_md()` | `soul_md.py` |
| `_startup_agents()`, `_migrate_legacy_runtime_agents()`, `_prune_orphan_legacy_db_rows()` | `profile_scanner.py` |
| `save_office_poses()` | `office_pose.py` |
| Lines 362-530 的 plan 代理函数 | 删除 (已由 services/plan.py 接管) |

**预期收益:** `agent.py` 从 1001 行降至约 500 行。

**风险:** 中。需仔细检查所有 import 关系, 确保无循环依赖。

---

#### P0-3: 后端 services/settings.py (916行) 职责拆分

**修改文件:**
- 保留 `services/settings.py` (~350 行: 配置 CRUD)
- 新建 `services/model_config.py` — 模型列表/Provider 查询/Env 管理
- 新建 `services/config_file.py` — config.yaml 底层读写

**方案:**
| 提取方法 | 目标文件 |
|----------|----------|
| `get_models_list_for_ui()`, `resolve_main_model_base_url()` 等 | `model_config.py` |
| `get_env_vars()`, `put_env_vars()` | `model_config.py` |
| `get_providers_list_for_ui()` 等 provider 相关 | `model_config.py` |
| 纯 config.yaml 文件读写 | `config_file.py` |

**预期收益:** `settings.py` 从 916 行降至约 350 行。

**风险:** 低。纯移出, 依赖关系清晰。

---

#### P0-4: 后端统一配置层

**修改文件:**
- 新建 `backend/src/backend/core/config.py`
- 修改 `services/settings.py`, `api/env.py`, `db/connection.py`, `main.py`

**方案:**
创建 `Settings` 数据类 (Pydantic `BaseSettings`), 聚合所有配置项:
- 数据库路径 / `HERMES_STUDIO_DATA_DIR`
- CORS 来源
- 子进程超时
- 上传大小限制
- 日志级别

**预期收益:** 单一配置源, 不再逐文件硬编码环境变量名。

**风险:** 低。但需细查每个 `os.environ` 调用点。

---

#### P0-5: 后端 DB 连接池

**修改文件:**
- 修改 `backend/src/backend/db/connection.py`

**方案:**
使用 `threading.local()` 实现线程本地连接缓存:
```python
_local = threading.local()

def get_connection() -> sqlite3.Connection:
    if not hasattr(_local, "conn") or _local.conn is None:
        _local.conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        _local.conn.execute("PRAGMA journal_mode=WAL")
        _local.conn.execute("PRAGMA busy_timeout=5000")
        _local.conn.row_factory = sqlite3.Row
    return _local.conn
```

**预期收益:** 减少重复连接创建开销。

**风险:** 低。连接生命周期自然绑定到线程。

---

#### P0-6: 前端 apiClient.ts (806行) 按模块拆分

**修改文件:**
- 删除 `frontend/src/api/apiClient.ts`
- 新建 `api/types.ts`, `agents.ts`, `chat.ts`, `settings.ts`, `models.ts`, `channels.ts`, `plans.ts`, `skills.ts`

**方案:**
按后端 router 域拆分, 每个模块导出该域所有 API 函数。共享类型移至 `api/types.ts`。

**预期收益:** 按模块导入提升 IDE 完成度和 tree-shaking 友好性。

**风险:** 低。纯机械拆分, 每条 import 路径可 grep 替换。

---

#### P0-7: 前端 chatStore.ts (430行) 按域拆分

**修改文件:**
- 新建 `stores/sessionStore.ts`, `agentStore.ts`, `uiStore.ts`, `channelStore.ts`, `modelStore.ts`, `skillStore.ts`, `feishuStore.ts`, `planStore.ts`, `inferStore.ts`, `appStore.ts`
- 新建 `stores/index.ts` (统一导出, 兼容现有 import)

**方案:**
每个域独立为 Zustand store, `appStore` 作为协调层:
```
sessionStore ←→ agentStore ←→ planStore
     ↓               ↓
 uiStore ←→ appStore (协调层) ←→ inferStore
     ↓               ↓
channelStore ←→ modelStore ←→ skillStore
                         ↓
                    feishuStore
```

**预期收益:** 每个 store 30-80 行, 修改一个域不影响其它, 减少合并冲突。

**风险:** 中。需处理跨 store 引用关系。

---

### 阶段 1 验证清单

完成阶段 1 后, 手动回归以下核心流程:
- [ ] 启动后端, Agent 自动启动
- [ ] 前端加载, 办公室地图渲染
- [ ] 创建/编辑/删除 Agent
- [ ] 发送消息, SSE 流式接收
- [ ] Agent 间 @ 转交
- [ ] 模型 CRUD
- [ ] 通道 CRUD
- [ ] SKILL.md 读写
- [ ] Plan artifact 创建/更新/删除

---

### 阶段 2 — P1 架构升级 (约 5-6 周)

目标: 引入现代化架构模式 (DI/Repository/Monkeypatch重构), 前端迁移到 React 体系。

#### P1-1: 后端依赖注入

**修改文件:**
- 新建 `backend/src/backend/core/di.py`
- 修改所有 `services/*.py`, `gateway/*.py`, `main.py`

**方案:**
使用 FastAPI 内建的 `Depends()` 模式, 创建模块级的工厂函数:
```python
# core/di.py
async def provide_gateway_manager() -> GatewayManager:
    return _manager  # 单例

async def provide_agent_service(
    manager: GatewayManager = Depends(provide_gateway_manager),
    db: Connection = Depends(provide_db),
) -> AgentService:
    return AgentService(manager, db)

# api/agent.py 中使用
@router.get("/agents")
async def list_agents(
    service: AgentService = Depends(provide_agent_service),
):
    return await service.list_agents()
```

**预期收益:** 单元测试可直接 mock 依赖, 不再需要 patch 模块级变量。
**风险:** 高。需要重构所有 service 模块, 建议分 3 个子任务逐步推进。

---

#### P1-2: Repository 存储层

**修改文件:**
- 新建 `backend/src/backend/repositories/base.py`, `agent_repository.py`, `plan_repository.py`, `session_repository.py`
- 修改 `db/connection.py` (精简为 Schema 管理)
- 修改所有依赖 DAO 的 services

**方案:**
```python
class BaseRepository(ABC):
    @abstractmethod
    def get(self, id: str) -> dict | None: ...
    @abstractmethod
    def list(self, **filters) -> list[dict]: ...
    @abstractmethod
    def create(self, data: dict) -> str: ...
    @abstractmethod
    def update(self, id: str, data: dict) -> bool: ...
    @abstractmethod
    def delete(self, id: str) -> bool: ...

class AgentRepository(BaseRepository):
    def __init__(self, conn: Connection):
        self._conn = conn
    # ... 从 db/agent.py 迁移 SQL 逻辑
```

**预期收益:** 数据库实现可替换, Service 层测试不需真实数据库。
**风险:** 中。纯 SQL DAO 需逐个迁移, 但接口变化不大。

---

#### P1-3: 前端 React + Phaser 共存架构 (Step 1)

这是最大幅度的前端重构, 分两步实施。

**Step 1 — 共存期:**
1. `index.html` 精简, React 接管 DOM
2. 新建 `AppShell.tsx` — 主布局 (左栏/右栏/底栏/Canvas 区域)
3. 新建 `PhaserCanvas.tsx` — React 组件包装 Phaser Game 实例
4. `UIMainScene` 及其 mixins 仅管理 Phaser Canvas 内部逻辑 (2D 办公室 + 人物精灵 + A* 寻路)
5. 所有 DOM 组件通过 React 渲染, 通过 Zustand store 与 Phaser 通信

**文件清单:**
- 新建 `frontend/src/App.tsx` — React 根组件
- 新建 `frontend/src/components/AppShell.tsx` — 主布局
- 新建 `frontend/src/components/PhaserCanvas.tsx` — Phaser wrapper
- 新建 `frontend/src/components/panels/LeftPanel.tsx`, `RightPanel.tsx`, `StatusBar.tsx`
- 新建 `frontend/src/components/chat/ChatMessageList.tsx`
- 新建 `frontend/src/hooks/useSseEvent.ts`
- 修改 `main.ts` — 渲染 `<App />` 而非纯 Phaser
- 修改 `index.html` — 移除原生 DOM 布局

**架构图:**
```
<App>
  <AppShell>
    <LeftPanel>         ← React (PlanTimeline)
    <PhaserCanvas />    ← Phaser Game (办公室 2D 场景)
    <RightPanel>        ← React (ChatMessageList + ProcessPanel)
    <StatusBar />       ← React (输入框 + 菜单)
    <DockPanel />       ← React (AgentList/TaskList/etc.)
    <ModalLayer />      ← React Portal (所有模态框)
  </AppShell>
</App>
```

**通信机制:**
```
React Component → Zustand Store ↔ Phaser Game Instance
       ↑                               ↑
  API Call                         SSE Event
       ↓                               ↓
  Backend API ←——————————————→ SSE Endpoint
```

---

#### P1-4: CSS 架构规范化

**修改文件:**
- 新建 `frontend/src/styles/design-tokens.css`
- 新建 `frontend/src/styles/globals.css`
- 逐步迁移现有 12 个 CSS 文件为 CSS Modules

**方案:**
1. 定义设计 Token: 提取 `UIMainScene.ts` 中 `COLORS` 常量和各处硬编码色值
2. CSS 自定义属性: `--color-bg: #0c0e12`, `--space-md: 12px`
3. 引入 CSS Modules (Vite 原生支持), 每个组件一个 `.module.css`
4. `design-tokens.css` 在 `index.html` 全局加载, 其余通过组件级导入

**预期收益:** 主题替换只需改 Token 文件, 避免 CSS 选择器冲突。
**风险:** 低。可逐文件替换, 不影响功能。

---

#### P1-5: Monkeypatch 重构

**修改文件:**
- 新建 `backend/src/backend/vendor_patches/patcher.py`
- 新建 `vendor_patches/session_search_patch.py`, `delegate_tool_patch.py`, `aiagent_patch.py`
- 修改 `hermes_subagent_ext.py` → 精简为 patch 加载器

**方案:**
```python
# vendor_patches/patcher.py
class VendorPatch:
    name: str
    enabled: bool = True
    def apply(self) -> None: ...
    def revert(self) -> None: ...

_patches: dict[str, VendorPatch] = {}

def register(patch: VendorPatch) -> None: ...
def apply_all() -> None: ...
def revert_all() -> None: ...
```

每个 patch 独立文件, 实现 `VendorPatch` 接口。

**预期收益:** vendor 升级时只需 disable 对应 patch, 不影响其他。每个 patch 可独立测试。
**风险:** 中。需验证所有 patch 的先后顺序依赖。

---

#### P1-6: Gateway 层重构

**修改文件:**
- 新建 `backend/src/backend/gateway/json_rpc.py`
- 新建 `gateway/process_manager.py`
- 新建 `gateway/event_router.py`
- 新建 `gateway/image_utils.py`
- 修改 `gateway/gateway.py` (精简为 GatewayManager 聚合层)

**方案:**
| 新文件 | 职责 | 从 gateway.py 提取内容 |
|--------|------|------------------------|
| `json_rpc.py` | JSON-RPC 协议: `call()`, `dispatch_inbound()`, 请求 ID 生成, 超时 | ~200 行 |
| `process_manager.py` | 子进程全生命周期: 启动/关闭/存活检查/环境注入 | ~350 行 |
| `event_router.py` | SSE 事件分发: 注册/取消/广播 | ~150 行 |
| `image_utils.py` | 图片格式检测函数 | ~50 行 |
| `gateway.py` | GatewayManager 聚合层 + AgentInfo | ~200 行 |

**预期收益:** 每个文件职责单一, 子进程生命周期管理可独立测试。
**风险:** 中。拆分类时需注意线程锁的粒度, 避免死锁。

---

#### P1-7: 飞书集成解耦

**修改文件:**
- 新建 `backend/src/backend/integrations/feishu/bridge.py`, `transcript.py`, `gateway.py`, `infer_emitter.py`
- 删除 `services/feishu_transcript.py`, `services/platform_gateway.py` (飞书部分), `services/gateway_studio_bridge.py`
- 清理 `extensions/feishu_bridge/`

**预期收益:** 飞书逻辑不再分散在 4 处。未来新增平台集成 (钉钉/企微) 可复用此目录结构。
**风险:** 低。纯文件移动 + 重命名。

---

#### P1-8: Response Models 补全

**修改文件:**
- 新建 `models/response/agent_responses.py`, `chat_responses.py`, `settings_responses.py`, `plan_responses.py`
- 修改对应 API 路由和 Services 返回值类型

**方案:**
为 30+ API 端点定义 Pydantic Response Model, 所有路由返回类型从 `dict` 改为 `ResponseModel`。

**预期收益:** API 文档自动生成更准确, IDE 类型推断提升, 编译时捕获字段错误。
**风险:** 低。模板化工作, 但量较大。

---

#### P1-9: 测试策略建立

**修改文件:**
- 新建 `backend/tests/conftest.py`
- 新建 `backend/tests/unit/services/test_agent.py`
- 新建 `backend/tests/unit/gateway/test_json_rpc.py`
- 新建 `backend/tests/unit/core/test_exceptions.py`
- 新建 `backend/tests/integration/test_health_api.py`
- 新建 `frontend/tests/unit/stores/test_sessionStore.ts`
- 新建 `frontend/tests/unit/lib/test_reasoning.ts`

**后端测试框架:**
- `pytest` + `pytest-asyncio` + `httpx` (TestClient)
- Unit: mock GatewayManager 和 DB
- Integration: FastAPI TestClient + SQLite `:memory:`

**前端测试框架:**
- `vitest` + `@testing-library/react`
- Unit: Zustand store + 纯函数
- Component: React Testing Library

**核心测试场景 (首批 20 个):**
1. 异常类层次结构正确性
2. 错误处理器返回格式一致性
3. AgentService CRUD (mock gateway)
4. ChatService session 创建 (mock gateway)
5. JsonRpcClient 序列化/反序列化
6. 飞书 transcript 解析
7. HandoffParser 各种 @ 语法
8. SSE 生成器超时行为
9. PlanArtifact 解析
10. Reasoning 内容分离
11. Zustand store 状态更新
12. API client 请求构建

**预期收益:** 不再盲目重构, CI 管道可捕获回归。
**风险:** 中。需投入较多时间搭建框架和写初始测试用例。

---

### 阶段 2 验证清单

- [ ] 所有 P0 流程回归 (见阶段 1 清单)
- [ ] DI 容器正常注入, 无循环依赖
- [ ] Repository 层可独立测试
- [ ] React + Phaser 共存, 无渲染冲突
- [ ] Monkeypatch 可按需开关
- [ ] Gateway 层拆分不破坏子进程通信
- [ ] 飞书集成正常运行
- [ ] 20+ 测试用例通过

---

### 阶段 3 — P2 持续优化 (约 3 周)

目标: 基础设施完善和性能优化。

| 任务 | 涉及文件 | 说明 |
|------|----------|------|
| P2-1: CI/CD | `.github/workflows/ci.yml` | lint + test + build |
| P2-2: Docker 化 | `Dockerfile` + `docker-compose.yml` | 后端 + 前端容器 |
| P2-3: 日志体系 | `backend/core/logging.py` | 结构化 JSON 日志, 可配置级别 |
| P2-4: React 组件全量替换 | 见阶段 2 Step 2 | 逐个替换 class-based 组件为 React |
| P2-5: 编排/计划链解耦 | `orchestrate.py` + `plan_chain.py` | 统一事件驱动, SSE 外移 |
| P2-6: 虚拟列表优化 | `ChatMessageList.tsx` | 长会话只渲染可视区域 |

---

## 六、关键风险与缓解措施

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|----------|
| services 拆分后循环依赖 | 中 | 高 | 先画依赖图, 明确分层方向: api→services→repositories→db |
| Monkeypatch 重构破坏子进程 | 中 | 极高 | 用 `HERMES_HDS_SUBAGENT_EXT_DISABLE` feature flag 切换新旧系统 |
| React + Phaser 共存渲染冲突 | 中 | 高 | Step 1 用 `PhaserCanvas` 隔离, Canvas 和 DOM 组件严格分属不同渲染器 |
| 测试基础为 0, 重构后回归 | 高 | 中 | 阶段 1 结束时手动回归所有核心流程 |
| DI 引入后重构范围过大 | 中 | 高 | 分 3 步子任务: (1) core/di.py (2) 单个 service 试点 (3) 全量迁移 |
| SQLite 连接锁 | 低 | 中 | 使用 `busy_timeout=5000` + WAL 模式避免并发写入冲突 |
| 阶段 2 周期过长 | 中 | 中 | P1-P2 之间有自然断点, 可在阶段 1 完成后发布 v1.0 再继续 |

---

## 七、实施建议

### 7.1 开发流程

1. **每个任务独立分支** — 按 `refactor/{task-name}` 命名
2. **渐进式提交** — 每个子任务一个 PR, 尽量小
3. **先测试后重构** — 对于被修改的模块, 先写核心场景的测试用例, 再修改代码
4. **Feature Flag** — 重大重构 (Monkeypatch/Gateway) 使用环境变量开关, 可快速回退
5. **持续回归** — 每次提交后手动跑核心流程

### 7.2 工具推荐

- **后端**: `mypy` (类型检查) + `ruff` (lint/format) + `pytest-cov` (覆盖率)
- **前端**: `eslint` + `prettier` + `vitest` + `@testing-library/react`
- **编辑器**: `TypeScript 严格模式`, `Pydantic VSCode 扩展`

### 7.3 避坑指南

1. 不要同时在 Mixin 模式和 React 模式下修改同一个 UI 组件 — 要么全改, 要么不改
2. services 拆分时先画依赖有向图, 确保无环后再动手写代码
3. Gateway 层重构时, 先提取纯数据类 (Constants/ImageUtils), 再动线程安全的逻辑
4. 前端 apiClient 拆分后, 用 `grep -r` 确认所有旧 import 路径已更新
5. 前端 store 拆分的跨 store 引用, 优先用 `zustand` 的 `getState()` 而非相互 subscribe

---

## 八、附录

### 附录 A: 核心文件行数变化

| 文件 | 当前 | 目标 | 变化 |
|------|------|------|------|
| `services/agent.py` | 1001 | ~500 | -50% |
| `services/settings.py` | 916 | ~350 | -62% |
| `gateway/gateway.py` | 850 | ~200 (4 个新文件各 ~200) | -76% |
| `hermes_subagent_ext.py` | 723 | ~100 | -86% |
| `api/apiClient.ts` | 806 | 8 个文件各 50-150 | -90% (原文件) |
| `stores/chatStore.ts` | 430 | 10 个文件各 30-80 | -86% (原文件) |
| `UIMainScene.ts` | 1349 | ~500 (+ React 组件 ~2000) | -63% (场景) |
| `UIMainScene_Messages.ts` | 1884 | 删除 (分散到 React 组件) | -100% |

### 附录 B: 新增文件汇总

| 阶段 | 新增文件数 | 主要目录 |
|------|-----------|----------|
| 阶段 1 | ~22 | `core/`, `services/` (新), `api/` (模块化) |
| 阶段 2 | ~50 | `repositories/`, `gateway/` (新), `vendor_patches/`, `integrations/`, React `components/` |
| 阶段 3 | ~10 | `.github/`, `docker*`, `core/logging.py` |
| **总计** | **~82** | |

### 附录 C: 关键修改文件路径索引

```
阶段 1 关键文件:
  new: backend/src/backend/core/exceptions.py
  new: backend/src/backend/core/error_handlers.py
  new: backend/src/backend/core/config.py
  new: backend/src/backend/services/soul_md.py
  new: backend/src/backend/services/profile_scanner.py
  new: backend/src/backend/services/office_pose.py
  new: backend/src/backend/services/model_config.py
  new: backend/src/backend/services/config_file.py
  new: frontend/src/api/types.ts, agents.ts, chat.ts, ...
  new: frontend/src/stores/sessionStore.ts, agentStore.ts, ...

阶段 2 关键文件:
  new: backend/src/backend/core/di.py
  new: backend/src/backend/repositories/base.py, agent_repository.py, ...
  new: backend/src/backend/gateway/json_rpc.py, process_manager.py, ...
  new: backend/src/backend/vendor_patches/patcher.py, *patch.py
  new: backend/src/backend/integrations/feishu/*
  new: backend/src/backend/models/response/*
  new: frontend/src/App.tsx, components/AppShell.tsx, PhaserCanvas.tsx
  new: frontend/src/hooks/useSseEvent.ts
  new: frontend/src/styles/design-tokens.css
  new: backend/tests/, frontend/tests/

阶段 3 关键文件:
  new: .github/workflows/ci.yml
  new: Dockerfile, docker-compose.yml
  new: backend/src/backend/core/logging.py
```
