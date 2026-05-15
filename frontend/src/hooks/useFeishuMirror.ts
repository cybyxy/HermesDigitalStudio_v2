/**
 * useFeishuMirror — Feishu transcript bridge hook.
 * Opens SSE connection to feishu gateway bridge for real-time transcript mirroring.
 */
import { useState, useCallback, useEffect, useRef } from 'react';
import type { ChatRow, ProcessRow } from '../types';
import { apiFetch } from '../api/client';

export function useFeishuMirror() {
  const [isConnected, setIsConnected] = useState(false);
  const [mirrorChatRows, setMirrorChatRows] = useState<ChatRow[]>([]);
  const [mirrorProcessRows, setMirrorProcessRows] = useState<ProcessRow[]>([]);
  const [error, setError] = useState<string | null>(null);
  const esRef = useRef<EventSource | null>(null);

  /** Connect to feishu gateway bridge SSE */
  const connect = useCallback((token: string) => {
    disconnect();
    setError(null);

    const es = new EventSource(`/api/chat/gateway-bridge/sse?token=${encodeURIComponent(token)}`);
    esRef.current = es;

    es.onopen = () => {
      setIsConnected(true);
    };

    es.onmessage = (e: MessageEvent) => {
      try {
        const data = JSON.parse(e.data) as Record<string, unknown>;
        if (data.type === 'chat') {
          setMirrorChatRows((prev) => [...prev, data.payload as unknown as ChatRow]);
        } else if (data.type === 'process') {
          setMirrorProcessRows((prev) => [...prev, data.payload as unknown as ProcessRow]);
        }
      } catch {
        // Ignore parse errors
      }
    };

    es.onerror = () => {
      setIsConnected(false);
      setError('飞书桥接连接错误');
    };
  }, []);

  const disconnect = useCallback(() => {
    if (esRef.current) {
      esRef.current.close();
      esRef.current = null;
    }
    setIsConnected(false);
  }, []);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (esRef.current) {
        esRef.current.close();
        esRef.current = null;
      }
    };
  }, []);

  /** Load feishu session history */
  const loadFeishuHistory = useCallback(async (): Promise<void> => {
    try {
      const data = await apiFetch<{ sessions?: Array<{ id: string; messages: ChatRow[] }> }>('/api/chat/feishu/sessions');
      // Merge messages
      const allMessages: ChatRow[] = [];
      for (const sess of data.sessions ?? []) {
        allMessages.push(...(sess.messages ?? []));
      }
      setMirrorChatRows(allMessages);
    } catch {
      setError('加载飞书历史失败');
    }
  }, []);

  return {
    isConnected,
    mirrorChatRows,
    mirrorProcessRows,
    error,
    connect,
    disconnect,
    loadFeishuHistory,
    clearError: () => setError(null),
  };
}
