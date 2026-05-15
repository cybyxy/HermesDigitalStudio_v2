/** 与 docs/hermes-gateway-rpc.md 对齐的常量与类型（抽离子集）。 */

export const JSONRPC_VERSION = "2.0" as const;

/** 下行 event.params.type（常用子集）。 */
export type HermesEventType =
  | "gateway.ready"
  | "session.info"
  | "message.start"
  | "message.delta"
  | "message.complete"
  | "thinking.delta"
  | "reasoning.delta"
  | "tool.generating"
  | "tool.progress"
  | "tool.complete"
  | "approval.request"
  | "clarify.request"
  | "error"
  | "status.update"
  | "skin.changed";

export interface HermesEventParams {
  type: HermesEventType | string;
  session_id?: string;
  payload?: Record<string, unknown>;
}

export interface JsonRpcRequest {
  jsonrpc: typeof JSONRPC_VERSION;
  id: number;
  method: string;
  params?: Record<string, unknown>;
}

export interface JsonRpcResult<T = unknown> {
  jsonrpc: typeof JSONRPC_VERSION;
  id: number;
  result: T;
}

export interface JsonRpcErrorBody {
  code: number;
  message: string;
}

export interface JsonRpcError {
  jsonrpc: typeof JSONRPC_VERSION;
  id: number;
  error: JsonRpcErrorBody;
}

export interface JsonRpcEventNotification {
  jsonrpc: typeof JSONRPC_VERSION;
  method: "event";
  params: HermesEventParams;
}
