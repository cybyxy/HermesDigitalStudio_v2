/**
 * TaskList — React replacement for TaskListRenderer.
 * Renders plan task rows with status dots, progress bar, and actions.
 */
import type { PlanArtifact, AgentInfo } from '../types';

interface PlanBundle {
  planId: number;
  artifact: PlanArtifact;
  anchorTs: number;
  dbPlan: { status: string; steps: Array<{ stepIndex?: number; stepTitle?: string; title?: string; status?: string; executor?: string }> } | null;
  sessionId?: string;
}

interface Props {
  bundles: PlanBundle[];
  agents: Array<{ agentId: string; displayName?: string }>;
  selectedPlanId: number | null;
  onSelectPlan?: (planId: number) => void;
  onDeletePlan?: (planId: number) => void;
}

function fmtTs(ts: number): string {
  const d = new Date(ts);
  return `${String(d.getMonth() + 1).padStart(2, '0')}/${String(d.getDate()).padStart(2, '0')} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
}

function escHtml(s: string): string {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

function maxMs(timestamps: number[]): number {
  let max = 0;
  for (const t of timestamps) {
    const ms = t > 0 && t < 1e11 ? t * 1000 : t;
    if (ms > max) max = ms;
  }
  return max;
}

export function TaskList({ bundles, agents, selectedPlanId, onSelectPlan, onDeletePlan }: Props) {
  if (!bundles.length) {
    return <div style={{ textAlign: 'center', color: '#8b93a7', padding: 20, fontSize: 13 }}>暂无任务规划</div>;
  }

  const agentLabel = (agentId: string): string => {
    const a = agents.find((x) => x.agentId === agentId);
    return a?.displayName || agentId;
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
      {bundles.map((b) => {
        const plan = b.artifact;
        if (!plan) return null;

        const dbPlan = b.dbPlan;
        const steps = dbPlan?.steps ?? [];
        const doneCount = steps.filter((s) => s.status === 'done').length;
        const activeCount = steps.filter((s) => s.status === 'active').length;
        const errorCount = steps.filter((s) => s.status === 'error').length;
        const total = steps.length;
        const pct = total > 0 ? Math.round((doneCount / total) * 100) : 0;

        let statusLabel = '准备中';
        let statusColor = '#8b93a7';
        if (errorCount > 0 && doneCount === 0) {
          statusLabel = '失败';
          statusColor = '#e53935';
        } else if (doneCount === total) {
          statusLabel = '已完成';
          statusColor = '#4caf50';
        } else if (activeCount > 0) {
          statusLabel = '进行中';
          statusColor = '#5b8cff';
        }

        const barColor = errorCount > 0 ? '#e53935' : doneCount === total ? '#4caf50' : '#5b8cff';
        const planner = steps[0]?.executor || '';
        const allExecutors = [...new Set(steps.map((s) => s.executor).filter((e): e is string => !!e))];
        const collaborators = allExecutors.filter((e) => e !== planner);

        const timestamps = [
          b.anchorTs,
          ...steps.map((s) => (s as Record<string, unknown>).startedAt as number).filter(Boolean),
          ...steps.map((s) => (s as Record<string, unknown>).completedAt as number).filter(Boolean),
        ];
        const latest = maxMs(timestamps);

        return (
          <div
            key={b.planId}
            onClick={() => onSelectPlan?.(b.planId)}
            style={{
              padding: '8px 10px',
              background: selectedPlanId === b.planId ? 'rgba(91,140,255,0.1)' : 'rgba(42,49,64,0.3)',
              border: `1px solid ${selectedPlanId === b.planId ? '#5b8cff' : '#2a3140'}`,
              borderRadius: 6,
              cursor: onSelectPlan ? 'pointer' : 'default',
            }}
          >
            {/* Name */}
            <div style={{ fontWeight: 500, fontSize: 13, color: '#e8eaef', marginBottom: 4 }}>
              {escHtml(plan.name || 'Unnamed Plan')}
            </div>

            {/* Status dots */}
            {total > 0 && (
              <div style={{ display: 'flex', gap: 2, marginBottom: 4 }}>
                {steps.map((s, i) => (
                  <span
                    key={i}
                    title={s.stepTitle || s.title || `Step ${i + 1}`}
                    style={{
                      width: 6,
                      height: 6,
                      borderRadius: '50%',
                      background: s.status === 'done' ? '#4caf50' : s.status === 'active' ? '#5b8cff' : s.status === 'error' ? '#e53935' : '#2a3140',
                      flexShrink: 0,
                    }}
                  />
                ))}
              </div>
            )}

            {/* Progress bar */}
            {total > 0 && (
              <div style={{ marginBottom: 4 }}>
                <div style={{ height: 4, background: '#1a2230', borderRadius: 2, overflow: 'hidden' }}>
                  <div style={{ height: '100%', width: `${pct}%`, background: barColor, borderRadius: 2 }} />
                </div>
                <span style={{ fontSize: 10, color: '#8b93a7' }}>{pct}%</span>
              </div>
            )}

            {/* Meta */}
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, fontSize: 11, color: '#8b93a7' }}>
              <span style={{ color: statusColor }}>{statusLabel}</span>
              {planner && <span>🧠 {agentLabel(planner)}</span>}
              {collaborators.map((c) => (
                <span key={c}>🤝 {agentLabel(c)}</span>
              ))}
              {latest > 0 && <span>{fmtTs(latest)}</span>}
            </div>

            {/* Active pulse */}
            {activeCount > 0 && (
              <span
                style={{
                  display: 'inline-block',
                  width: 6,
                  height: 6,
                  borderRadius: '50%',
                  background: '#5b8cff',
                  marginLeft: 4,
                  animation: 'hds-tool-pulse 1.2s infinite',
                }}
              />
            )}

            {/* Delete button */}
            {b.planId > 0 && onDeletePlan && (
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  onDeletePlan(b.planId);
                }}
                style={{
                  marginTop: 6,
                  background: 'none',
                  border: '1px solid #2a3140',
                  borderRadius: 4,
                  color: '#8b93a7',
                  cursor: 'pointer',
                  fontSize: 11,
                  padding: '2px 8px',
                }}
              >
                删除
              </button>
            )}
          </div>
        );
      })}
    </div>
  );
}
