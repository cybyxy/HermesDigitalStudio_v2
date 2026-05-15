/**
 * App — root React component.
 *
 * Architecture:
 *   - Phaser renders into a fullscreen canvas (z-index 0)
 *   - React UI (AppShell: panels, status bar) floats on top (z-index 1+)
 *   - Communication: bidirectional via Zustand domain stores
 */
import { useRef, useEffect } from 'react';
import { PhaserGameProvider } from './context/PhaserGameContext';
import { AppShell } from './components/AppShell';
import { useSessionStore } from './stores/sessionStore';
import { useChannelStore } from './stores/channelStore';
import { useSkillStore } from './stores/skillStore';
import { apiGetSessions, apiGetHistory, apiGetLastActiveSession, apiGetSessionChainHistory } from './api/chat';
import { apiGetChannels } from './api/channels';
import { apiGetSkills } from './api/skills';

export function App() {
  const phaserHostRef = useRef<HTMLDivElement>(null);

  // 启动时优先恢复上次活跃 session（持久记忆），否则加载所有 session 并激活第一个
  useEffect(() => {
    const LOADING_TIMEOUT_MS = 10000; // 历史消息加载超时（10 秒）

    async function loadSessions() {
      const store = useSessionStore.getState();
      
      // 标记会话恢复中，ChatPanel 显示加载指示器
      store.setIsRestoringSession(true);

      try {
        // 1. 尝试恢复上次活跃 session（持久记忆）
        const lastActive = await apiGetLastActiveSession();
        if (lastActive.session && lastActive.session.sessionId && lastActive.session.agentId) {
          const las = lastActive.session;
          const sessionState = {
            id: las.sessionId,
            agentId: las.agentId,
            title: '',
            messages: [] as import('./types').ChatRow[],
            processRows: [] as import('./types').ProcessRow[],
            streaming: false,
            unread: false,
          };
          // 先设置 session 和 activeId，ChatPanel 显示恢复中状态
          store.setSessions(() => [sessionState]);
          store.setActiveId(las.sessionId);
          console.log('[App] 恢复上次活跃 session:', las.sessionId, 'agent:', las.agentId,
            lastActive.restored ? '(已重新连接)' : '(已在线)');

          // 并发加载：链历史（带超时）+ SSE 连接同时建立
          try {
            const chainHistory = await Promise.race([
              apiGetSessionChainHistory(las.sessionId, 10),
              new Promise<never>((_, reject) =>
                setTimeout(() => reject(new Error('加载历史消息超时')), LOADING_TIMEOUT_MS),
              ),
            ]);
            if (chainHistory.messages && chainHistory.messages.length > 0) {
              store.patchSession(las.sessionId, (s) => ({
                ...s,
                messages: chainHistory.messages,
              }));
              console.log('[App] 已加载会话链历史消息, 数量:', chainHistory.messages.length);
            }
          } catch (err) {
            console.error('[App] 加载会话链历史失败或超时:', err);
            // 超时后不阻塞：ChatPanel 显示恢复中，后台继续尝试异步加载
            if (String(err).includes('超时')) {
              // 异步兜底：忽略超时后继续加载（不阻塞 UI）
              apiGetSessionChainHistory(las.sessionId, 10).then((chainHistory) => {
                if (chainHistory.messages && chainHistory.messages.length > 0) {
                  store.patchSession(las.sessionId, (s) => ({
                    ...s,
                    messages: chainHistory.messages,
                  }));
                  console.log('[App] 超时后异步加载完成, 数量:', chainHistory.messages.length);
                }
              }).catch((e2) => {
                console.error('[App] 异步兜底加载也失败:', e2);
              });
            }
          }
          
          store.setIsRestoringSession(false);
          return; // 成功恢复，不再走 fallback
        }
      } catch (err) {
        console.error('[App] 加载上次活跃 session 失败，回退到 session 列表:', err);
      }

      // 2. Fallback: 加载所有 session 并激活第一个
      try {
        const sessions = await apiGetSessions();
        if (sessions.length > 0) {
          store.setSessions((prev) => {
            const merged = [...prev];
            for (const s of sessions) {
              if (!merged.find((p) => p.id === s.id)) {
                merged.push(s);
              }
            }
            return merged;
          });
          const activeSession = sessions.find((s) => s.agentId) ?? sessions[0];
          store.setActiveId(activeSession.id);
          console.log('[App] 已加载 session, 激活:', activeSession.id, 'agent:', activeSession.agentId);

          try {
            const history = await Promise.race([
              apiGetHistory(activeSession.id),
              new Promise<never>((_, reject) =>
                setTimeout(() => reject(new Error('加载历史消息超时')), LOADING_TIMEOUT_MS),
              ),
            ]);
            if (history.messages && history.messages.length > 0) {
              useSessionStore.getState().patchSession(activeSession.id, (s) => ({
                ...s,
                messages: history.messages as import('./types').ChatRow[],
                processRows: (history.processRows ?? []) as import('./types').ProcessRow[],
              }));
              console.log('[App] 已加载历史消息, 数量:', history.messages.length);
            }
          } catch (err) {
            console.error('[App] 加载历史消息失败或超时:', err);
          }
        } else {
          // 无历史 session → 标记自动连接，由 AppShell 为所有 Agent 建立连接
          console.log('[App] 无历史 session，将自动连接所有 Agent');
          const { useAppStore } = await import('./stores/appStore');
          useAppStore.getState().setAutoConnect(true);
        }
      } catch (err) {
        console.error('[App] 加载 session 失败，将自动连接所有 Agent:', err);
        const { useAppStore } = await import('./stores/appStore');
        useAppStore.getState().setAutoConnect(true);
      }
      
      // 无论 fallback 结果如何，都结束恢复状态
      store.setIsRestoringSession(false);
    }
    loadSessions();

    // 加载通道列表
    async function loadChannels() {
      try {
        const channelList = await apiGetChannels();
        useChannelStore.getState().setChannels(channelList);
        console.log('[App] 已加载通道, 数量:', channelList.length);
      } catch (err) {
        console.error('[App] 加载通道失败:', err);
      }
    }
    loadChannels();

    // 加载技能列表
    async function loadSkills() {
      try {
        const skillList = await apiGetSkills();
        useSkillStore.getState().setSkills(skillList);
        console.log('[App] 已加载技能, agent 数量:', skillList.length);
      } catch (err) {
        console.error('[App] 加载技能失败:', err);
      }
    }
    loadSkills();
  }, []);

  return (
    <PhaserGameProvider containerRef={phaserHostRef}>
      {/* Phaser canvas layer — fills viewport minus bottom bar */}
      <div
        ref={phaserHostRef}
        style={{
          position: 'absolute',
          left: 0,
          top: 0,
          right: 0,
          bottom: 'var(--menu-h)',
          zIndex: 0,
        }}
      />
      {/* React UI layer — floats above Phaser, pointerEvents passthrough.
           NOTE: pointerEvents: 'none' on the outer div allows clicks on empty areas
           to reach the Phaser canvas below. Individual React components within AppShell
           (panels, bottom bar, dock, modals) receive events naturally through the
           browser's event dispatch — no inner pointerEvents: 'auto' wrapper needed. */}
      <div style={{ position: 'relative', zIndex: 1, pointerEvents: 'none', height: '100%' }}>
        <AppShell />
      </div>
    </PhaserGameProvider>
  );
}
