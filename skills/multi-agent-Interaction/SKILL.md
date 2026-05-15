---
name: multi-agent-interaction
description: Hermes Digital Studio 多 Agent 用户消息转发与 @ 行语法（与 HermesBungalow handoff 对齐）
---

# 多 Agent 消息转发（Studio）

## 目标

用户在任一聊天会话中输入带路由前缀的文本时，**后端**将负载投递到对应 Agent 的会话（子进程），并返回实际接收流的 `sessionId`，以便前端 SSE 与历史一致。语法与 HermesBungalow 的 `backend/api/game/handoff_parser.py` 及 `frontend/src/services/gameApi.ts` 保持一致。

## 语法（整段文本，首尾 trim 后匹配）

1. **Legacy relay**：行首 `/relay <token> | <message>`（大小写不敏感）。
2. **@ 竖线**：`@<token> | <message>` 或全角竖线 `@<token> ｜ <message>`。
3. **@ 冒号**：`@<token>：<message>` 或英文冒号 `@<token>: <message>`（从文档/中文输入法复制时常用）。
4. **@ 空格**：`@<token> <message>`（`@` 与 token 无空格；token 与正文间至少一个空白）。

从聊天窗口、Markdown 或网页复制时，行首可能带 **BOM / 零宽字符 / 窄不间断空格**；另常见 **全角 ``＠``（U+FF20）** 与半角 `@` 外观一致但正则匹配不上。后端与前端会做规范化（含 **NFKC**、全角 `@`→`@`、多种 Unicode 空白→空格），避免「看起来对却匹配不上」。若仍出现 `relayed: false` 且正文含 `@`，请看日志 ``handoff not parsed`` 中的 ``text_prefix``。

- `<token>` 中不得含空白、`|`、`@`（与 Bungalow 正则一致）。
- 若 `@` / `/relay` 在**最后一行**且前面还有正文（协作规范：招呼写在 `@` 行之前），目标 Agent 会收到 **`前文 + 空行 + @ 行后的说明`**，便于理解语境。
- 匹配成功后，**不会**把整段原文交给源 Agent 跑一轮；负载投递到目标。若目标会话正忙（`session busy`），会先 `interrupt` 再重试，仍失败则为该同事**新建会话**再提交，避免丢消息。

### 何时算「转发」

- **当前会话所属 Agent ≠ `@token` 解析出的 Agent`**：HTTP 响应里 `relayed: true`，消息进入**对方**子进程与会话。
- **你已经在 `@default`（崽崽）自己的会话里**再发 `@default …`：这是**本会话对话**，响应为 `relayed: false`，**不会**再「转发」给自己。要让「转发」发生，须从**另一位 Agent 的会话**（例如另一 profile 的 Tab）发送该行。

## 广播

当 `<token>` 为 `所有人` 或 `all`（大小写不敏感）时，向**除当前会话所属 Agent 以外**的每个运行中 Agent 各投递同一 `<message>`。

## Token 解析

在运行中的 Agent 列表中解析 `<token>`（优先级）：

1. `agentId` 精确匹配；
2. `profile` 精确匹配；
3. 以上两项 ASCII 时大小写不敏感；
4. `displayName` 精确匹配；若显示名仅 ASCII，则再尝试大小写不敏感。

**同一时刻不存在两个运行中 Agent 共用同一 `agentId` / profile**：`GatewayManager` 以 profile 名为子进程主键（如 `default`、`minimax`）。`@default` 只解析到 **profile 为 `default`** 的那一条；另一条 profile（例如 `minimax`）须用 **`@minimax`**（或该条目的 `displayName` 若唯一）解析。**模型/API 厂商名**（如口头说「迷你马克斯」）**不等于** Hermes 的 profile，除非你在 `agents` 列表里确实看到 `agentId` 为 `default`。

未解析到唯一 Agent 时：单播返回 400；广播若无其他 Agent 返回 400。

## 会话选择

- 单播：在目标 Agent 上选取已有会话（`session_id → agent_id` 映射中任一条）；若无，则创建新会话并注册映射，再 `prompt.submit`。
- 广播：对每个目标 Agent 重复上述逻辑（顺序投递）。

## 系统提示注入

每次向某子进程提交前，对该子进程调用 `studio.set_routing_hint`，传入 `_build_studio_peer_routing_hint(mgr, 当前目标 agent_id)`（与单会话直发一致）。

## 与 HermesBungalow 的差异（为何 Bungalow 里模型写出 `@…` 也会转发）

Bungalow 的聊天**不**直接等价于「浏览器对 Hermes 单次 `prompt.submit`」，而是统一走 **`POST /api/game/agent-chat-orchestrated`**（或 `/run` + SSE），由 `HermesBungalow/backend/server.py` 里的 **`_orchestrate_turn_sync`** 编排：

1. 若用户整段以 **`parse_user_handoff_prefix`** 能解析（行首 `@对方|…` 等），可**跳过主 Agent 模型轮**，直接 **`_run_recursive_peer_invokes`** 投递同伴（与 Studio 的「用户 handoff」类似）。
2. 否则先跑主 Agent 一轮（`HermesBungalow/backend/api/game/agent.py` 的 **`orchestrated_peer_turns_sync`**），拿到 **`primary_reply` 后调用 `parse_hermes_bungalow_invokes`**（按**行**扫 `@target | msg` / `@target msg`，见 Bungalow 的 `handoff_parser.parse_at_handoff_lines` 与前端 `gameApi.parseHermesBungalowInvokes`），再 **`run_recursive_peer_invokes`** 对同伴子进程各跑一轮（可嵌套）。

因此：**同伴模型在 assistant 正文里写的 `@default | …` 会被后端二次解析并真正 `prompt.submit` 到对方会话**；不是「只打印到前端」。

**Studio 编排（与 Bungalow 对齐）**：逻辑在 `backend/services/orchestrate.py`。主 UI 走 **Bungalow 式两段式**（缩短首包阻塞）：

1. **`POST /api/chat/orchestrated/run`** — 请求体与旧版阻塞接口相同（`OrchestratedChatRequest`）；校验会话后立即返回 **`{ ok: true, run_id }`**。
2. **`GET /api/chat/orchestrated/stream?run_id=…`** — **SSE**（`text/event-stream`），推送编排进度与最终结果，直至 **`orch_done`**。

可选 **`GET /api/chat/orchestrated/pending?run_id=…`** — 与 Bungalow `pending` 类似：`{ ok, done, run_id, session_id? }`（未知 `run_id` 时视为 `done: true`）。

**SSE 事件**（`data:` 后为 JSON，`type` 字段区分）：

- `orch_phase`：`phase` 如 `start`、`user_handoff`、`delegations` 等。
- `orch_primary_begin` / `orch_primary_end`：主轮起止（含 `session_id`、`agent_id`、`ok`、`error`）。
- `orch_delegation_start` / `orch_delegation_end`：同伴投递起止。
- `orch_done`：字段 **`result`** 与 **`POST /api/chat/orchestrated`** 成功时的 JSON 体一致（见下节）；失败时 `result.ok === false`，`primary.error` / `error` 含原因。
- `orch_error`：无效 `run_id` 等（如 `unknown_run_id`）。

用户整段若以 `parse_user_handoff_prefix` 命中，则与 **`POST /api/chat/prompt`** 行为一致（内部仍调 `submit_prompt`）；否则主 Agent 等待 ``message.complete`` 后，用 ``parse_assistant_invokes`` 扫描 assistant 全文，再对同伴 ``_submit_relay_payload``（可嵌套，有深度上限）。主轮流式仍经既有 **会话 SSE**；编排控制面为上述 **独立 SSE**。

遗留 **`POST /api/chat/orchestrated`** 仍可用（单请求阻塞至结束，兼容脚本）；**`POST /api/chat/prompt`** 仍可用（调试或外部客户端）。

## HTTP 响应（`POST /api/chat/orchestrated`）

- 用户 handoff / 广播：与下节 ``prompt`` 相同字段（``relayed`` / ``relayTargets`` / ``broadcast`` 等），并带 ``orchestrated: true``、``delegations: []``。
- 普通对话：`relayed: false`，``sessionId`` 为主会话；若模型输出中含可解析的 ``@`` 同伴行，``delegations`` 为树形 ``{ target, ok, sessionId, agentId, displayName, error, reply?, nested }[]``。失败时 HTTP 500，``detail`` 为错误信息。

**与 `orch_done.result` 对齐**：`POST /orchestrated/run` + SSE 结束时，前端用 **`orch_done.result`** 处理广播 / relay / `delegations` 与旧阻塞接口相同。

## HTTP 响应（`POST /api/chat/prompt`）

- 普通发送：`relayed: false`，`sessionId` 与请求一致。
- 单播转发：`relayed: true`，`sessionId` 为实际接收模型流的会话；可选 `displayName`。
- 广播：`broadcast: true`，`sessionIds` 为全部投递会话，`relayTargets` 为 `{ sessionId, agentId, displayName }[]`（与 `sessionIds` 顺序一致）。

## 前端

行首解析应与上述规则一致。**凡是「带正文的 handoff」**（`@tok|…` / `@tok …` / 最后一行如此 / `/relay tok|…`），在收到响应前**不要** `switchAgent`：须保持当前「源」`sessionId`；否则 `sessionId` 会变成目标 Tab，后端会判成 source==target。仅「只 @ 同事、无正文」的换 Tab操作可先切换。

若 `agents` 尚未加载导致前端解析不出 `switchTo`，只要正文形状像 handoff，同样禁止预切换，交给后端解析。

收到 **`orch_done.result`**（或阻塞接口 JSON）中的 `sessionId` / `relayTargets` 后再 `selectSession` 对齐会话 SSE；编排控制面使用独立的 `EventSource` 连接 ``/orchestrated/stream``。
