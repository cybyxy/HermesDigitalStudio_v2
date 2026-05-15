/**
 * useSseSession — React hook for SSE EventSource lifecycle.
 * 自动重连：断线后指数退避重试（1s → 2s → 4s → … → 最大 30s）。
 * 切换 session 或卸载时停止重连。
 */
import { useEffect, useRef, useCallback } from 'react';
import { useAppStore } from '../stores/appStore';
import type { HermesEventParams } from '../types';

interface UseSseSessionOptions {
  sessionId: string | null;
  onEvent: (event: HermesEventParams) => void;
  /** Called when the SSE connection opens successfully */
  onOpen?: () => void;
  /** Called when the SSE connection errors */
  onError?: () => void;
}

export function useSseSession({ sessionId, onEvent, onOpen, onError }: UseSseSessionOptions) {
  const esRef = useRef<EventSource | null>(null);
  const onEventRef = useRef(onEvent);
  onEventRef.current = onEvent;

  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const reconnectAttemptRef = useRef(0);

  /** 清除待执行的重连计时器 */
  const clearReconnectTimer = useCallback(() => {
    if (reconnectTimerRef.current) {
      clearTimeout(reconnectTimerRef.current);
      reconnectTimerRef.current = null;
    }
  }, []);

  /** 安排重连：指数退避 1s/2s/4s/8s/16s/30s/... */
  const scheduleReconnect = useCallback((sid: string) => {
    clearReconnectTimer();
    reconnectAttemptRef.current += 1;
    const attempt = reconnectAttemptRef.current;
    // 指数退避: 1s, 2s, 4s, 8s, 16s, 30s (上限)
    const delay = Math.min(1000 * Math.pow(2, attempt - 1), 30000);
    console.log(`[SSE] 将在 ${delay}ms 后尝试重连 (第 ${attempt} 次)`);
    reconnectTimerRef.current = setTimeout(() => {
      console.log('[SSE] 正在重连...');
      // 用 ref 调用 connect，避免闭包过期
      connectRef.current(sid);
    }, delay);
  }, [clearReconnectTimer]);

  const connect = useCallback((sid: string) => {
    // Clear any pending reconnect
    clearReconnectTimer();

    // Close existing connection first
    if (esRef.current) {
      esRef.current.close();
      esRef.current = null;
    }

    const es = new EventSource(`/api/chat/sse/${sid}`);
    esRef.current = es;

    es.onopen = () => {
      console.log('[SSE] 连接已建立:', `/api/chat/sse/${sid}`);
      useAppStore.getState().setWsConnected(true);
      // 重连成功，重置尝试计数
      reconnectAttemptRef.current = 0;
      onOpen?.();
    };

    es.onmessage = (e: MessageEvent) => {
      try {
        const obj = JSON.parse(e.data);
        if (obj.method === 'event' && obj.params) {
          onEventRef.current(obj.params as HermesEventParams);
        } else if (obj.type) {
          onEventRef.current(obj as HermesEventParams);
        }
      } catch {
        // 忽略无法解析的消息
      }
    };

    es.onerror = () => {
      // 仅当仍为此 EventSource 时处理（防止关闭旧连接时误触发）
      if (esRef.current !== es) return;
      console.warn('[SSE] 连接错误:', `/api/chat/sse/${sid}`);
      useAppStore.getState().setWsConnected(false);
      onError?.();

      // 自动重连
      scheduleReconnect(sid);
    };
  }, [clearReconnectTimer, scheduleReconnect, onOpen, onError]);

  // connect 保持最新引用（供 scheduleReconnect 超时回调使用）
  const connectRef = useRef(connect);
  connectRef.current = connect;

  const disconnect = useCallback(() => {
    clearReconnectTimer();
    reconnectAttemptRef.current = 0;
    if (esRef.current) {
      esRef.current.close();
      esRef.current = null;
    }
    useAppStore.getState().setWsConnected(false);
  }, [clearReconnectTimer]);

  useEffect(() => {
    if (sessionId) {
      console.log('[SSE] connecting to session:', sessionId);
      connect(sessionId);
    } else {
      console.log('[SSE] disconnecting (no sessionId)');
      disconnect();
    }
    return () => {
      console.log('[SSE] cleanup for session:', sessionId);
      clearReconnectTimer();
      if (esRef.current) {
        esRef.current.close();
        esRef.current = null;
      }
    };
  }, [sessionId, connect, disconnect, clearReconnectTimer]);

  return { connect, disconnect };
}
