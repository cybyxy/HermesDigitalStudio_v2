/**
 * Pure geometry and text helper functions for the office encounter system.
 * Extracted from UIMainScene_OfficeMixin — zero Phaser / DOM dependencies.
 */
import type { AgentInfo } from '../types';
import type { Direction } from '../types/direction';
import {
  AGENT_BODY_COLLISION_W,
  AGENT_BODY_COLLISION_UP,
  COMPLETE_BUBBLE_LINE1_MAX,
  COMPLETE_BUBBLE_CHAR_MAX,
} from './officeConstants';

// ─── Sorting / Keys ──────────────────────────────────────────────────────

/** Deterministic pair key for ordered agent-id pairs (greet cooldown etc.). */
export function pairKey(a: string, b: string): string {
  return a < b ? `${a}\0${b}` : `${b}\0${a}`;
}

// ─── Labels / Text ──────────────────────────────────────────────────────

/** Human-readable scene label for an agent (displayName or agentId). */
export function agentSceneLabel(agent: AgentInfo): string {
  const n = (agent.displayName || '').trim();
  return n || agent.agentId;
}

/** Truncate a string to maxChars code points, appending ellipsis if needed. */
export function truncateBubbleText(s: string, maxChars: number): string {
  const t = s.replace(/\r/g, '').replace(/\s+/g, ' ').trim();
  if ([...t].length <= maxChars) return t;
  return `${[...t].slice(0, maxChars).join('')}…`;
}

/**
 * Format an agent's complete reply into a 1–2 line bubble snippet.
 * Uses COMPLETE_BUBBLE_LINE1_MAX and COMPLETE_BUBBLE_CHAR_MAX constants.
 */
export function formatCompleteBubbleSnippet(text: string): string {
  const raw = text.replace(/\r/g, '').trim();
  if (!raw) return '推理已完成';
  const cp = [...raw];

  if (cp.length <= COMPLETE_BUBBLE_LINE1_MAX) {
    return cp.join('');
  }
  if (cp.length <= COMPLETE_BUBBLE_CHAR_MAX) {
    return `${cp.slice(0, COMPLETE_BUBBLE_LINE1_MAX).join('')}\n${cp.slice(COMPLETE_BUBBLE_LINE1_MAX).join('')}`;
  }
  return `${cp.slice(0, COMPLETE_BUBBLE_LINE1_MAX).join('')}\n${cp.slice(COMPLETE_BUBBLE_LINE1_MAX, COMPLETE_BUBBLE_CHAR_MAX).join('')}...`;
}

// ─── Direction ──────────────────────────────────────────────────────────

/** Map a Direction enum to a sprite-facing value (left/right/up/down). */
export function spriteFacingFromDirection(d: Direction): 'down' | 'up' | 'left' | 'right' {
  switch (d) {
    case 'up':
    case 'left':
    case 'right':
      return d;
    case 'down':
    case 'idle':
    default:
      return 'down';
  }
}

/** Derive cardinal direction from pixel delta. */
export function dirFromPixelDelta(dx: number, dy: number): 'down' | 'up' | 'left' | 'right' {
  if (Math.abs(dx) >= Math.abs(dy)) {
    return dx > 0 ? 'right' : 'left';
  }
  return dy > 0 ? 'down' : 'up';
}

/** Return the opposite facing direction. */
export function oppositeFacing(d: 'down' | 'up' | 'left' | 'right'): 'down' | 'up' | 'left' | 'right' {
  switch (d) {
    case 'down':  return 'up';
    case 'up':    return 'down';
    case 'left':  return 'right';
    case 'right': return 'left';
  }
}

// ─── Geometry ───────────────────────────────────────────────────────────

/** Axis-aligned body collision rectangle centred under the agent's feet. */
export function agentBodyRectAt(
  footX: number,
  footY: number,
): { left: number; top: number; right: number; bottom: number } {
  const halfW = AGENT_BODY_COLLISION_W / 2;
  return {
    left: footX - halfW,
    right: footX + halfW,
    top: footY - AGENT_BODY_COLLISION_UP,
    bottom: footY,
  };
}

/** True if two axis-aligned rectangles overlap. */
export function bodyRectsOverlap(
  a: { left: number; top: number; right: number; bottom: number },
  b: { left: number; top: number; right: number; bottom: number },
): boolean {
  return a.left < b.right && a.right > b.left && a.top < b.bottom && a.bottom > b.top;
}

/** World-pixel foot centre for a tile coordinate. */
export function tileFootCenter(
  tx: number,
  ty: number,
  tileW: number,
  tileH: number,
): { x: number; y: number } {
  return {
    x: tx * tileW + tileW / 2,
    y: ty * tileH + tileH / 2,
  };
}
