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
3. **@ 空格**：`@<token> <message>`（`@` 与 token 无空格；token 与正文间至少一个空白）。

- `<token>` 中不得含空白、`|`、`@`（与 Bungalow 正则一致）。
- 若 `@` / `/relay` 在**最后一行**且前面还有正文（协作规范：招呼写在 `@` 行之前），目标 Agent 会收到 **`前文 + 空行 + @ 行后的说明`**，便于理解语境。
- 匹配成功后，**不会**把整段原文交给源 Agent 跑一轮；负载投递到目标。若目标会话正忙（`session busy`），会先 `interrupt` 再重试，仍失败则为该同事**新建会话**再提交，避免丢消息。

## 广播

当 `<token>` 为 `所有人` 或 `all`（大小写不敏感）时，向**除当前会话所属 Agent 以外**的每个运行中 Agent 各投递同一 `<message>`。

## Token 解析

在运行中的 Agent 列表中解析 `<token>`（优先级）：

1. `agentId` 精确匹配；
2. `profile` 精确匹配；
3. 以上两项 ASCII 时大小写不敏感；
4. `displayName` 精确匹配；若显示名仅 ASCII，则再尝试大小写不敏感。

未解析到唯一 Agent 时：单播返回 400；广播若无其他 Agent 返回 400。

## 会话选择

- 单播：在目标 Agent 上选取已有会话（`session_id → agent_id` 映射中任一条）；若无，则创建新会话并注册映射，再 `prompt.submit`。
- 广播：对每个目标 Agent 重复上述逻辑（顺序投递）。

## 系统提示注入

每次向某子进程提交前，对该子进程调用 `studio.set_routing_hint`，传入 `_build_studio_peer_routing_hint(mgr, 当前目标 agent_id)`（与单会话直发一致）。

## HTTP 响应（`POST /api/chat/prompt`）

- 普通发送：`relayed: false`，`sessionId` 与请求一致。
- 单播转发：`relayed: true`，`sessionId` 为实际接收模型流的会话；可选 `displayName`。
- 广播：`broadcast: true`，`sessionIds` 为全部投递会话，`relayTargets` 为 `{ sessionId, agentId, displayName }[]`（与 `sessionIds` 顺序一致）。

## 前端

行首解析应与上述规则一致。**凡是「带正文的 handoff」**（`@tok|…` / `@tok …` / 最后一行如此 / `/relay tok|…`），在收到响应前**不要** `switchAgent`：须保持当前「源」`sessionId`；否则 `sessionId` 会变成目标 Tab，后端会判成 source==target。仅「只 @ 同事、无正文」的换 Tab操作可先切换。

若 `agents` 尚未加载导致前端解析不出 `switchTo`，只要正文形状像 handoff，同样禁止预切换，交给后端解析。

收到响应中的 `sessionId` / `relayTargets` 后再 `selectSession` 对齐 SSE。
