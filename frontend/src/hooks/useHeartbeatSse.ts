/**
 * useHeartbeatSse — 心跳推理 SSE 连接 hook。
 * 连接到 /api/chat/heartbeat/sse，接收后端心跳推理结果。
 * 自动重连：指数退避 1s→2s→4s→...→30s（与 useSseSession 一致）。
 */
import { useEffect, useRef, useCallback } from 'react';
import { useAppStore } from '../stores/appStore';
import { useAgentStore } from '../stores/agentStore';

export function useHeartbeatSse(enabled = true) {
  const esRef = useRef<EventSource | null>(null);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const reconnectAttemptRef = useRef(0);

  const clearReconnectTimer = useCallback(() => {
    if (reconnectTimerRef.current) {
      clearTimeout(reconnectTimerRef.current);
      reconnectTimerRef.current = null;
    }
  }, []);

  const scheduleReconnect = useCallback(() => {
    clearReconnectTimer();
    reconnectAttemptRef.current += 1;
    const attempt = reconnectAttemptRef.current;
    const delay = Math.min(1000 * Math.pow(2, attempt - 1), 30000);
    console.log(`[HeartbeatSSE] 将在 ${delay}ms 后重连 (第 ${attempt} 次)`);
    reconnectTimerRef.current = setTimeout(() => {
      connectRef.current();
    }, delay);
  }, [clearReconnectTimer]);

  const connect = useCallback(() => {
    clearReconnectTimer();

    if (esRef.current) {
      esRef.current.close();
      esRef.current = null;
    }

    console.log('[HeartbeatSSE] 正在连接 /api/chat/heartbeat/sse...');
    const es = new EventSource('/api/chat/heartbeat/sse');
    esRef.current = es;

    es.onopen = () => {
      console.log('[HeartbeatSSE] 心跳推理 SSE 已连接');
      reconnectAttemptRef.current = 0;
    };

    es.onmessage = (e: MessageEvent) => {
      try {
        const obj = JSON.parse(e.data);
        if (obj.type === 'heartbeat.thinking') {
          // 实时累积 thinking 文本流
          const store = useAppStore.getState();
          store.setHeartbeatThinking(store.heartbeatThinking + String(obj.content ?? ''));
        } else if (obj.type === 'heartbeat.reasoning') {
          useAppStore.getState().setHeartbeatMessage({
            agentId: String(obj.agent_id ?? ''),
            content: String(obj.content ?? ''),
            timestamp: Number(obj.timestamp ?? Date.now()),
          });
          // 推理完成，清空 thinking 流
          useAppStore.getState().clearHeartbeatThinking();
        } else if (obj.type === 'small_thought') {
          const agentId = String(obj.agent_id ?? '');
          const content = String(obj.content ?? '');
          useAppStore.getState().setSmallThought({
            agentId,
            content,
            timestamp: Number(obj.timestamp ?? Date.now()),
          });
          // Also set the Phaser scene infer state for bubble display
          useAgentStore.getState().patchAgentSceneInfer(agentId, {
            phase: 'small_thought',
            smallThoughtSnippet: content,
            smallThoughtExpiresAt: Date.now() + 10000,
          });
        }
      } catch {
        // 忽略无法解析的消息
      }
    };

    es.onerror = () => {
      if (esRef.current !== es) return;
      console.warn('[HeartbeatSSE] 连接错误');
      esRef.current?.close();
      esRef.current = null;
      scheduleReconnect();
    };
  }, [clearReconnectTimer, scheduleReconnect]);

  const connectRef = useRef(connect);
  connectRef.current = connect;

  const disconnect = useCallback(() => {
    clearReconnectTimer();
    reconnectAttemptRef.current = 0;
    if (esRef.current) {
      esRef.current.close();
      esRef.current = null;
    }
  }, [clearReconnectTimer]);

  useEffect(() => {
    if (enabled) {
      connect();
    }
    return () => {
      disconnect();
    };
  }, [enabled]); // eslint-disable-line react-hooks/exhaustive-deps

  return { connect, disconnect };
}
