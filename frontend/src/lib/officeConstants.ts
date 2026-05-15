/**
 * Office scene constants.
 * Migrated from scenes/UIMainScene_Constants.ts — only symbols used by new code.
 */
import { PERSON_FRAME_H } from '../ui/personSprites';

/** Agent body collision box width (pixels) */
export const AGENT_BODY_COLLISION_W = 48;
/** Agent body collision box upward offset from feet (pixels) */
export const AGENT_BODY_COLLISION_UP = 16;

/** Max characters in first line of complete bubble before truncation */
export const COMPLETE_BUBBLE_LINE1_MAX = 25;
/** Max characters in complete bubble before truncation */
export const COMPLETE_BUBBLE_CHAR_MAX = 47;

/** Milliseconds before an idle agent auto-wanders */
export const AGENT_AUTO_WANDER_AFTER_MS = 2 * 60 * 1000;
/** Pixel distance threshold for agent greeting */
export const AGENT_GREET_DISTANCE_PX = 32;
/** Cooldown between greet events for a pair (ms) */
export const AGENT_GREET_PAIR_COOLDOWN_MS = 10_000;

// Kept from original for INFER_BUBBLE_LOCAL_Y reference (used internally by AgentSprites.ts)
export const INFER_BUBBLE_LOCAL_Y = -PERSON_FRAME_H - 34;
