/**
 * AgentToolPanel — 展示 Agent 推理过程和工具调用的面板
 */
import { useState, useEffect, useRef } from 'react';
import { useSessionStore } from '../stores/sessionStore';
import { useAgentStore } from '../stores/agentStore';
import { escapeHtml } from '../lib/formatUtils';
import type { ProcessRow } from '../types';

interface Props {
  sessionId: string | null;
  agentId?: string;
}

export function AgentToolPanel({ sessionId, agentId }: Props) {
  const [collapsed, setCollapsed] = useState(false);
  const [expandedItems, setExpandedItems] = useState<Set<string>>(new Set());
  const bottomRef = useRef<HTMLDivElement>(null);

  const sessions = useSessionStore((s) => s.sessions);
  const session = sessionId ? sessions.find((s) => s.id === sessionId) : null;

  const inferState = useAgentStore((s) => s.agentSceneInfer);
  const currentInfer = agentId ? inferState[agentId] : null;

  const processRows = session?.processRows ?? [];

  useEffect(() => {
    if (!collapsed && bottomRef.current) {
      bottomRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [processRows.length, collapsed]);

  const toggleItem = (id: string) => {
    setExpandedItems((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  };

  const expandAll = () => setExpandedItems(new Set(processRows.map((r) => r.id)));
  const collapseAll = () => setExpandedItems(new Set());

  const fmtTime = (ts: number | undefined): string => {
    if (ts == null || !Number.isFinite(ts)) return '';
    const d = new Date(ts);
    return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
  };

  const renderReasoningItem = (row: ProcessRow) => {
    const isExpanded = expandedItems.has(row.id);
    const isRunning = row.streaming;
    return (
      <div key={row.id} style={{ borderLeft: `3px solid ${isRunning ? '#6c8bf5' : '#2a3140'}`, background: isRunning ? 'rgba(108,139,245,0.06)' : 'transparent', padding: '6px 8px', marginBottom: 4, borderRadius: 4, fontSize: 12 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: isExpanded ? 4 : 0, cursor: 'pointer' }} onClick={() => toggleItem(row.id)}>
          <span style={{ color: '#8b93a7', fontSize: 10 }}>◇</span>
          <span style={{ fontWeight: 500, color: '#e8eaef' }}>{isRunning ? '思考中…' : '推理过程'}</span>
          {row.timestamp != null && <span style={{ color: '#8b93a7', fontSize: 11, marginLeft: 'auto' }}>{fmtTime(row.timestamp)}</span>}
          {isRunning && <span style={{ width: 6, height: 6, borderRadius: '50%', background: '#6c8bf5', animation: 'hds-tool-pulse 1.2s infinite', flexShrink: 0 }} />}
          <span style={{ color: '#5a6478', marginLeft: 4 }}>{isExpanded ? '▼' : '▶'}</span>
        </div>
        {!isExpanded && row.body && <div style={{ color: '#8b93a7', fontSize: 11, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', maxWidth: '100%' }}>{row.body.slice(0, 80)}...</div>}
        {isExpanded && <div style={{ color: '#c0c6d0', lineHeight: 1.45, wordBreak: 'break-word', maxHeight: 160, overflow: 'auto' }} dangerouslySetInnerHTML={{ __html: escapeHtml(row.body || '…').replace(/\n/g, '<br>') }} />}
      </div>
    );
  };

  const renderToolItem = (row: ProcessRow) => {
    const isExpanded = expandedItems.has(row.id);
    const isTool = row.variant === 'tool';
    const isRunning = row.streaming;
    const accentColor = isTool ? '#4fc3f7' : '#6c8bf5';
    const titleClean = () => { let t = row.title || ''; if (isRunning) return t.replace(/^⏳\s*/, ''); if (isTool) return t.replace(/^[🔧⚡→]\s*/, ''); return '推理'; };
    const bodyEl = () => { const b = row.body || ''; if (isRunning && !b) return '…'; return escapeHtml(b).replace(/\n/g, '<br>'); };
    return (
      <div key={row.id} style={{ borderLeft: `3px solid ${isRunning ? accentColor : '#2a3140'}`, background: isRunning ? `rgba(79,195,247,0.06)` : 'transparent', padding: '6px 8px', marginBottom: 4, borderRadius: 4, fontSize: 12 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: isExpanded ? 4 : 0, cursor: 'pointer' }} onClick={() => toggleItem(row.id)}>
          <span style={{ color: isTool ? '#4fc3f7' : '#8b93a7', fontSize: 10 }}>{isTool ? '⚡' : '◇'}</span>
          <span style={{ fontWeight: 500, color: '#e8eaef' }}>{titleClean()}</span>
          {row.timestamp != null && <span style={{ color: '#8b93a7', fontSize: 11, marginLeft: 'auto' }}>{fmtTime(row.timestamp)}</span>}
          {isRunning && <span style={{ width: 6, height: 6, borderRadius: '50%', background: accentColor, animation: 'hds-tool-pulse 1.2s infinite', flexShrink: 0 }} />}
          <span style={{ color: '#5a6478', marginLeft: 4 }}>{isExpanded ? '▼' : '▶'}</span>
        </div>
        {!isExpanded && row.body && <div style={{ color: '#8b93a7', fontSize: 11, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', maxWidth: '100%' }}>{row.body.slice(0, 60)}...</div>}
        {isExpanded && (
          <>
            <div style={{ color: '#c0c6d0', lineHeight: 1.45, wordBreak: 'break-word', maxHeight: 200, overflow: 'auto' }} dangerouslySetInnerHTML={{ __html: bodyEl() }} />
            {row.toolCalls?.map((tc) => {
              const statusIcon = tc.status === 'complete' ? '✓' : tc.status === 'error' ? '✗' : '●';
              const statusColor = tc.status === 'complete' ? '#4caf50' : tc.status === 'error' ? '#e53935' : accentColor;
              return (
                <div key={tc.id} style={{ marginTop: 6, padding: '4px 6px', background: 'rgba(42,49,64,0.4)', borderRadius: 4, fontSize: 11 }}>
                  <div style={{ color: statusColor }}>{statusIcon} {tc.name}</div>
                  {tc.input && Object.keys(tc.input).length > 0 && (
                    <div style={{ marginTop: 4 }}>
                      <div style={{ color: '#5a6478', marginBottom: 2 }}>输入:</div>
                      <pre style={{ color: '#8b93a7', margin: 0, whiteSpace: 'pre-wrap', wordBreak: 'break-all', fontSize: 10, maxHeight: 80, overflow: 'auto' }}>{JSON.stringify(tc.input, null, 2)}</pre>
                    </div>
                  )}
                  {tc.progress && <div style={{ color: '#8b93a7', marginTop: 2 }}>进度: {tc.progress}</div>}
                  {tc.result && (
                    <div style={{ marginTop: 4 }}>
                      <div style={{ color: '#5a6478', marginBottom: 2 }}>结果:</div>
                      <pre style={{ color: '#c0c6d0', margin: 0, whiteSpace: 'pre-wrap', wordBreak: 'break-all', fontSize: 10, maxHeight: 100, overflow: 'auto' }}>{tc.result.slice(0, 500)}</pre>
                    </div>
                  )}
                </div>
              );
            })}
          </>
        )}
      </div>
    );
  };

  const hasInferContent = currentInfer?.thinkingSnippet;
  const hasProcessRows = processRows.length > 0;
  const hasContent = hasInferContent || hasProcessRows;
  const latestInfer = agentId ? inferState[agentId] : null;

  if (!sessionId) return null;

  return (
    <div style={{ background: 'rgba(26,31,42,0.95)', borderTop: '1px solid #2a3140', maxHeight: collapsed ? 40 : 300, overflow: collapsed ? 'hidden' : 'auto', transition: 'max-height 0.2s ease' }}>
      <div style={{ display: 'flex', alignItems: 'center', padding: '8px 12px', borderBottom: collapsed ? 'none' : '1px solid #2a3140', cursor: 'pointer', userSelect: 'none', position: 'sticky', top: 0, background: 'rgba(26,31,42,0.98)', zIndex: 1 }} onClick={() => setCollapsed(!collapsed)}>
        <span style={{ color: '#8b93a7', fontSize: 12, marginRight: 6 }}>{collapsed ? '▶' : '▼'}</span>
        <span style={{ fontSize: 12, fontWeight: 500, color: '#e8eaef' }}>推理 · 工具</span>
        {hasContent && !collapsed && <span style={{ marginLeft: 6, fontSize: 10, color: '#5a6478' }}>({processRows.length} 项)</span>}
        {!collapsed && hasContent && (
          <div style={{ marginLeft: 'auto', display: 'flex', gap: 4 }}>
            <button onClick={(e) => { e.stopPropagation(); expandAll(); }} style={{ background: 'transparent', border: '1px solid #2a3140', borderRadius: 4, color: '#8b93a7', fontSize: 10, padding: '2px 6px', cursor: 'pointer' }}>全部展开</button>
            <button onClick={(e) => { e.stopPropagation(); collapseAll(); }} style={{ background: 'transparent', border: '1px solid #2a3140', borderRadius: 4, color: '#8b93a7', fontSize: 10, padding: '2px 6px', cursor: 'pointer' }}>全部折叠</button>
          </div>
        )}
      </div>
      {!collapsed && (
        <div style={{ padding: '4px 8px' }}>
          {latestInfer?.thinkingSnippet && (
            <div style={{ marginBottom: 8, padding: '6px 8px', background: 'rgba(108,139,245,0.08)', borderRadius: 4, fontSize: 11 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 4, marginBottom: 4 }}>
                <span style={{ color: '#6c8bf5', fontSize: 10 }}>◇</span>
                <span style={{ color: '#8b93a7', fontSize: 10 }}>实时推理</span>
                {latestInfer.phase === 'thinking' && <span style={{ width: 4, height: 4, borderRadius: '50%', background: '#6c8bf5', animation: 'hds-tool-pulse 1.2s infinite' }} />}
              </div>
              <div style={{ color: '#c0c6d0', lineHeight: 1.4, wordBreak: 'break-word', maxHeight: 60, overflow: 'hidden' }}>{latestInfer.thinkingSnippet}</div>
            </div>
          )}
          {processRows.map((row) => row.variant === 'reasoning' ? renderReasoningItem(row) : renderToolItem(row))}
          {!hasContent && <div style={{ textAlign: 'center', color: '#5a6478', fontSize: 12, padding: '20px 0' }}>暂无推理或工具调用</div>}
          <div ref={bottomRef} />
        </div>
      )}
    </div>
  );
}
