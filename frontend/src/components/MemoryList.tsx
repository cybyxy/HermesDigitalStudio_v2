/**
 * MemoryList — 记忆管理面板，卡片网格布局。
 * 每张卡片对应一个 Agent，点击弹出 MemoryDetailModal。
 */
import { AgentSpriteCanvas } from './AgentSpriteCanvas';
import type { AgentInfo } from '../types';

interface Props {
  agents: AgentInfo[];
  onSelectMemory: (agentId: string) => void;
}

export function MemoryList({ agents, onSelectMemory }: Props) {
  return (
    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
      {agents.length === 0 ? (
        <div style={{ color: '#8b93a7', fontSize: 12, textAlign: 'center', padding: '24px 0', width: '100%' }}>
          暂无 Agent 数据。请先在 &quot;Agent 管理&quot; 中创建 Agent。
        </div>
      ) : (
        agents.map((a) => (
          <div
            key={a.agentId}
            onClick={() => onSelectMemory(a.agentId)}
            style={{
              width: 100,
              minHeight: 120,
              border: '1.5px solid transparent',
              borderRadius: 10,
              background: 'rgba(42,49,64,0.2)',
              cursor: 'pointer',
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              gap: 6,
              padding: 8,
              position: 'relative',
            }}
            onMouseEnter={(e) => {
              e.currentTarget.style.background = 'rgba(91,140,255,0.12)';
              e.currentTarget.style.borderColor = 'rgba(91,140,255,0.35)';
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.borderColor = 'transparent';
              e.currentTarget.style.background = 'rgba(42,49,64,0.2)';
            }}
          >
            <AgentSpriteCanvas agent={a} />
            <span
              style={{
                fontSize: 11,
                color: '#e8eaef',
                textAlign: 'center',
                maxWidth: 80,
                overflow: 'hidden',
                textOverflow: 'ellipsis',
                whiteSpace: 'nowrap',
              }}
            >
              {a.displayName || a.agentId}
            </span>
            {a.profile && (
              <span
                style={{
                  fontSize: 10,
                  color: '#8b93a7',
                  textAlign: 'center',
                  maxWidth: 80,
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                  whiteSpace: 'nowrap',
                }}
              >
                {a.profile}
              </span>
            )}
          </div>
        ))
      )}
    </div>
  );
}
