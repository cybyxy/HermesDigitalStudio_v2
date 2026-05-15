/**
 * AgentList — React replacement for class-based AgentList.
 * Renders a card-grid of agents with animated sprite canvases and model selectors.
 */
import { AgentSpriteCanvas } from './AgentSpriteCanvas';
import type { AgentInfo } from '../types';

interface ModelInfo {
  id: string;
  name: string;
  provider: string;
  isDefault?: boolean;
}

interface Props {
  agents: AgentInfo[];
  activeAgentId: string | null;
  models: ModelInfo[];
  onSelect: (agentId: string) => void;
  onEdit: (agentId: string) => void;
  onAdd: () => void;
  onDelete: (agentId: string) => void;
  onModelChange: (agentId: string, model: string, provider: string) => void;
  onAgentLabel?: (agent: AgentInfo) => string;
}

export function AgentList({
  agents, activeAgentId, models,
  onSelect, onEdit, onAdd, onDelete, onModelChange, onAgentLabel,
}: Props) {
  return (
    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
      {/* Add card */}
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
        <span style={{ fontSize: 11, color: '#8b93a7' }}>新建</span>
      </div>

      {/* Agent cards */}
      {agents.map((a) => {
        const isActive = a.agentId === activeAgentId;
        return (
          <div
            key={a.agentId}
            onClick={() => { onSelect(a.agentId); onEdit(a.agentId); }}
            style={{
              width: 100,
              minHeight: 120,
              border: `1.5px solid ${isActive ? '#5b8cff' : 'transparent'}`,
              borderRadius: 10,
              background: isActive ? 'rgba(91,140,255,0.18)' : 'rgba(42,49,64,0.2)',
              cursor: 'pointer',
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              gap: 6,
              padding: 8,
              position: 'relative',
            }}
            onMouseEnter={(e) => {
              e.currentTarget.style.background = isActive ? 'rgba(91,140,255,0.18)' : 'rgba(91,140,255,0.12)';
              e.currentTarget.style.borderColor = 'rgba(91,140,255,0.35)';
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.borderColor = isActive ? '#5b8cff' : 'transparent';
              e.currentTarget.style.background = isActive ? 'rgba(91,140,255,0.18)' : 'rgba(42,49,64,0.2)';
            }}
          >
            <AgentSpriteCanvas agent={a} />
            <span style={{ fontSize: 11, color: '#e8eaef', textAlign: 'center', maxWidth: 80, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              {onAgentLabel ? onAgentLabel(a) : a.displayName || a.agentId}
            </span>
            {a.profile && (
              <span style={{ fontSize: 10, color: '#8b93a7', textAlign: 'center', maxWidth: 80, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {a.profile}
              </span>
            )}

            {/* Model selector */}
            <select
              value={a.model && a.modelProvider ? `${a.modelProvider}:${a.model}` : ''}
              onClick={(e) => e.stopPropagation()}
              onChange={(e) => {
                const val = e.target.value;
                if (!val) return;
                const [provider, model] = val.split(':');
                if (provider && model) onModelChange(a.agentId, model, provider);
              }}
              style={{
                width: '100%',
                background: '#0f1218',
                color: '#e8eaef',
                border: '1px solid #2a3140',
                borderRadius: 4,
                fontSize: 10,
                padding: '2px 4px',
                cursor: 'pointer',
              }}
            >
              <option value="">默认模型</option>
              {models.map((m) => (
                <option key={m.id} value={`${m.provider}:${m.name}`}>
                  {m.provider} / {m.name}
                </option>
              ))}
            </select>

            {/* Delete button */}
            {onDelete && (
              <button
                onClick={(e) => { e.stopPropagation(); onDelete(a.agentId); }}
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
                }}
              >
                ×
              </button>
            )}
          </div>
        );
      })}
    </div>
  );
}
