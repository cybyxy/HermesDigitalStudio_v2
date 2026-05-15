/**
 * PlanTimeline — React replacement for class-based PlanTimelineRenderer.
 * Renders plan timeline with step rows, status dots, agent chips, and deliverables.
 * Step result popups use React portals for drag support.
 */
import { useState, useCallback, useRef, useEffect, type CSSProperties } from 'react';
import { createPortal } from 'react-dom';
import { useSessionStore } from '../stores/sessionStore';
import { useAgentStore } from '../stores/agentStore';
import { usePlanStore } from '../stores/planStore';
import { apiGetStepResult } from '../api/plans';
import type { PlanSummary, PlanStepDb } from '../api/types';
import type {
  PlanArtifact,
  PlanStep,
  PlanTimelineRunState,
  AgentInfo,
} from '../types';

// CSS classes are in planTimeline.css (already imported globally)

interface Props {
  onOpenPath?: (path: string) => void;
  fetchDbPlan?: {
    status: string;
    steps: Array<{ stepIndex: number; stepStatus: string }>;
  } | null;
}

/* ------------------------------------------------------------------ */
/*  Helpers                                                             */
/* ------------------------------------------------------------------ */

function stepLabel(st: PlanTimelineRunState['stepStatuses'][number]): string {
  if (st === 'done') return '已完成';
  if (st === 'active') return '进行中';
  return '未完成';
}

function confidenceColor(conf: PlanStep['confidence']): string {
  if (conf === 'high') return '#4ade80';
  if (conf === 'low') return '#94a3b8';
  return '#fbbf24';
}

function agentLabel(
  agents: { agentId: string; displayName?: string }[],
  agentId: string,
): string {
  const a = agents.find((x) => x.agentId === agentId);
  return a?.displayName?.trim() || a?.agentId || agentId || '—';
}

/* Converts PlanSummary from DB to the internal bundle used by renderTimeline */
function planBundleFromSummary(plan: PlanSummary): {
  artifact: PlanArtifact;
  anchorTs: number;
  dbPlan: {
    status: string;
    steps: Array<{
      stepIndex: number;
      stepStatus: string;
      completedAt?: number;
      executor?: string;
      sessionId?: string;
      stepId?: number | string;
      result?: string | null;
    }>;
  };
} {
  const artifactSteps = (plan.steps ?? []).map((s: PlanStepDb) => ({
    id: s.stepIndex,
    title: s.title ?? `步骤 ${s.stepIndex}`,
    action: s.action ?? '',
    filePath: s.filePath,
    confidence: 'high' as const,
  }));
  return {
    artifact: {
      name: plan.name ?? '未命名规划',
      planSummary: plan.planSummary ?? '',
      steps: artifactSteps,
      plannerAgentId: plan.agentId,
    },
    anchorTs: plan.createdAt ?? 0,
    dbPlan: {
      status: plan.status ?? 'pending',
      steps: (plan.steps ?? []).map((s: PlanStepDb) => ({
        stepIndex: s.stepIndex,
        stepStatus: s.stepStatus,
        completedAt: s.completedAt,
        executor: s.executor,
        sessionId: s.sessionId,
        stepId: s.stepId,
        result: s.result,
      })),
    },
  };
}

/* Align DB step rows with artifact steps (handles stepIndex type mismatches) */
function resolveDbStepRow(
  dbPlan:
    | {
        steps: Array<{
          stepIndex?: number | string;
          stepId?: number | string;
          sessionId?: string;
          completedAt?: number | string | null;
          executor?: string;
          result?: string | null;
        }>;
      }
    | null
    | undefined,
  idx: number,
  step: PlanStep,
):
  | {
      stepIndex?: number | string;
      stepId?: number | string;
      sessionId?: string;
      completedAt?: number | string | null;
      executor?: string;
      result?: string | null;
    }
  | undefined {
  const rows = dbPlan?.steps;
  if (!rows?.length) return undefined;
  const idNum = Number(step.id);
  const byIndex = rows.find((s) => Number(s.stepIndex) === idx);
  if (byIndex) return byIndex;
  if (Number.isFinite(idNum)) {
    const byStepIndexEqId = rows.find((s) => Number(s.stepIndex) === idNum);
    if (byStepIndexEqId) return byStepIndexEqId;
    const byStepId = rows.find((s) => Number(s.stepId) === idNum);
    if (byStepId) return byStepId;
  }
  return rows[idx];
}

function effectiveStepStatuses(
  artifact: PlanArtifact,
  anchorTs: number,
  run: PlanTimelineRunState | null,
  dbPlan?: {
    status: string;
    steps: Array<{
      stepIndex: number;
      stepStatus: string;
    }>;
  } | null,
): PlanTimelineRunState['stepStatuses'] {
  const n = artifact.steps.length;
  if (run && run.planAnchorTs === anchorTs && run.stepStatuses.length === n) {
    return run.stepStatuses;
  }
  if (dbPlan?.steps) {
    return dbPlan.steps.map((s) => s.stepStatus as PlanTimelineRunState['stepStatuses'][number]);
  }
  return Array(n).fill('pending');
}

function parseDeliverable(text: string): {
  text: string;
  files: string[];
  dirs: string[];
} {
  const files: string[] = [];
  const dirs: string[] = [];
  const fileMatch = text.match(/\[文件[列表]?\]([\s\S]*?)(?=\[目录|$)/i);
  const dirMatch = text.match(/\[目录[列表]?\]([\s\S]*?)$/i);
  if (fileMatch) {
    fileMatch[1].replace(/^\s*`([^`]+)`\s*$/gm, (_, f) => {
      const trimmed = f.trim();
      if (trimmed) files.push(trimmed);
      return '';
    });
  }
  if (dirMatch) {
    dirMatch[1].replace(/^\s*`([^`]+)`\s*$/gm, (_, d) => {
      const trimmed = d.trim();
      if (trimmed) dirs.push(trimmed.replace(/\/$/, ''));
      return '';
    });
  }
  return { text, files, dirs };
}

/* ------------------------------------------------------------------ */
/*  Types                                                              */
/* ------------------------------------------------------------------ */

interface DbStepEntry {
  stepIndex?: number | string;
  stepId?: number | string;
  sessionId?: string;
  completedAt?: number | string | null;
  executor?: string;
  result?: string | null;
}

/* ------------------------------------------------------------------ */
/*  StepResultPopup — draggable floating popup (portal)                */
/* ------------------------------------------------------------------ */

interface PopupState {
  stepIdx: number;
  stepSessionId: string;
  completedAtNum: number;
  executor?: string;
  stepResultCached: string;
}

function StepResultPopup({
  state,
  onClose,
}: {
  state: PopupState;
  onClose: () => void;
}) {
  const [content, setContent] = useState<string | null>(null);
  const [status, setStatus] = useState<'loading' | 'loaded' | 'empty' | 'error'>('loading');
  const [pos, setPos] = useState({ top: 80, right: 20 });
  const dragRef = useRef<{ x: number; y: number; dragging: boolean }>({
    x: 0,
    y: 0,
    dragging: false,
  });

  const { stepIdx, stepSessionId, completedAtNum, executor, stepResultCached } = state;

  // Compute executor label
  const executorLabel = (() => {
    const agents = useAgentStore.getState().agents;
    const sessions = useSessionStore.getState().sessions;
    const execRaw = (executor ?? '').trim();
    if (execRaw) {
      const byExecId = agents.find((a) => a.agentId === execRaw);
      return (byExecId?.displayName?.trim() || byExecId?.agentId) || execRaw;
    }
    const session = sessions.find((s) => s.id === stepSessionId);
    const sessionAgent = session
      ? agents.find((a) => a.agentId === session.agentId)
      : undefined;
    return sessionAgent?.displayName?.trim() || sessionAgent?.agentId || '—';
  })();

  const timeStr = (() => {
    const ms =
      Number.isFinite(completedAtNum) && completedAtNum > 0
        ? completedAtNum < 1e12
          ? completedAtNum * 1000
          : completedAtNum
        : NaN;
    return Number.isFinite(ms)
      ? new Date(ms).toLocaleString('zh-CN', {
          year: 'numeric',
          month: '2-digit',
          day: '2-digit',
          hour: '2-digit',
          minute: '2-digit',
          second: '2-digit',
        })
      : '—';
  })();

  const canShowStepResult =
    Boolean(stepSessionId) && Number.isFinite(completedAtNum) && completedAtNum > 0;

  // Drag handlers
  const onMouseDown = useCallback(
    (e: React.MouseEvent) => {
      dragRef.current = { x: e.clientX, y: e.clientY, dragging: true };
    },
    [],
  );
  useEffect(() => {
    const onMove = (e: MouseEvent) => {
      if (!dragRef.current.dragging) return;
      const dx = e.clientX - dragRef.current.x;
      const dy = e.clientY - dragRef.current.y;
      dragRef.current.x = e.clientX;
      dragRef.current.y = e.clientY;
      setPos((prev) => ({
        top: Math.max(0, prev.top + dy),
        right: Math.max(0, prev.right - dx),
      }));
    };
    const onUp = () => {
      dragRef.current.dragging = false;
    };
    document.addEventListener('mousemove', onMove);
    document.addEventListener('mouseup', onUp);
    return () => {
      document.removeEventListener('mousemove', onMove);
      document.removeEventListener('mouseup', onUp);
    };
  }, []);

  // Load step result
  useEffect(() => {
    if (stepResultCached && !canShowStepResult) {
      setContent(stepResultCached);
      setStatus('loaded');
      return;
    }
    let cancelled = false;
    (async () => {
      try {
        let atParam = completedAtNum;
        if (atParam > 1e12) atParam = atParam / 1000;
        const data = await apiGetStepResult(stepSessionId, atParam);
        if (cancelled) return;
        const fromHistory = data.result?.text?.trim() ?? '';
        if (fromHistory) {
          setContent(fromHistory);
          setStatus('loaded');
        } else if (stepResultCached) {
          setContent(stepResultCached);
          setStatus('loaded');
        } else {
          setStatus('empty');
        }
      } catch {
        if (cancelled) return;
        if (stepResultCached) {
          setContent(stepResultCached);
          setStatus('loaded');
        } else {
          setStatus('error');
        }
      }
    })();
    return () => { cancelled = true; };
  }, [stepSessionId, completedAtNum, stepResultCached, canShowStepResult]);

  const popupStyle: CSSProperties = {
    position: 'fixed',
    top: pos.top,
    right: pos.right,
    zIndex: 10000,
    background: '#1e2433',
    border: '1px solid rgba(91, 140, 255, 0.3)',
    borderRadius: 12,
    width: 420,
    maxHeight: '70vh',
    display: 'flex',
    flexDirection: 'column',
    boxShadow: '0 12px 40px rgba(0,0,0,0.4)',
  };

  return createPortal(
    <div style={popupStyle} data-step-idx={stepIdx}>
      <div
        className="step-result-popup__header"
        onMouseDown={onMouseDown}
      >
        <div className="step-result-popup__title-meta">
          <span className="step-result-popup__title">第 {stepIdx + 1} 步推理结果</span>
          <div className="step-result-popup__meta">
            <div className="step-result-popup__meta-row">
              <span className="step-result-popup__meta-k">执行 Agent</span>
              <span className="step-result-popup__meta-v">{executorLabel}</span>
            </div>
            <div className="step-result-popup__meta-row">
              <span className="step-result-popup__meta-k">完成时间</span>
              <span className="step-result-popup__meta-v">{timeStr}</span>
            </div>
          </div>
        </div>
        <button className="step-result-popup__close" onClick={onClose}>
          ✕
        </button>
      </div>
      <div className={`step-result-popup__content step-result-popup__content--${status}`}>
        {status === 'loading' && '加载中…'}
        {status === 'empty' && '无推理结果'}
        {status === 'error' && '加载失败'}
        {status === 'loaded' && content}
      </div>
    </div>,
    document.body,
  );
}

/* ------------------------------------------------------------------ */
/*  PlanTimeline                                                        */
/* ------------------------------------------------------------------ */

export function PlanTimeline({ onOpenPath, fetchDbPlan }: Props) {
  const leftPanelTaskPlanId = usePlanStore((s) => s.leftPanelTaskPlanId);
  const taskListPlans = usePlanStore((s) => s.taskListPlans);
  const agents = useAgentStore((s) => s.agents);
  const sessions = useSessionStore((s) => s.sessions);
  const activeId = useSessionStore((s) => s.activeId);
  const planTimelineRun = usePlanStore((s) => s.planTimelineRun);
  const agentLastPlan = usePlanStore((s) => s.agentLastPlan);
  const setLeftPanelTaskPlanId = usePlanStore((s) => s.setLeftPanelTaskPlanId);

  // Step result popup state
  const [popup, setPopup] = useState<PopupState | null>(null);

  // --- Compute plan data ---
  const selectedId = leftPanelTaskPlanId;
  const selectedPlan =
    selectedId != null
      ? taskListPlans.find((p) => p.id === selectedId)
      : undefined;

  let artifact: PlanArtifact | null = null;
  let anchorTs = 0;
  let dbPlan:
    | {
        status: string;
        steps: Array<{
          stepIndex: number;
          stepStatus: string;
          completedAt?: number;
          executor?: string;
          sessionId?: string;
          stepId?: number | string;
          result?: string | null;
        }>;
      }
    | null
    | undefined = fetchDbPlan;

  if (selectedPlan) {
    const b = planBundleFromSummary(selectedPlan);
    artifact = b.artifact;
    anchorTs = b.anchorTs;
    dbPlan = fetchDbPlan ?? b.dbPlan;
  } else {
    const activeSession = sessions.find((s) => s.id === activeId);
    const agentPlan = activeSession
      ? agentLastPlan[activeSession.agentId ?? ''] ?? null
      : null;
    artifact = agentPlan?.artifact ?? null;
    anchorTs = agentPlan?.anchorTs ?? 0;
    if (fetchDbPlan === undefined) {
      dbPlan = agentPlan?.dbPlan ?? null;
    }
  }

  // Fix: if selectedId is set but plan not found, reset
  useEffect(() => {
    if (selectedId != null && selectedId !== undefined && !selectedPlan) {
      usePlanStore.getState().setLeftPanelTaskPlanId(null);
    }
  }, [selectedId, taskListPlans]);

  const run = planTimelineRun;
  const deliverable =
    run && run.planAnchorTs === anchorTs ? run.deliverable ?? null : null;

  // --- Empty state ---
  if (!artifact || (!artifact.planSummary && artifact.steps.length === 0)) {
    return <div className="pt-empty">暂无任务规划</div>;
  }

  const stepStatuses = effectiveStepStatuses(artifact, anchorTs, run, dbPlan);

  // Toggle step result popup
  const toggleStepPopup = useCallback(
    (idx: number, dbEntry: DbStepEntry | undefined, step: PlanStep) => {
      if (popup?.stepIdx === idx) {
        setPopup(null);
        return;
      }

      const stepSessionId = dbEntry?.sessionId?.trim?.() ? dbEntry.sessionId.trim() : '';
      const stepCompletedAt = dbEntry?.completedAt;
      const stepExecutor = dbEntry?.executor;
      const stepResultCached =
        typeof dbEntry?.result === 'string' && dbEntry.result.trim()
          ? dbEntry.result.trim()
          : '';

      const completedAtNum =
        stepCompletedAt == null || stepCompletedAt === ''
          ? NaN
          : Number(stepCompletedAt);

      const canShowStepResult =
        Boolean(stepSessionId) && Number.isFinite(completedAtNum) && completedAtNum > 0;

      if (canShowStepResult || stepResultCached) {
        setPopup({
          stepIdx: idx,
          stepSessionId,
          completedAtNum,
          executor: stepExecutor,
          stepResultCached,
        });
      }
    },
    [popup],
  );

  return (
    <>
      {/* Plan header */}
      <div className="pt-plan-header">
        {artifact.name && (
          <div className="pt-plan-header__name">{artifact.name}</div>
        )}
        <PlanHeaderAgentsRow
          artifact={artifact}
          dbPlan={dbPlan}
          agents={agents}
        />
      </div>

      {/* Plan summary */}
      {artifact.planSummary && (
        <div className="pt-summary">{artifact.planSummary}</div>
      )}

      {/* Step rows */}
      {artifact.steps.map((step, idx) => {
        const st = stepStatuses[idx] ?? 'pending';
        const stepDb = resolveDbStepRow(dbPlan, idx, step);
        const stepSessionId = stepDb?.sessionId?.trim?.() ? stepDb.sessionId.trim() : '';
        const stepCompletedAt = stepDb?.completedAt;
        const stepResultCached =
          typeof stepDb?.result === 'string' && stepDb.result.trim()
            ? stepDb.result.trim()
            : '';

        const completedAtNum =
          stepCompletedAt == null || stepCompletedAt === ''
            ? NaN
            : Number(stepCompletedAt);
        const canShowStepResult =
          Boolean(stepSessionId) &&
          Number.isFinite(completedAtNum) &&
          completedAtNum > 0;
        const isClickable = canShowStepResult || Boolean(stepResultCached);

        return (
          <div
            key={`${step.id}-${idx}`}
            className={`pt-step-row${isClickable ? ' pt-step-row--clickable' : ''}`}
            style={{
              paddingBottom: idx < artifact.steps.length - 1 ? 14 : 2,
            }}
            onClick={
              isClickable
                ? () => toggleStepPopup(idx, stepDb, step)
                : undefined
            }
          >
            {/* Rail */}
            <div className="pt-rail">
              <div className={`pt-dot pt-dot--${st}`} />
              {idx < artifact.steps.length - 1 && <div className="pt-connector" />}
            </div>

            {/* Body */}
            <div className="pt-body">
              <div className="pt-head">
                <span>
                  {idx + 1}. {step.title}
                </span>
                <span className={`pt-status-tag pt-status-tag--${st}`}>
                  {stepLabel(st)}
                </span>
              </div>
              <div className="pt-action">{step.action}</div>
              {step.filePath && (
                <div className="pt-filepath">{step.filePath}</div>
              )}
              <div className="pt-badge">
                <span
                  className={`pt-conf-tag pt-conf--${step.confidence}`}
                  style={{ background: confidenceColor(step.confidence) }}
                >
                  置信 {step.confidence}
                </span>
                {stepDb?.executor && agents.length > 0 && (
                  <span className="pt-agent-tag">
                    {agentLabel(agents, stepDb.executor)}
                  </span>
                )}
              </div>
            </div>
          </div>
        );
      })}

      {/* Deliverables */}
      <DeliverablesSection
        deliverable={deliverable}
        onOpenPath={onOpenPath}
      />

      {/* Step result popup */}
      {popup && (
        <StepResultPopup
          state={popup}
          onClose={() => setPopup(null)}
        />
      )}
    </>
  );
}

/* ------------------------------------------------------------------ */
/*  PlanHeaderAgentsRow — planner + collaborator chips                 */
/* ------------------------------------------------------------------ */

function PlanHeaderAgentsRow({
  artifact,
  dbPlan,
  agents,
}: {
  artifact: PlanArtifact;
  dbPlan:
    | { steps: Array<{ executor?: string }> }
    | null
    | undefined;
  agents: AgentInfo[];
}) {
  const execAgents = new Set<string>();
  for (const s of dbPlan?.steps ?? []) {
    if (s.executor) execAgents.add(s.executor);
  }
  const execList = [...execAgents];

  return (
    <div className="pt-plan-header__agents-row">
      <div className="pt-plan-header__agent-chip pt-plan-header__agent-chip--planner">
        🧠 规划
      </div>
      {artifact.plannerAgentId && agents.length > 0 && (
        <div className="pt-plan-header__agent-chip">
          {agentLabel(agents, artifact.plannerAgentId)}
        </div>
      )}
      {execList.length > 0 && agents.length > 0 && (
        <>
          <div className="pt-plan-header__agent-chip pt-plan-header__agent-chip--collab">
            🤝 协作
          </div>
          {execList.map((eid) => (
            <div key={eid} className="pt-plan-header__agent-chip">
              {agentLabel(agents, eid)}
            </div>
          ))}
        </>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  DeliverablesSection                                                 */
/* ------------------------------------------------------------------ */

function DeliverablesSection({
  deliverable,
  onOpenPath,
}: {
  deliverable: NonNullable<PlanTimelineRunState['deliverable']> | null;
  onOpenPath?: (path: string) => void;
}) {
  const parsed = deliverable
    ? parseDeliverable(deliverable.text || '')
    : { text: '', files: [], dirs: [] };
  const { text, files } = parsed;

  const notesText = text
    .replace(/\[文件[列表]?\][\s\S]*?(?=\[目录|$)/gi, '')
    .replace(/\[目录[列表]?\][\s\S]*$/gi, '')
    .trim();

  return (
    <>
      {/* Notes */}
      <div className="deliv-notes">
        <div className="deliv-notes__title">📋 重要说明</div>
        <div className="deliv-notes__text">{notesText || '（无）'}</div>
      </div>

      {/* Files */}
      <div className="deliv-notes">
        <div className="deliv-notes__title">📁 文件</div>
        <div
          className={
            files.length > 0
              ? 'deliv-notes__text deliv-notes__text--list'
              : 'deliv-notes__text'
          }
        >
          {files.length === 0
            ? '（无）'
            : files.map((file) => (
                <div
                  key={file}
                  className="deliv-item"
                  title={file}
                  onClick={() => {
                    const dir = file.substring(0, file.lastIndexOf('/')) || '.';
                    onOpenPath?.(dir);
                  }}
                >
                  <span className="deliv-item__icon" style={{ color: '#5b8cff' }}>
                    📄
                  </span>
                  <span className="deliv-item__path">{file}</span>
                </div>
              ))}
        </div>
      </div>
    </>
  );
}
