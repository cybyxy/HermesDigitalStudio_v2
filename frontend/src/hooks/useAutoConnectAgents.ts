/**
 * useAutoConnectAgents — 页面加载后自动为所有 Agent 建立 session 和 SSE 连接。
 *
 * 在 AppShell 加载完 agent 列表后调用，
 * 若 appStore.autoConnect = true（无历史 session），
 * 并发为每个 agent 创建 session，建立即时通讯。
 */
import { useEffect } from 'react';
import { useAppStore } from '../stores/appStore';
import { useSessionStore } from '../stores/sessionStore';
import { apiPostSession } from '../api/chat';
import type { AgentInfo } from '../types';

export function useAutoConnectAgents(
  agents: AgentInfo[],
  onReady: (sessionId: string) => void,
) {
  useEffect(() => {
    const appStore = useAppStore.getState();
    if (!appStore.autoConnect || agents.length === 0) return;

    let cancelled = false;

    async function connectAll() {
      // 并发为所有 agent 创建 session
      const results = await Promise.allSettled(
        agents.map((agent) =>
          apiPostSession(agent.agentId, 120).then((res) => ({
            sessionId: res.sessionId,
            agentId: agent.agentId,
          })),
        ),
      );

      if (cancelled) return;

      // 收集成功创建的 session
      const validSessions = results
        .filter(
          (r): r is PromiseFulfilledResult<{ sessionId: string; agentId: string }> =>
            r.status === 'fulfilled',
        )
        .map((r) => ({
          id: r.value.sessionId,
          agentId: r.value.agentId,
          title: '',
          messages: [] as any[],
          processRows: [] as any[],
          streaming: false,
          unread: false,
        }));

      if (validSessions.length > 0) {
        const sessionStore = useSessionStore.getState();
        sessionStore.addSessions(validSessions);

        // 默认选中第一个 agent 的 session
        const first = validSessions[0];
        sessionStore.setActiveId(first.id);
        onReady(first.id);
        console.log(
          '[AutoConnect] 已连接 %d/%d 个 Agent，激活: %s',
          validSessions.length,
          agents.length,
          first.agentId,
        );
      }

      useAppStore.getState().setAutoConnect(false);
    }

    connectAll();

    return () => {
      cancelled = true;
    };
  }, [agents]);
}
