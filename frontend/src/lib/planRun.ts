import type { ChatRow, SessionState } from '../types';

/** 用户明确要「开始执行」当前规划链（含口语与短确认）。 */
export function userMeansStartPlan(text: string): boolean {
  const t = (text || '').trim();
  if (!t) return false;
  if (
    /开始|启动|开搞|开整|执行|动手|搞起来|上马|行动起来|先做|开干|走起|搞吧|上吧|来(?:吧|呗)|干吧|冲|go\b|start\b|execute\b|proceed\b/i.test(
      t,
    )
  ) {
    return true;
  }
  // 短句确认：「好」「好的」「行」「可以」「ok」等（避免误触过长闲聊）
  if (t.length <= 12 && /^(?:好[吧的呀哟]|行|可以|ok|okay|yes|嗯|成|妥)\s*[,，。.!！…]*$/i.test(t)) {
    return true;
  }
  return false;
}

type AssistantMsg = Extract<ChatRow, { role: 'assistant' }>;

/** 全工作区时间戳最新的一条带结构化规划的助手消息。 */
export function findLatestPlanMessage(
  sessions: SessionState[],
): { sid: string; msg: AssistantMsg; ts: number } | null {
  let best: { sid: string; msg: AssistantMsg; ts: number } | null = null;
  for (const s of sessions) {
    for (const m of s.messages) {
      if (m.role !== 'assistant' || !m.planArtifact) continue;
      const ts = m.timestamp ?? 0;
      if (!best || ts >= best.ts) best = { sid: s.id, msg: m, ts };
    }
  }
  return best;
}

export function planMessageStillExists(sessions: SessionState[], planAnchorTs: number): boolean {
  for (const s of sessions) {
    for (const m of s.messages) {
      if (m.role === 'assistant' && m.timestamp === planAnchorTs && m.planArtifact) return true;
    }
  }
  return false;
}
