/**
 * Pure handoff / relay parsing utilities.
 * Extracted from UIMainScene_MessagesMixin — zero side effects.
 */
import type { AgentInfo } from '../types';

/** Normalize unicode whitespace / BOM / fullwidth chars before parsing. */
export function normalizeHandoffInput(s: string): string {
  let t = s
    .replace(/\ufeff/g, '')
    .replace(/[\u200b\u200c\u200d\u2060]/g, '')
    .replace(/\uff20/g, '@')
    .replace(/\u202f/g, ' ')
    .replace(/\u00a0/g, ' ');
  t = t.replace(/[\u2000-\u200a\u3000]+/g, ' ');
  try {
    t = t.normalize('NFKC');
  } catch {
    // ignore
  }
  return t.trim();
}

/**
 * Try to parse a single block as a handoff line.
 * Supports `@agent | msg`, `@agent : msg`, `@agent msg`,
 * and `/relay agent | msg` forms.
 */
export function tryParseHandoffBlock(
  block: string,
): { token: string; msg: string; broadcast: boolean } | null {
  const s = normalizeHandoffInput(block);
  let m = s.match(/^\/relay\s+(\S+)\s*\|\s*([\s\S]+)$/i);
  if (!m) m = s.match(/^@([^\s|@\n]+)\s*[|｜]\s*([\s\S]+)$/);
  if (!m) m = s.match(/^@([^\s|@\n]+)\s*[：:]\s*([\s\S]+)$/);
  if (!m) m = s.match(/^@([^\s|@\n]+)\s+([\s\S]+)$/);
  if (!m) return null;
  const token = (m[1] || '').trim();
  const msg = (m[2] || '').trim();
  if (!token || !msg) return null;
  const broadcast = token === '所有人' || token.toLowerCase() === 'all';
  return { token, msg, broadcast };
}

/** Heuristic: does the raw text look like an agent handoff with payload? */
export function looksLikeAgentHandoffWithPayload(raw: string): boolean {
  const t = normalizeHandoffInput(raw);
  if (tryParseHandoffBlock(t) != null) return true;
  if (/^@([^\s|@\n]+)\s*[|｜]\s*\S/m.test(t)) return true;
  if (/^\/relay\s+\S+\s*\|/im.test(t)) return true;
  const lines = t
    .split(/\r?\n/)
    .map((ln) => ln.trim())
    .filter(Boolean);
  const last = lines[lines.length - 1];
  if (!last) return false;
  if (!last.startsWith('@') && !last.toLowerCase().startsWith('/relay')) return false;
  if (/^@([^\s|@\n]+)\s*[|｜]\s*\S/.test(last)) return true;
  if (/^@([^\s|@\n]+)\s*[：:]\s*\S/.test(last)) return true;
  if (/^\/relay\s+\S+\s*\|/i.test(last)) return true;
  return /^@([^\s|@\n]+)\s+\S/.test(last);
}

/**
 * Find an agent by mention handle.
 * Matches by agentId, profile, or displayName (case-insensitive for ASCII).
 */
export function findAgentByMentionHandle(handle: string, agents: AgentInfo[]): AgentInfo | null {
  const h = handle.trim();
  if (!h) return null;
  const lower = h.toLowerCase();
  const ascii = (s: string): boolean => /^[\x00-\x7f]+$/.test(s);
  for (const a of agents) {
    if (a.agentId === h || (a.profile && a.profile === h)) return a;
    if (ascii(a.agentId) && a.agentId.toLowerCase() === lower) return a;
    if (a.profile && ascii(a.profile) && a.profile.toLowerCase() === lower) return a;
    const dn = (a.displayName || '').trim();
    if (dn && dn === h) return a;
    if (dn && ascii(dn) && dn.toLowerCase() === lower) return a;
  }
  return null;
}

/**
 * Parse an outgoing user prompt into a route decision.
 * Returns the target agent ID (or null), the text to send to the API,
 * the display text, and whether it's a broadcast.
 */
export function parseOutgoingPrompt(
  raw: string,
  agents: AgentInfo[],
): { switchTo: string | null; apiText: string; isBroadcast: boolean; displayRaw: string } {
  const trimmed = normalizeHandoffInput(raw);
  let hit = tryParseHandoffBlock(trimmed);
  if (!hit) {
    const lines = trimmed
      .split(/\r?\n/)
      .map((ln) => ln.trim())
      .filter(Boolean);
    for (let i = lines.length - 1; i >= 0; i--) {
      const line = lines[i]!;
      if (!line.startsWith('@') && !line.toLowerCase().startsWith('/relay')) continue;
      hit = tryParseHandoffBlock(line);
      if (hit) break;
    }
  }
  if (hit) {
    if (hit.broadcast) {
      return { switchTo: null, apiText: trimmed, isBroadcast: true, displayRaw: trimmed };
    }
    const agent = findAgentByMentionHandle(hit.token, agents);
    if (agent) {
      return {
        switchTo: agent.agentId,
        apiText: hit.msg,
        isBroadcast: false,
        displayRaw: trimmed,
      };
    }
  }
  const lm = trimmed.match(/^@(\S+)/);
  if (lm) {
    const agent = findAgentByMentionHandle(lm[1]!, agents);
    if (agent) {
      const rest = trimmed.slice(lm[0]!.length).trimStart();
      return { switchTo: agent.agentId, apiText: rest, isBroadcast: false, displayRaw: trimmed };
    }
  }
  return { switchTo: null, apiText: trimmed, isBroadcast: false, displayRaw: trimmed };
}

/**
 * Check if orchestration was rejected (orchestrator sent back a rejection signal).
 */
export function isOrchestrationRejected(payload: Record<string, unknown>): boolean {
  if (payload.rejected === true) return true;
  if (typeof payload.message === 'string' && payload.message.includes('rejected')) return true;
  if (payload.status === 'rejected' || payload.status === 'declined') return true;
  return false;
}
