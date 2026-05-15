/**
 * ChannelList — React replacement for class-based ChannelList.
 * Renders a card-grid of communication channels with platform icons and status.
 */
import type { AgentInfo, ChannelInfo } from '../types';

interface Props {
  channels: ChannelInfo[];
  agents: AgentInfo[];
  onAdd?: () => void;
  onEdit?: (channelId: string) => void;
  onDelete?: (channelId: string) => void;
}

const PLATFORM_ICONS: Record<string, string> = {
  feishu: '🐦', dingtalk: '🔷', wecom: '💚', slack: '💬', telegram: '✈️',
  whatsapp: '💬', discord: '🎮', line: '💚', teams: '🟣', signal: '🔒',
  matrix: '🟢', rocket: '🚀', zulip: '📨', mattermost: '📢', email: '📧',
  sms: '📱', webhook: '🔗', custom: '⚙',
};

export function ChannelList({ channels, agents, onAdd, onEdit, onDelete }: Props) {
  const icon = (platform: string): string => {
    const key = platform.toLowerCase();
    return PLATFORM_ICONS[key] || '📡';
  };

  const statusColor = (ch: ChannelInfo): string => {
    if (ch.status === 'connected') return '#4caf50';
    if (ch.status === 'error') return '#e53935';
    return '#8b93a7';
  };

  const statusLabel = (ch: ChannelInfo): string => {
    if (ch.status === 'connected') return '已连接';
    if (ch.status === 'error') return '错误';
    return '未连接';
  };

  const boundAgent = (agentId?: string): string | null => {
    if (!agentId) return null;
    const a = agents.find((x) => x.agentId === agentId);
    return a ? `🤖 ${a.displayName || a.agentId}` : null;
  };

  return (
    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
      {/* Add card */}
      {onAdd && (
        <div
          onClick={onAdd}
          style={{
            width: 100,
            minHeight: 120,
            border: '1px dashed #2a3140',
            borderRadius: 10,
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            gap: 6,
            cursor: 'pointer',
            background: 'rgba(42,49,64,0.2)',
          }}
        >
          <div style={{ width: 32, height: 32, borderRadius: '50%', background: '#2a3140', display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#8b93a7', fontSize: 18 }}>
            +
          </div>
          <span style={{ fontSize: 11, color: '#8b93a7' }}>新建通道</span>
        </div>
      )}

      {/* Channel cards */}
      {channels.map((ch) => (
        <div
          key={ch.id}
          onClick={() => onEdit?.(ch.id)}
          style={{
            width: 100,
            minHeight: 120,
            border: '1px solid #2a3140',
            borderRadius: 10,
            padding: 8,
            cursor: 'pointer',
            background: 'rgba(42,49,64,0.2)',
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            gap: 4,
            position: 'relative',
          }}
        >
          <div style={{ fontSize: 20 }}>{icon(ch.platform)}</div>
          <div style={{ fontSize: 11, fontWeight: 500, color: '#e8eaef', textAlign: 'center', maxWidth: 80, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
            {ch.name}
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
            <span style={{ width: 6, height: 6, borderRadius: '50%', background: statusColor(ch) }} />
            <span style={{ fontSize: 10, color: '#8b93a7' }}>{statusLabel(ch)}</span>
          </div>
          {ch.chatId && (
            <div style={{ fontSize: 10, color: '#5a6478', textAlign: 'center', maxWidth: 80, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              {ch.chatId}
            </div>
          )}
          {boundAgent(ch.agentId) && (
            <div style={{ fontSize: 10, color: '#5b8cff', textAlign: 'center', maxWidth: 80, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              {boundAgent(ch.agentId)}
            </div>
          )}

          {/* Hover actions */}
          {onDelete && (
            <button
              onClick={(e) => { e.stopPropagation(); onDelete(ch.id); }}
              style={{
                position: 'absolute',
                top: 4,
                right: 4,
                width: 18,
                height: 18,
                background: 'rgba(229,57,53,0.2)',
                border: 'none',
                borderRadius: '50%',
                color: '#e53935',
                cursor: 'pointer',
                fontSize: 10,
                lineHeight: 1,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                opacity: 0.6,
              }}
              onMouseEnter={(e) => (e.currentTarget.style.opacity = '1')}
              onMouseLeave={(e) => (e.currentTarget.style.opacity = '0.6')}
            >
              ×
            </button>
          )}
        </div>
      ))}
    </div>
  );
}
