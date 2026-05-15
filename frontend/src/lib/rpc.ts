import {
  JSONRPC_VERSION,
  type HermesEventParams,
  type JsonRpcError,
  type JsonRpcEventNotification,
  type JsonRpcRequest,
  type JsonRpcResult,
} from "./hermes-protocol";

export type HermesEventHandler = (p: HermesEventParams) => void;

export class HermesGatewayRpc {
  private ws: WebSocket | null = null;
  private nextId = 1;
  private pending = new Map<
    number,
    { resolve: (v: unknown) => void; reject: (e: Error) => void }
  >();
  private eventHandlers = new Set<HermesEventHandler>();
  constructor(private readonly url: string) {}

  addEventListener(fn: HermesEventHandler): () => void {
    this.eventHandlers.add(fn);
    return () => this.eventHandlers.delete(fn);
  }

  connect(): Promise<void> {
    return new Promise((resolve, reject) => {
      const ws = new WebSocket(this.url);
      this.ws = ws;
      ws.onopen = () => resolve();
      ws.onerror = () => reject(new Error("WebSocket 连接失败"));
      ws.onclose = () => {
        this.ws = null;
        for (const [, p] of this.pending) {
          p.reject(new Error("WebSocket 已断开"));
        }
        this.pending.clear();
      };
      ws.onmessage = (ev) => {
        const text = String(ev.data);
        for (const line of text.split("\n")) {
          const t = line.trim();
          if (t) this.dispatchLine(t);
        }
      };
    });
  }

  close(): void {
    this.ws?.close();
    this.ws = null;
  }

  async call<T = unknown>(method: string, params: Record<string, unknown> = {}): Promise<T> {
    const ws = this.ws;
    if (!ws || ws.readyState !== WebSocket.OPEN) {
      throw new Error("WebSocket 未连接");
    }
    const id = this.nextId++;
    const req: JsonRpcRequest = { jsonrpc: JSONRPC_VERSION, id, method, params };
    return new Promise<T>((resolve, reject) => {
      this.pending.set(id, {
        resolve: (v) => resolve(v as T),
        reject,
      });
      ws.send(JSON.stringify(req));
    });
  }

  private dispatchLine(line: string): void {
    let msg: Record<string, unknown>;
    try {
      msg = JSON.parse(line) as Record<string, unknown>;
    } catch {
      return;
    }
    if (msg.method === "event") {
      const params = (msg as unknown as JsonRpcEventNotification).params;
      for (const fn of this.eventHandlers) fn(params);
      return;
    }
    const mid = msg.id;
    if (typeof mid !== "number") return;
    const p = this.pending.get(mid);
    if (!p) return;
    this.pending.delete(mid);
    if ("error" in msg && msg.error) {
      const err = msg as unknown as JsonRpcError;
      p.reject(new Error(err.error.message || String(err.error.code)));
    } else if ("result" in msg) {
      const ok = msg as unknown as JsonRpcResult;
      p.resolve(ok.result);
    }
  }
}

/** 浏览器同源开发：使用相对路径，经 Vite 代理到后端。 */
export function defaultGatewayWsUrl(): string {
  const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${proto}//${window.location.host}/api/chat`;
}
