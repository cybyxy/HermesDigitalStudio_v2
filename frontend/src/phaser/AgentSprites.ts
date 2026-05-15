/**
 * Agent Sprite Module — creation, removal, appearance, and infer bubbles.
 * Extracted from UIMainScene_OfficeMixin.
 */
import Phaser from 'phaser';
import { useAgentStore } from '../stores/agentStore';
import { useOfficeAgentPoseStore } from '../stores/officeAgentPoseStore';
import {
  AGENT_BODY_COLLISION_W,
  AGENT_BODY_COLLISION_UP,
} from '../lib/officeConstants';
import {
  PERSON_FRAME_W,
  PERSON_FRAME_H,
  getPersonSheetUrl,
  personTextureKey,
  personFrameIndex,
} from '../ui/personSprites';
import type { AgentInfo } from '../types';
import type { Direction } from '../types/direction';
import { spriteFacingFromDirection, agentSceneLabel } from '../lib/officeEncounterHelpers';

const INFER_BUBBLE_LOCAL_Y = -PERSON_FRAME_H - 34;

// ─── Agent Sprite Cache ──────────────────────────────────────────────────

/** Ensure person sprite sheet texture is loaded into the Phaser cache. */
async function ensurePersonSheet(
  scene: Phaser.Scene,
  avatar: string,
): Promise<boolean> {
  const texKey = personTextureKey(avatar);
  if (scene.textures.exists(texKey)) return true;

  await new Promise<void>((resolve) => {
    const img = new Image();
    img.onload = () => {
      if (scene.textures.exists(texKey)) {
        resolve();
        return;
      }
      scene.textures.addSpriteSheet(texKey, img, {
        frameWidth: PERSON_FRAME_W,
        frameHeight: PERSON_FRAME_H,
      });
      resolve();
    };
    img.onerror = () => resolve();
    img.src = getPersonSheetUrl(avatar);
  });

  return scene.textures.exists(texKey);
}

// ─── Agent Sprite Container ─────────────────────────────────────────────

export interface AgentSpriteEntry {
  container: Phaser.GameObjects.Container;
  /** Index into agentLayer — this persists across the lifetime of the sprite. */
}

/**
 * Create and add an agent sprite to the scene.
 * Returns the container or null if the sheet failed to load.
 */
export async function createAgentSprite(
  scene: Phaser.Scene,
  agentLayer: Phaser.GameObjects.Container,
  agentId: string,
  avatar: string,
  px: number,
  py: number,
  initialFacing: Direction,
  displayLabel?: string,
): Promise<Phaser.GameObjects.Container | null> {
  const ok = await ensurePersonSheet(scene, avatar);
  if (!ok) return null;

  const texKey = personTextureKey(avatar);

  const state = useAgentStore.getState();
  const agentRow = state.agents.find((a) => a.agentId === agentId);
  const label =
    (displayLabel && displayLabel.trim()) ||
    (agentRow ? agentSceneLabel(agentRow) : agentId);

  const nameText = scene.add.text(0, -PERSON_FRAME_H - 2, label, {
    fontSize: '11px',
    color: '#ffffff',
    backgroundColor: '#5b8cffaa',
    padding: { x: 4, y: 1 },
  });
  nameText.setOrigin(0.5, 1);
  nameText.setDepth(0.83);

  const stateBubble = scene.add.graphics();
  stateBubble.setDepth(0.9);
  stateBubble.setVisible(false);
  const stateText = scene.add.text(0, INFER_BUBBLE_LOCAL_Y, '', {
    fontSize: '11px',
    color: '#ffffff',
    fontFamily: 'system-ui, Segoe UI, sans-serif',
  });
  stateText.setOrigin(0.5, 0.5);
  stateText.setDepth(0.91);
  stateText.setVisible(false);

  const facing = spriteFacingFromDirection(initialFacing);
  const img = scene.add.image(0, 0, texKey, personFrameIndex(facing, 0));
  img.setOrigin(0.5, 1);
  img.setInteractive({ useHandCursor: true });

  const container = scene.add.container(px, py, [img, nameText, stateBubble, stateText]);
  agentLayer.add(container);
  container.setDepth(0.5);

  return container;
}

/** Destroy agent sprite and clean up associated data. */
export function removeAgentSprite(
  container: Phaser.GameObjects.Container,
  agentId: string,
): void {
  useOfficeAgentPoseStore.getState().removePose(agentId);
  useAgentStore.getState().clearAgentSceneInfer(agentId);
  container.destroy();
}

// ─── Sprite Appearance ──────────────────────────────────────────────────

/** Refresh an agent sprite's display name and avatar texture. */
export async function refreshAgentAppearance(
  scene: Phaser.Scene,
  container: Phaser.GameObjects.Container,
  agent: AgentInfo,
  currentFacing: Direction,
): Promise<void> {
  if (container.list.length < 2) return;

  const nameText = container.list[1] as Phaser.GameObjects.Text;
  nameText.setText(agentSceneLabel(agent));

  const img = container.list[0] as Phaser.GameObjects.Image;
  const avatar = agent.avatar ?? 'badboy';
  const texKey = personTextureKey(avatar);
  if (img.texture.key === texKey) return;

  const ok = await ensurePersonSheet(scene, avatar);
  if (!ok) return;

  const dir = spriteFacingFromDirection(currentFacing);
  img.setTexture(texKey, personFrameIndex(dir, 0));
}

// ─── Infer Bubble Helpers ───────────────────────────────────────────────

/** Get or create infer bubble graphics+text objects on a container. */
export function ensureInferBubble(
  scene: Phaser.Scene,
  container: Phaser.GameObjects.Container,
): { bubble: Phaser.GameObjects.Graphics; label: Phaser.GameObjects.Text } {
  if (container.list.length >= 4) {
    return {
      bubble: container.list[2] as Phaser.GameObjects.Graphics,
      label: container.list[3] as Phaser.GameObjects.Text,
    };
  }
  const bubble = scene.add.graphics();
  bubble.setDepth(0.9);
  bubble.setVisible(false);
  const label = scene.add.text(0, INFER_BUBBLE_LOCAL_Y, '', {
    fontSize: '11px',
    color: '#ffffff',
    fontFamily: 'system-ui, Segoe UI, sans-serif',
  });
  label.setOrigin(0.5, 0.5);
  label.setDepth(0.91);
  label.setVisible(false);
  container.add(bubble);
  container.add(label);
  return { bubble, label };
}

/** High-level data for syncing an infer bubble to a sprite. */
export interface InferBubbleState {
  phase: 'thinking' | 'tool' | 'done' | 'social' | 'idle' | 'small_thought' | undefined;
  thinkingSnippet?: string;
  toolSnippet?: string;
  doneSnippet?: string;
  socialSnippet?: string;
  smallThoughtSnippet?: string;
  doneExpiresAt?: number;
  socialExpiresAt?: number;
  smallThoughtExpiresAt?: number;
}

/** Mood colours mapped to bubble and text colours. */
const MOOD_STYLES: Record<string, { line: number; fill: number; text: string }> = {
  thinking: { line: 0x6c8bf5, fill: 0x1a2332, text: '#a8b8ff' },
  tool: { line: 0x4fc3f7, fill: 0x1a2832, text: '#81d4fa' },
  done: { line: 0xe8c96b, fill: 0x2a2818, text: '#e8c96b' },
  social: { line: 0x86efac, fill: 0x183228, text: '#86efac' },
  small_thought: { line: 0xf0c0a0, fill: 0x2a2018, text: '#f0c0a0' },
};

/**
 * Get animated ellipsis string based on time.
 * Cycles through " " → "." → ".." → "..." every 800ms.
 */
function animatedEllipsis(now: number): string {
  const t = Math.floor(now / 400) % 4;
  return t === 0 ? ' ' : '.'.repeat(t);
}

/**
 * Truncate text to fit within maxWidth pixels, appending "…" if truncated.
 */
function truncateText(
  text: Phaser.GameObjects.Text,
  str: string,
  maxWidth: number,
): string {
  if (text.width <= maxWidth) return str;
  // Binary search for the right truncation point
  let lo = 1;
  let hi = str.length;
  while (lo < hi) {
    const mid = Math.ceil((lo + hi) / 2);
    text.setText(str.slice(0, mid) + '…');
    if (text.width > maxWidth) {
      hi = mid - 1;
    } else {
      lo = mid;
    }
  }
  return str.slice(0, Math.max(1, lo - 1)) + '…';
}

/**
 * Draw an infer bubble on a sprite container.
 * Assumes the container was created via createAgentSprite (has bubble at index 2,
 * label at index 3).
 *
 * Enhanced with:
 * - Animated ellipsis for thinking/tool active states
 * - State-specific prefix text for clarity
 * - Multi-line text with word wrap
 * - Long text truncation
 * - Pulse animation effect (border alpha oscillates for active states)
 */
export function drawInferBubble(
  container: Phaser.GameObjects.Container,
  state: InferBubbleState,
  now: number,
): void {
  const bubble = container.list[2] as Phaser.GameObjects.Graphics | undefined;
  const label = container.list[3] as Phaser.GameObjects.Text | undefined;
  if (!bubble || !label) return;

  const isExpired =
    (state.phase === 'done' && now >= (state.doneExpiresAt ?? 0)) ||
    (state.phase === 'social' && now >= (state.socialExpiresAt ?? 0));

  if (!state.phase || state.phase === 'idle' || isExpired) {
    bubble.setVisible(false);
    label.setVisible(false);
    return;
  }

  let mood: 'thinking' | 'tool' | 'done' | 'social' | 'small_thought' | 'normal' = 'normal';
  if (state.phase === 'tool') mood = 'tool';
  else if (state.phase === 'thinking') mood = 'thinking';
  else if (state.phase === 'done' && now < (state.doneExpiresAt ?? 0)) mood = 'done';
  else if (state.phase === 'social' && now < (state.socialExpiresAt ?? 0)) mood = 'social';
  else if (state.phase === 'small_thought' && now < (state.smallThoughtExpiresAt ?? 0)) mood = 'small_thought';

  if (mood === 'normal') {
    bubble.setVisible(false);
    label.setVisible(false);
    return;
  }

  // Build state label with prefix and animated ellipsis
  const dot = animatedEllipsis(now);
  let stateLabel: string;

  if (mood === 'thinking') {
    const base = state.thinkingSnippet || '思考中';
    stateLabel = `思考 ${base}${dot}`;
  } else if (mood === 'tool') {
    const base = state.toolSnippet ? `${state.toolSnippet}` : '使用工具';
    stateLabel = `工具 ${base}${dot}`;
  } else if (mood === 'social') {
    stateLabel = state.socialSnippet || '你好！';
  } else if (mood === 'small_thought') {
    stateLabel = state.smallThoughtSnippet || '...';
  } else {
    const doneText = state.doneSnippet || '回答完成';
    // 超过 50 字则截断，提示点击弹窗查看详情
    stateLabel = doneText.length > 50
      ? doneText.slice(0, 50) + '...'
      : doneText;
  }

  // Truncate to fit
  const MAX_BUBBLE_WIDTH = 200;
  label.setText(stateLabel);
  if (label.width > MAX_BUBBLE_WIDTH) {
    const truncated = truncateText(label, stateLabel, MAX_BUBBLE_WIDTH);
    label.setText(truncated);
  }

  const colors = MOOD_STYLES[mood] ?? { line: 0xffffff, fill: 0x000000, text: '#ffffff' };
  label.setStyle({ color: colors.text, fontSize: '11px', fontFamily: 'system-ui, Segoe UI, sans-serif' });
  // Enable word wrap for multi-line support
  label.setWordWrapWidth(MAX_BUBBLE_WIDTH - 10);

  // Pulse alpha for active states (thinking/tool)
  const isActive = mood === 'thinking' || mood === 'tool';
  const pulseAlpha = isActive
    ? 0.5 + 0.3 * Math.sin(now * 0.004)
    : 0.92;

  // Measure actual rendered text bounds (supports multi-line)
  const textW = Math.min(label.width + 12, MAX_BUBBLE_WIDTH);
  const textH = Math.max(18, label.height);
  const pad = 5;
  const bubbleW = textW + pad * 2;
  const bubbleH = textH + pad * 2;

  const yPos = INFER_BUBBLE_LOCAL_Y;

  bubble.clear();
  // Background
  bubble.fillStyle(colors.fill, 0.85);
  bubble.fillRoundedRect(-bubbleW / 2, yPos - bubbleH / 2, bubbleW, bubbleH, 6);
  // Border with pulse alpha
  bubble.lineStyle(1.5, colors.line, pulseAlpha);
  bubble.strokeRoundedRect(-bubbleW / 2, yPos - bubbleH / 2, bubbleW, bubbleH, 6);

  bubble.setVisible(true);
  label.setPosition(0, yPos);
  label.setVisible(true);
}

/**
 * PAD 情绪 → 粒子效果映射。
 *
 * 根据 Valence（愉悦度）、Arousal（唤醒度）、Dominance（支配度）
 * 返回适用的粒子配置名称，由调用方在游戏中应用。
 */
export function padToMoodParticleConfig(
  valence: number,
  arousal: number,
  dominance: number,
): {
  mood: string;
  particleColor: number;
  count: number;
  speed: number;
} {
  if (dominance > 0.3) {
    return { mood: 'confident', particleColor: 0x4caf50, count: 12, speed: 60 };
  }
  if (dominance < -0.3) {
    return { mood: 'submissive', particleColor: 0x9c27b0, count: 8, speed: 30 };
  }
  if (valence > 0.3 && arousal > 0.3) {
    return { mood: 'happy', particleColor: 0xffd700, count: 16, speed: 80 };
  }
  if (valence > 0.3 && arousal < -0.3) {
    return { mood: 'calm', particleColor: 0x64b5f6, count: 10, speed: 25 };
  }
  if (valence < -0.3 && arousal > 0.3) {
    return { mood: 'frustrated', particleColor: 0xe53935, count: 14, speed: 90 };
  }
  if (valence < -0.3 && arousal < -0.3) {
    return { mood: 'anxious', particleColor: 0x9e9e9e, count: 8, speed: 40 };
  }
  return { mood: 'neutral', particleColor: 0xffffff, count: 6, speed: 40 };
}

/**
 * 为 Agent 精灵容器添加/更新情绪粒子发射器。
 *
 * 调用方需要在主循环中传入情绪数据（valence/arousal/dominance），
 * 该函数会创建或更新 Phaser 粒子发射器。
 */
export function setMoodParticles(
  scene: Phaser.Scene,
  container: Phaser.GameObjects.Container,
  valence: number,
  arousal: number,
  dominance: number,
  enabled: boolean = true,
): void {
  // 查找或创建粒子纹理
  const particleKey = 'mood_particle';
  if (!scene.textures.exists(particleKey)) {
    const gfx = scene.add.graphics();
    gfx.fillStyle(0xffffff, 1);
    gfx.fillCircle(4, 4, 4);
    gfx.generateTexture(particleKey, 8, 8);
    gfx.destroy();
  }

  // 获取配置
  const config = padToMoodParticleConfig(valence, arousal, dominance);

  // 移除旧粒子发射器（如果存在于 container 中）
  const existing = container.getData('moodParticleEmitter') as Phaser.GameObjects.Particles.ParticleEmitter | undefined;
  if (existing) {
    existing.stop();
    existing.destroy();
    container.setData('moodParticleEmitter', undefined);
  }

  if (!enabled || config.mood === 'neutral') return;

  // 创建新发射器
  const emitter = scene.add.particles(0, 0, particleKey, {
    tint: config.particleColor,
    speed: { min: config.speed * 0.5, max: config.speed },
    scale: { start: 0.6, end: 0 },
    alpha: { start: 0.7, end: 0 },
    lifespan: 1200,
    frequency: 400,
    quantity: 2,
    blendMode: 'ADD',
    follow: container,
    followOffset: { x: 0, y: -20 },
  });

  container.setData('moodParticleEmitter', emitter);
}
