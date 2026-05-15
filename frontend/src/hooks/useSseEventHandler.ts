/**
 * useSseEventHandler — Core SSE event dispatcher.
 * Maps Hermes SSE events to domain store state updates.
 *
 * Uses split stores: sessionStore, agentStore, planStore, appStore.
 */
import { useCallback } from 'react';
import { useSessionStore } from '../stores/sessionStore';
import { useAgentStore } from '../stores/agentStore';
import { usePlanStore } from '../stores/planStore';
import { useAppStore } from '../stores/appStore';
import { eventSessionId } from '../lib/sseEventProcessor';
import type { HermesEventParams, PlanTimelineStepStatus, ChatRow, ProcessRow } from '../types';
import { isOrchestrationRejected } from '../lib/handoffParser';

/** 模块级缓存 sid -> agentId 映射，在 hook 重渲染间保持不变 */
const sessionAgentCache = new Map<string, string>();

/**
 * 健壮的 agentId 解析器：
 * 1. 优先使用 payload 中的 agentId
 * 2. 其次使用缓存的 sid -> agentId 映射
 * 3. 最后从 sessionStore 中的 session 数据查找 agentId
 * 4. 兜底返回 sid
 */
function resolveAgentId(
  sid: string,
  payload: Record<string, unknown>,
): string {
  // 1. 检查 payload 是否携带 agentId
  const fromPayload = String(payload.agentId ?? '');
  if (fromPayload) return fromPayload;

  // 2. 检查缓存
  const fromCache = sessionAgentCache.get(sid);
  if (fromCache) return fromCache;

  // 3. 从 sessionStore 查 session 的 agentId
  const sessionStore = useSessionStore.getState();
  const session = sessionStore.sessions.find((s) => s.id === sid);
  if (session?.agentId) {
    sessionAgentCache.set(sid, session.agentId);
    return session.agentId;
  }

  // 4. 兜底返回 sid
  return sid;
}

export function useSseEventHandler() {
  const handleEvent = useCallback((p: HermesEventParams): void => {
    const sid = eventSessionId(p);
    const type = String(p.type ?? '');
    const payload = (p.payload || {}) as Record<string, unknown>;
    const sessionStore = useSessionStore.getState();

    // --- Message events ---
    if (type === 'message.start') {
      console.log('[SSEHandler] message.start sid:', sid);
      const text = String(payload.text ?? '');
      const agentId = String(payload.agentId ?? '');
      const agentName = String(payload.agentName ?? '');
      const agentAvatar = String(payload.agentAvatar ?? '');
      const newMsg: ChatRow = {
        role: 'assistant' as const,
        text,
        streaming: true,
        agentId,
        agentName,
        agentAvatar,
        timestamp: Date.now(),
      };
      sessionStore.appendChat(sid, newMsg);
      sessionStore.setStreaming(sid, true);

      // 缓存 sid -> agentId 映射
      if (agentId) {
        sessionAgentCache.set(sid, agentId);
        useAgentStore.getState().setInferState(agentId, 'active', {
          phase: 'thinking',
          message: '思考中…',
        });
      }
    } else if (type === 'message.delta') {
      const delta = String(payload.text ?? payload.delta ?? '');
      console.log('[SSEHandler] message.delta:', delta.slice(0, 40));
      sessionStore.appendDelta(sid, delta);
    } else if (type === 'message.complete') {
      console.log('[SSEHandler] message.complete sid:', sid);
      sessionStore.finalizeMessage(sid, payload);
      // 完成推理行（停止流式动画）
      sessionStore.finalizeReasoning(sid);
      // Parse plan artifact
      const planJson = payload.planArtifact ?? payload.plan_artifact;
      if (planJson && typeof planJson === 'object') {
        sessionStore.setPlanArtifact(sid, planJson as Record<string, unknown>);
      }
      // Set infer bubble to 'done' briefly (5s), then idle
      const completeAgentId = resolveAgentId(sid, payload);
      if (completeAgentId) {
        // 从 messages 获取最终的回答文本
        const curState = useSessionStore.getState();
        const session = curState.sessions.find((s) => s.id === sid);
        const lastMsg = session?.messages?.length
          ? session.messages[session.messages.length - 1]
          : null;
        const resultText = (lastMsg?.role === 'assistant' ? lastMsg.text : '') || '回答完成';

        const agentStore = useAgentStore.getState();
        agentStore.setInferState(completeAgentId, 'done', {
          phase: 'done',
          message: resultText,
        });

        // 如果回答文本超过 50 字，自动弹出结果弹窗
        if (resultText.length > 50) {
          agentStore.setReasoningResultModal({
            agentId: completeAgentId,
            text: resultText,
          });
        }
      }
    } else if (type === 'thinking.delta' || type === 'reasoning.delta') {
      const text = String(payload.text ?? payload.delta ?? '');
      const agentId = resolveAgentId(sid, payload);
      const agentStore = useAgentStore.getState();
      agentStore.appendReasoning(agentId, text);
      // 同时写入 processRows，用于右侧面板工具面板展示
      sessionStore.appendReasoningDelta(sid, text);
    } else if (type === 'tool.generating') {
      const toolCall = payload.toolCall ?? payload.tool_call;
      sessionStore.appendToolCall(sid, toolCall as Record<string, unknown>);
      // 更新场景推理气泡：显示工具使用状态
      const agentId = resolveAgentId(sid, payload);
      if (agentId) {
        const toolName = String(
          (toolCall as Record<string, unknown>)?.name ??
          payload.name ??
          'tool',
        );
        useAgentStore.getState().setInferState(agentId, 'tool', {
          phase: 'tool',
          message: `使用 ${toolName}`,
        });
      }
    } else if (type === 'tool.progress') {
      sessionStore.updateToolProgress(sid, payload);
      // 更新场景推理气泡：显示工具进度
      const agentId = resolveAgentId(sid, payload);
      if (agentId) {
        const progress = String(payload.progress ?? payload.text ?? '');
        const toolCall = payload.toolCall as Record<string, unknown> | undefined;
        const toolName = String(toolCall?.name ?? payload.name ?? '');
        const snippet = toolName
          ? `${toolName}: ${progress.slice(0, 30)}`
          : progress.slice(0, 30);
        useAgentStore.getState().setInferState(agentId, 'tool', {
          phase: 'tool',
          message: snippet,
        });
      }
    } else if (type === 'tool.complete') {
      sessionStore.completeTool(sid, payload);
      // 尝试从工具结果中提取音频 URL，设置到 assistant 消息上
      const resultStr = String(payload.result ?? '');
      if (resultStr) {
        try {
          const parsed = JSON.parse(resultStr);
          const filePath = parsed.file_path || parsed.audio_url || parsed.mp3_url;
          if (filePath && typeof filePath === 'string') {
            const audioUrl = filePath.startsWith('http')
              ? filePath
              : `/api/media/${encodeURIComponent(filePath)}`;
            sessionStore.patchSession(sid, (session) => {
              const msgs = [...session.messages];
              const last = msgs[msgs.length - 1];
              if (last && last.role === 'assistant') {
                msgs[msgs.length - 1] = {
                  ...last,
                  mediaUrls: [...((last as { mediaUrls?: string[] }).mediaUrls ?? []), audioUrl],
                };
              }
              return { ...session, messages: msgs };
            });
          }
        } catch {
          // result 不是 JSON，忽略
        }
      }
      // 工具完成后回到 thinking 状态（后续可能继续推理）
      const agentId = resolveAgentId(sid, payload);
      if (agentId) {
        const agentStore = useAgentStore.getState();
        const currentInfer = agentStore.agentSceneInfer[agentId];
        if (currentInfer?.phase === 'tool') {
          agentStore.setInferState(agentId, 'thinking', {
            phase: 'thinking',
            message: currentInfer.thinkingSnippet || '思考中',
          });
        }
      }
    }

    // --- Plan chain events ---
    else if (type === 'plan_chain.step_begin') {
      const planAnchorTs = Number(payload.planAnchorTs ?? 0);
      const sourceSessionId = String(payload.sourceSessionId ?? '').trim() || sid;
      const index = Math.max(0, Number(payload.index ?? 0));
      const total = Math.max(1, Number(payload.total ?? 1));
      const statuses = Array<PlanTimelineStepStatus>(total).fill('pending');
      for (let j = 0; j < index; j++) statuses[j] = 'done';
      statuses[index] = 'active';
      usePlanStore.getState().setPlanTimelineRun({
        planAnchorTs,
        sourceSessionId,
        stepStatuses: statuses,
      });
    } else if (type === 'plan_chain.step_end') {
      const doneIndex = Number(payload.index ?? 0);
      const planStore = usePlanStore.getState();
      const run = planStore.planTimelineRun;
      if (run) {
        const next = [...run.stepStatuses];
        if (doneIndex >= 0 && doneIndex < next.length) next[doneIndex] = 'done';
        planStore.setPlanTimelineRun({ ...run, stepStatuses: next });
      }
    } else if (type === 'plan_chain.complete') {
      const deliverableText = String(payload.deliverable_text ?? payload.text ?? '');
      const files = (Array.isArray(payload.files) ? payload.files : []) as string[];
      const dirs = (Array.isArray(payload.dirs) ? payload.dirs : []) as string[];
      const planStore = usePlanStore.getState();
      const run = planStore.planTimelineRun;
      if (run) {
        planStore.setPlanTimelineRun({
          ...run,
          stepStatuses: run.stepStatuses.map(() => 'done' as const),
          deliverable: { text: deliverableText, files, dirs },
        });
      }
    }

    // --- Approval / Clarify ---
    else if (type === 'approval.request') {
      sessionStore.setApproval({
        sessionId: sid,
        payload: payload as Record<string, unknown>,
      });
    } else if (type === 'clarify.request') {
      sessionStore.setClarify({
        sessionId: sid,
        requestId: String(payload.requestId ?? ''),
        question: String(payload.question ?? ''),
        choices: payload.choices ?? null,
      });
    }

    // --- Session info ---
    else if (type === 'session.info') {
      sessionStore.updateSessionInfo(sid, payload);
    }

    // --- Handoff / Orchestration reject ---
    else if (type === 'orch_rejected' || isOrchestrationRejected(payload)) {
      useAppStore.getState().setWsConnected(true);
    }

    // --- Session switch (context compression → new session) ---
    else if (type === 'session.switch') {
      const oldSid = String(payload.old_session_id ?? '');
      const newSid = String(payload.new_session_id ?? '');
      if (oldSid && newSid && oldSid !== newSid) {
        console.log('[SSEHandler] session.switch:', oldSid, '→', newSid);
        const agentId = resolveAgentId(oldSid, payload);
        const newSession: import('../types').SessionState = {
          id: newSid,
          agentId,
          title: '',
          messages: [],
          processRows: [],
          streaming: false,
          unread: false,
        };
        sessionStore.addSession(newSession);
        if (agentId) sessionAgentCache.set(newSid, agentId);
        sessionStore.setActiveId(newSid);
      }
    }

    // --- M3.2 Backtalk ---
    else if (type === 'backtalk.generated') {
      const btContent = String(payload.content ?? '');
      const btIntensity = Number(payload.intensity ?? 0);
      const btLabel = String(payload.intensity_label ?? 'gentle');
      const btAgentId = String(payload.agent_id ?? '');
      if (btContent) {
        const backtalkMsg: ChatRow = {
          role: 'assistant' as const,
          text: btContent,
          streaming: false,
          agentId: btAgentId,
          agentName: '',
          agentAvatar: '',
          timestamp: Date.now(),
          metadata: {
            backtalk: true,
            intensity: btIntensity,
            intensityLabel: btLabel,
            triggerType: String(payload.trigger_type ?? ''),
          },
        };
        sessionStore.appendChat(sid, backtalkMsg);
      }
    }

    // --- Error ---
    else if (type === 'error') {
      const errorText = String(payload.message ?? payload.error ?? '未知错误');
      sessionStore.appendError(sid, errorText);
    }
  }, []);

  return { handleEvent };
}
