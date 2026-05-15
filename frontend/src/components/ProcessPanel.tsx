/**
 * ProcessPanel — React replacement for ProcessPanelRenderer.
 * Renders a single reasoning or tool-call process row.
 */
import { escapeHtml } from '../lib/formatUtils';
import type { ProcessRow } from '../types';

interface Props {
  row: ProcessRow;
}

export function ProcessPanel({ row }: Props) {
  const isTool = row.variant === 'tool';
  const isRunning = row.streaming;
  const fmtTime = (ts: number | undefined): string => {
    if (ts == null || !Number.isFinite(ts)) return '';
    const d = new Date(ts);
    return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
  };

  const titleClean = (): string => {
    let t = row.title || '';
    if (isRunning) return t.replace(/^⏳\s*/, '');
    if (isTool) return t.replace(/^[🔧⚡→]\s*/, '');
    return '思考';
  };

  const bodyEl = (): string => {
    const b = row.body || '';
    if (isRunning && !b) return '…';
    return escapeHtml(b).replace(/\n/g, '<br>');
  };

  const accentColor = isTool ? '#4fc3f7' : '#6c8bf5';

  return (
    <div
      className="ppro-row"
      style={{
        borderLeft: `3px solid ${isRunning ? accentColor : '#2a3140'}`,
        background: isRunning
          ? isTool
            ? 'rgba(79,195,247,0.06)'
            : 'rgba(108,139,245,0.06)'
          : 'transparent',
        padding: '6px 8px',
        marginBottom: 4,
        borderRadius: 4,
        fontSize: 12,
      }}
    >
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 4 }}>
        <span style={{ color: isTool ? '#4fc3f7' : '#8b93a7', fontSize: 10 }}>
          {isTool ? '⚡' : '◇'}
        </span>
        <span style={{ fontWeight: 500, color: '#e8eaef' }}>{titleClean()}</span>
        {row.timestamp != null && (
          <span style={{ color: '#8b93a7', fontSize: 11, marginLeft: 'auto' }}>
            {fmtTime(row.timestamp)}
          </span>
        )}
        {isRunning && (
          <span
            style={{
              width: 6,
              height: 6,
              borderRadius: '50%',
              background: accentColor,
              animation: 'hds-tool-pulse 1.2s infinite',
              flexShrink: 0,
            }}
          />
        )}
      </div>

      {/* Body */}
      <div
        style={{ color: '#c0c6d0', lineHeight: 1.45, wordBreak: 'break-word' }}
        dangerouslySetInnerHTML={{ __html: bodyEl() }}
      />

      {/* Tool calls */}
      {row.toolCalls?.map((tc) => {
        const statusIcon =
          tc.status === 'complete' ? '✓' : tc.status === 'error' ? '✗' : '●';
        const statusColor =
          tc.status === 'complete' ? '#4caf50' : tc.status === 'error' ? '#e53935' : accentColor;

        return (
          <div
            key={tc.id}
            style={{
              marginTop: 6,
              padding: '4px 6px',
              background: 'rgba(42,49,64,0.4)',
              borderRadius: 4,
              fontSize: 11,
            }}
          >
            <div style={{ color: statusColor }}>
              {statusIcon} {tc.name}
            </div>
            {tc.input && (
              <div style={{ color: '#8b93a7', marginTop: 2, whiteSpace: 'pre-wrap' }}>
                {JSON.stringify(tc.input, null, 2).slice(0, 200)}
              </div>
            )}
            {tc.progress && (
              <div style={{ color: '#8b93a7', marginTop: 2 }}>{tc.progress}</div>
            )}
            {tc.result && (
              <div style={{ color: '#c0c6d0', marginTop: 2, whiteSpace: 'pre-wrap' }}>
                {tc.result.slice(0, 300)}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
