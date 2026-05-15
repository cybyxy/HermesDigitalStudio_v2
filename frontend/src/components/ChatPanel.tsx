/**
 * ChatPanel — Renders the chat messages for a session.
 * Reads from sessionStore and agentStore, uses ChatBubble / AgentToolPanel sub-components.
 */
import { useEffect, useRef } from 'react';
import { useSessionStore } from '../stores/sessionStore';
import { useAgentStore } from '../stores/agentStore';
import { ChatBubble } from './ChatBubble';
import { AgentToolPanel } from './AgentToolPanel';

interface Props {
  sessionId: string | null;
}

export function ChatPanel({ sessionId }: Props) {
  const sessions = useSessionStore((s) => s.sessions);
  const agents = useAgentStore((s) => s.agents);
  const session = sessionId ? sessions.find((s) => s.id === sessionId) : null;
  const isRestoringSession = useSessionStore((s) => s.isRestoringSession);

  console.log('[ChatPanel] render sessionId:', sessionId,
    'session found:', !!session,
    'messages:', session?.messages?.length ?? 0,
    'isRestoringSession:', isRestoringSession);

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // Auto-scroll to bottom when messages change
  useEffect(() => {
    if (messagesEndRef.current) {
      messagesEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [session?.messages?.length]);

  // Auto-focus input after session restore completes
  useEffect(() => {
    if (!isRestoringSession && session && inputRef.current) {
      inputRef.current.focus();
    }
  }, [isRestoringSession, session?.id]);

  // Loading state while session is being restored on startup
  if (isRestoringSession) {
    return (
      <div style={{
        flex: 1,
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        color: '#5a6478',
        fontSize: 13,
        gap: 12,
      }}>
        <div style={{
          width: 24,
          height: 24,
          border: '2px solid #e0e4ea',
          borderTopColor: '#5b8cff',
          borderRadius: '50%',
          animation: 'hds-spin 0.8s linear infinite',
        }} />
        <span>正在恢复会话...</span>
      </div>
    );
  }

  if (!session) {
    return (
      <div style={{
        flex: 1,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        color: '#5a6478',
        fontSize: 13,
      }}>
        {agents.length > 0 ? '正在连接 Agent...' : '选择一个 Agent 开始对话'}
      </div>
    );
  }

  const agentFacing = new Map<string, 'down' | 'up' | 'left' | 'right'>();

  return (
    <div style={{
      flex: 1,
      display: 'flex',
      flexDirection: 'column',
      overflow: 'hidden',
    }}>
      {/* 消息区域 */}
      <div style={{
        flex: 1,
        overflow: 'hidden auto',
        padding: '8px 12px',
      }}>
        {session.messages.map((msg, i) => (
          <ChatBubble
            key={`msg-${i}-${msg.timestamp}`}
            message={msg}
            layout={msg.role === 'user' ? 'initiator' : 'responder'}
            agents={agents}
            agentFacing={agentFacing}
            onResolveAgent={(msg) => {
              if (msg.role !== 'assistant') return null;
              return agents.find((a) => a.agentId === session.agentId) ?? null;
            }}
          />
        ))}

        {/* Streaming indicator */}
        {session.streaming && (
          <div style={{
            display: 'flex',
            alignItems: 'center',
            gap: 6,
            padding: '4px 8px',
            color: '#8b93a7',
            fontSize: 12,
          }}>
            <span style={{
              width: 6,
              height: 6,
              borderRadius: '50%',
              background: '#5b8cff',
              animation: 'hds-tool-pulse 1.2s infinite',
            }} />
            思考中…
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* 推理 · 工具面板 */}
      <AgentToolPanel
        sessionId={sessionId}
        agentId={session.agentId}
      />
    </div>
  );
}
