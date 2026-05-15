/**
 * useChatSend — Send message + orchestration flow hook.
 *
 * Handles: POST /api/chat/orchestrated/run → stream orchestration events.
 */
import { useState, useCallback, useRef } from 'react';
import { useAppStore } from '../stores/appStore';
import { useSessionStore } from '../stores/sessionStore';
import { apiFetch, ApiError } from '../api/client';

interface UseChatSendOptions {
  sessionId: string;
  onStreamEvent?: (event: Record<string, unknown>) => void;
}

export function useChatSend({ sessionId, onStreamEvent }: UseChatSendOptions) {
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const streamEsRef = useRef<EventSource | null>(null);

  const sendMessage = useCallback(async (text: string, attachments?: File[]): Promise<string | null> => {
    if (sending) return null;
    setSending(true);
    setError(null);

    try {
      // 1. POST to orchestrated run (JSON body)
      const data = await apiFetch<{ run_id?: string; message?: string }>(
        '/api/chat/orchestrated/run',
        { method: 'POST', json: { sessionId, text } },
      );

      const runId = data.run_id;
      if (!runId) {
        setError('未获取到 runId');
        return null;
      }

      // 2. Open short-lived orchestration stream
      const streamEs = new EventSource(`/api/chat/orchestrated/stream?run_id=${encodeURIComponent(runId)}`);
      streamEsRef.current = streamEs;

      return new Promise<string | null>((resolve) => {
        streamEs.onmessage = (e: MessageEvent) => {
          try {
            const evt = JSON.parse(e.data) as Record<string, unknown>;
            onStreamEvent?.(evt);

            if (evt.type === 'orch_done') {
              streamEs.close();
              streamEsRef.current = null;
              resolve(String(evt.session_id ?? evt.message ?? runId));
            } else if (evt.type === 'orch_error') {
              streamEs.close();
              streamEsRef.current = null;
              const errMsg = String(evt.message ?? evt.error ?? '编排错误');
              setError(errMsg);
              resolve(null);
            }
          } catch {
            // Ignore parse errors
          }
        };

        streamEs.onerror = () => {
          streamEs.close();
          streamEsRef.current = null;
          setError('编排流连接错误');
          resolve(null);
        };

        // Timeout after 60 seconds
        setTimeout(() => {
          if (streamEsRef.current) {
            streamEsRef.current.close();
            streamEsRef.current = null;
            setError('编排超时');
            resolve(null);
          }
        }, 60000);
      });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : (err instanceof Error ? err.message : '发送异常'));
      return null;
    } finally {
      setSending(false);
    }
  }, [sessionId, sending, onStreamEvent]);

  const cancelSending = useCallback(() => {
    if (streamEsRef.current) {
      streamEsRef.current.close();
      streamEsRef.current = null;
    }
    setSending(false);
  }, []);

  return { sendMessage, cancelSending, sending, error, clearError: () => setError(null) };
}
