/**
 * Agent Movement Module — pathfinding, walking, autonomy helpers.
 * Extracted from UIMainScene_OfficeMixin.
 */
import Phaser from 'phaser';
import { useOfficeAgentPoseStore } from '../stores/officeAgentPoseStore';
import { personFrameIndex } from '../ui/personSprites';
import { astar, nearestWalkableTile } from './astar';
import {
  AGENT_BODY_COLLISION_W,
  AGENT_BODY_COLLISION_UP,
  AGENT_AUTO_WANDER_AFTER_MS,
  AGENT_GREET_DISTANCE_PX,
} from '../lib/officeConstants';
import {
  tileToWorld,
  worldToTile,
} from './OfficeMap';
import {
  dirFromPixelDelta,
  agentBodyRectAt,
  bodyRectsOverlap,
} from '../lib/officeEncounterHelpers';

// ─── Obstacle / Walk Grid ────────────────────────────────────────────────

/** Clone the obstacle grid for per-agent pathfinding. */
export function cloneObstacleGrid(grid: boolean[][]): boolean[][] {
  return grid.map((row) => row.slice());
}

/**
 * Build a walk grid for a specific agent by marking tiles occupied
 * by other agents as blocked.
 */
export function buildWalkGrid(
  obstacleGrid: boolean[][],
  exceptAgentId: string,
  tileW: number,
  tileH: number,
  agentSprites: Map<string, Phaser.GameObjects.Container>,
): boolean[][] {
  const g = cloneObstacleGrid(obstacleGrid);
  const rows = g.length;
  const cols = g[0]?.length ?? 0;
  for (let ty = 0; ty < rows; ty++) {
    for (let tx = 0; tx < cols; tx++) {
      if (!g[ty]![tx]) continue;
      const { x, y } = tileToWorld(tx, ty, tileW, tileH);
      const selfR = agentBodyRectAt(x, y);
      let blocked = false;
      for (const [id, cont] of agentSprites) {
        if (id === exceptAgentId) continue;
        const otherR = agentBodyRectAt(cont.x, cont.y);
        if (bodyRectsOverlap(selfR, otherR)) {
          blocked = true;
          break;
        }
      }
      if (blocked) g[ty]![tx] = false;
    }
  }
  return g;
}

// ─── Pathfinding ─────────────────────────────────────────────────────────

/** Snap start and goal tile coords to nearest walkable tiles. */
export function snapPathEndpoints(
  grid: boolean[][],
  sx: number,
  sy: number,
  gx: number,
  gy: number,
): { sx: number; sy: number; gx: number; gy: number } | null {
  const s = nearestWalkableTile(grid, sx, sy);
  const g = nearestWalkableTile(grid, gx, gy);
  if (!s || !g) return null;
  return { sx: s.x, sy: s.y, gx: g.x, gy: g.y };
}

/** Pick a random walkable destination and compute a path to it. */
export function pickRandomWanderPath(
  agentId: string,
  obstacleGrid: boolean[][],
  tileW: number,
  tileH: number,
  agentSprites: Map<string, Phaser.GameObjects.Container>,
): { x: number; y: number }[] | null {
  if (obstacleGrid.length === 0) return null;
  const cont = agentSprites.get(agentId);
  if (!cont) return null;
  const walkGrid = buildWalkGrid(obstacleGrid, agentId, tileW, tileH, agentSprites);
  const rows = walkGrid.length;
  const cols = walkGrid[0]?.length ?? 0;
  if (rows === 0 || cols === 0) return null;
  const { tx: sx, ty: sy } = worldToTile(cont.x, cont.y, tileW, tileH);
  for (let attempt = 0; attempt < 48; attempt++) {
    const gx = Math.floor(Math.random() * cols);
    const gy = Math.floor(Math.random() * rows);
    if (!walkGrid[gy]![gx]) continue;
    const snapped = snapPathEndpoints(walkGrid, sx, sy, gx, gy);
    if (!snapped) continue;
    const path = astar(walkGrid, snapped.sx, snapped.sy, snapped.gx, snapped.gy);
    if (path.length > 1) return path;
  }
  return null;
}

// ─── Agent Walking ───────────────────────────────────────────────────────

export interface WalkContext {
  scene: Phaser.Scene;
  tileW: number;
  tileH: number;
  obstacleGrid: boolean[][];
  agentSprites: Map<string, Phaser.GameObjects.Container>;
  agentFacing: Map<string, 'down' | 'up' | 'left' | 'right'>;
  agentIdleSinceMs: Map<string, number>;
  idleTick: number;
}

/**
 * Run an agent along a tile path using Phaser tweens.
 * On completion, records the idle timestamp and persists the pose.
 */
export function runAgentPath(
  ctx: WalkContext,
  agentId: string,
  path: { x: number; y: number }[],
  onDone?: () => void,
): void {
  const container = ctx.agentSprites.get(agentId);
  if (!container) {
    onDone?.();
    return;
  }
  if (path.length === 0) {
    ctx.agentIdleSinceMs.set(agentId, Date.now());
    onDone?.();
    return;
  }

  ctx.agentIdleSinceMs.delete(agentId);
  ctx.scene.tweens.killTweensOf(container);
  const img = container.list[0] as Phaser.GameObjects.Image;

  const finishWalk = (): void => {
    const d = ctx.agentFacing.get(agentId) ?? 'down';
    img.setFrame(personFrameIndex(d, ctx.idleTick % 3));
    useOfficeAgentPoseStore.getState().setPose(agentId, {
      x: container.x,
      y: container.y,
      facing: d,
    });
    ctx.agentIdleSinceMs.set(agentId, Date.now());
    onDone?.();
  };

  let step = 0;
  const moveNext = (): void => {
    if (step >= path.length) {
      finishWalk();
      return;
    }
    const { x: tx, y: ty } = path[step]!;
    const tpx = tx * ctx.tileW + ctx.tileW / 2;
    const tpy = ty * ctx.tileH + ctx.tileH / 2;
    const staticRow = ctx.obstacleGrid[ty];
    if (!staticRow?.[tx]) {
      finishWalk();
      return;
    }

    // Check other agent collision
    const footRect = agentBodyRectAt(tpx, tpy);
    for (const [id, cont] of ctx.agentSprites) {
      if (id === agentId) continue;
      if (bodyRectsOverlap(footRect, agentBodyRectAt(cont.x, cont.y))) {
        finishWalk();
        return;
      }
    }

    const dx = tpx - container.x;
    const dy = tpy - container.y;
    const dist = Math.hypot(dx, dy);

    if (dist < 0.5) {
      step++;
      moveNext();
      return;
    }

    const facing = dirFromPixelDelta(dx, dy);
    ctx.agentFacing.set(agentId, facing);

    ctx.scene.tweens.add({
      targets: container,
      x: tpx,
      y: tpy,
      duration: Math.max(160, Math.min(600, dist * 4)),
      ease: 'Linear',
      onUpdate: (tween: Phaser.Tweens.Tween) => {
        const col = Math.min(2, Math.floor(tween.progress * 3));
        img.setFrame(personFrameIndex(facing, col));
      },
      onComplete: () => {
        step++;
        moveNext();
      },
    });
  };
  moveNext();
}

// ─── Autonomy ────────────────────────────────────────────────────────────

/**
 * Self-driving agent autonomy: wander when idle, detect proximity for
 * potential greetings.
 * Returns a set of agent pairs that crossed into greet distance.
 */
export function runAutonomyTick(
  ctx: WalkContext,
  frozenSet: Set<string>,
  pairLastFrameDistance: Map<string, number>,
  greetPairLastMs: Map<string, number>,
): { crossedPairs: Array<[string, string]> } {
  const now = Date.now();
  const crossedPairs: Array<[string, string]> = [];

  // Wander for idle agents
  for (const [agentId, cont] of ctx.agentSprites) {
    if (frozenSet.has(agentId)) continue;
    if (ctx.scene.tweens.isTweening(cont)) {
      ctx.agentIdleSinceMs.delete(agentId);
      continue;
    }
    if (!ctx.agentIdleSinceMs.has(agentId)) {
      ctx.agentIdleSinceMs.set(agentId, now);
    }
    const since = ctx.agentIdleSinceMs.get(agentId)!;
    if (now - since < AGENT_AUTO_WANDER_AFTER_MS) continue;
    const path = pickRandomWanderPath(
      agentId,
      ctx.obstacleGrid,
      ctx.tileW,
      ctx.tileH,
      ctx.agentSprites,
    );
    if (path?.length) {
      runAgentPath(ctx, agentId, path);
    }
  }

  // Detect proximity crossings
  for (const [moverId, moverCont] of ctx.agentSprites) {
    if (frozenSet.has(moverId)) continue;
    if (!ctx.scene.tweens.isTweening(moverCont)) continue;
    for (const [otherId, otherCont] of ctx.agentSprites) {
      if (otherId === moverId) continue;
      const d = Math.hypot(moverCont.x - otherCont.x, moverCont.y - otherCont.y);
      if (d >= AGENT_GREET_DISTANCE_PX) continue;
      const pk = moverId < otherId ? `${moverId}\0${otherId}` : `${otherId}\0${moverId}`;
      const prevD = pairLastFrameDistance.get(pk);
      const crossedIn =
        prevD !== undefined &&
        prevD >= AGENT_GREET_DISTANCE_PX &&
        d < AGENT_GREET_DISTANCE_PX;
      if (!crossedIn) continue;
      const lastGreet = greetPairLastMs.get(pk) ?? 0;
      if (now - lastGreet < 10_000) continue;
      crossedPairs.push([moverId, otherId]);
    }
  }

  // Update pair distances
  const sprites = [...ctx.agentSprites.entries()];
  for (let i = 0; i < sprites.length; i++) {
    const [idA, contA] = sprites[i]!;
    for (let j = i + 1; j < sprites.length; j++) {
      const [idB, contB] = sprites[j]!;
      const pk = idA < idB ? `${idA}\0${idB}` : `${idB}\0${idA}`;
      pairLastFrameDistance.set(pk, Math.hypot(contA.x - contB.x, contA.y - contB.y));
    }
  }

  return { crossedPairs };
}

// ─── Facing / Encounter Movement ─────────────────────────────────────────

import { oppositeFacing } from '../lib/officeEncounterHelpers';

/** Make two agents face each other.  Returns the facing directions. */
export function applyFaceToFace(
  aId: string,
  bId: string,
  tileW: number,
  tileH: number,
  agentSprites: Map<string, Phaser.GameObjects.Container>,
  agentFacing: Map<string, 'down' | 'up' | 'left' | 'right'>,
  idleTick: number,
): void {
  const ca = agentSprites.get(aId);
  const cb = agentSprites.get(bId);
  if (!ca || !cb) return;
  const dx = cb.x - ca.x;
  const dy = cb.y - ca.y;
  const faceA = dirFromPixelDelta(dx, dy);
  const faceB = oppositeFacing(faceA);
  agentFacing.set(aId, faceA);
  agentFacing.set(bId, faceB);
  for (const [id, cont] of [
    [aId, ca],
    [bId, cb],
  ] as const) {
    const img = cont.list[0] as Phaser.GameObjects.Image;
    const d = agentFacing.get(id) ?? 'down';
    img.setFrame(personFrameIndex(d, idleTick % 3));
  }
  // Persist poses
  for (const [id] of [
    [aId, ca],
    [bId, cb],
  ] as const) {
    const cont = agentSprites.get(id);
    if (cont) {
      useOfficeAgentPoseStore.getState().setPose(id, {
        x: cont.x,
        y: cont.y,
        facing: agentFacing.get(id) ?? 'down',
      });
    }
  }
}

/** Halt an agent's movement (stop tweens, set idle frame, persist pose). */
export function haltAgentMovement(
  scene: Phaser.Scene,
  agentId: string,
  agentSprites: Map<string, Phaser.GameObjects.Container>,
  agentFacing: Map<string, 'down' | 'up' | 'left' | 'right'>,
  agentIdleSinceMs: Map<string, number>,
  idleTick: number,
): void {
  const cont = agentSprites.get(agentId);
  if (!cont) return;
  scene.tweens.killTweensOf(cont);
  const d = agentFacing.get(agentId) ?? 'down';
  const img = cont.list[0] as Phaser.GameObjects.Image;
  img.setFrame(personFrameIndex(d, idleTick % 3));
  useOfficeAgentPoseStore.getState().setPose(agentId, {
    x: cont.x,
    y: cont.y,
    facing: d,
  });
  agentIdleSinceMs.delete(agentId);
}
