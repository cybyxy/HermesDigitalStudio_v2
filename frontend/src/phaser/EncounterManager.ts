/**
 * Office Encounter Module — Phaser-side encounter state management.
 * Extracted from UIMainScene_OfficeMixin encounter system.
 *
 * This module handles the Phaser-facing side of office encounters:
 * freezing/unfreezing agents, tracking pending replies, and the delegation
 * approach animation. The orchestration (greeting prompts, SSE responses)
 * belongs in React hooks (Phase 5).
 */
import { useSessionStore } from '../stores/sessionStore';
import { useAgentStore } from '../stores/agentStore';
import { astar } from './astar';
import {
  worldToTile,
} from './OfficeMap';
import {
  buildWalkGrid,
  snapPathEndpoints,
  applyFaceToFace,
  haltAgentMovement,
  runAgentPath,
  type WalkContext,
} from './AgentMovement';
import { agentSceneLabel } from '../lib/officeEncounterHelpers';

// ─── Pending Reply State ─────────────────────────────────────────────────

export interface PendingOfficeReply {
  walkerPromptSent: string;
  peerSid: string;
  peerId: string;
  walkerId: string;
  walkerLabel: string;
  phase: 'await_walker_assistant' | 'await_peer_assistant';
  peerPromptSent?: string;
}

// ─── Encounter Manager ───────────────────────────────────────────────────

export class EncounterManager {
  readonly frozen: Set<string> = new Set();
  readonly pendingReplies: Map<string, PendingOfficeReply> = new Map();
  readonly greetPairLastMs: Map<string, number> = new Map();
  readonly encounterEndMs: Map<string, number> = new Map();

  private ctx: WalkContext;

  constructor(ctx: WalkContext) {
    this.ctx = ctx;
  }

  /** Freeze an agent pair for encounter. Returns true if both were frozen. */
  freeze(walkerId: string, peerId: string): boolean {
    this.frozen.add(walkerId);
    this.frozen.add(peerId);
    return true;
  }

  /** Unfreeze an agent pair after encounter ends. */
  unfreeze(
    walkerId: string,
    peerId: string,
    resumeWalker: boolean,
  ): void {
    this.frozen.delete(walkerId);
    this.frozen.delete(peerId);

    const now = Date.now();
    const pk = walkerId < peerId ? `${walkerId}\0${peerId}` : `${peerId}\0${walkerId}`;
    this.encounterEndMs.set(pk, now);

    if (resumeWalker) {
      // Resume walker will be handled by autonomy
      this.ctx.agentIdleSinceMs.set(walkerId, now);
    }
    this.ctx.agentIdleSinceMs.set(peerId, now);
  }

  /** Apply face-to-face positioning for two agents. */
  faceToFace(walkerId: string, peerId: string): void {
    applyFaceToFace(
      walkerId,
      peerId,
      this.ctx.tileW,
      this.ctx.tileH,
      this.ctx.agentSprites,
      this.ctx.agentFacing,
      this.ctx.idleTick,
    );
  }

  /** Halt both agents' movement. */
  haltBoth(walkerId: string, peerId: string): void {
    haltAgentMovement(
      this.ctx.scene,
      walkerId,
      this.ctx.agentSprites,
      this.ctx.agentFacing,
      this.ctx.agentIdleSinceMs,
      this.ctx.idleTick,
    );
    haltAgentMovement(
      this.ctx.scene,
      peerId,
      this.ctx.agentSprites,
      this.ctx.agentFacing,
      this.ctx.agentIdleSinceMs,
      this.ctx.idleTick,
    );
  }

  /** Check if an agent's session is busy (streaming). */
  isSessionBusy(agentId: string): boolean {
    const st = useSessionStore.getState();
    const sid = st.sessions.find((s) => s.agentId === agentId)?.id?.trim();
    if (!sid) return true;
    const s = st.sessions.find((x) => x.id === sid);
    return !!(s?.streaming);
  }

  /** Check if agent's infer is in thinking/tool phase. */
  isInferBusy(agentId: string): boolean {
    const st = useAgentStore.getState().agentSceneInfer[agentId];
    const ph = st?.phase;
    return ph === 'thinking' || ph === 'tool';
  }

  /** Get or compute a greeting prompt for proximity encounter. */
  getGreetPrompt(
    walkerId: string,
    peerId: string,
  ): { walkerSid: string; peerSid: string; walkerLabel: string; prompt: string } | null {
    const agents = useAgentStore.getState().agents;
    const sessions = useSessionStore.getState().sessions;
    const walker = agents.find((a) => a.agentId === walkerId);
    const peer = agents.find((a) => a.agentId === peerId);
    if (!walker || !peer) return null;
    const peerLabel = agentSceneLabel(peer);
    const walkerLabel = agentSceneLabel(walker);
    const walkerSid = sessions.find((s) => s.agentId === walkerId)?.id?.trim();
    const peerSid = sessions.find((s) => s.agentId === peerId)?.id?.trim();
    if (!walkerSid || !peerSid) return null;

    const prompt =
      `【办公室偶遇】你正在 Hermes Digital Studio 办公室场景里**走过**同事「${peerLabel}」身旁（彼此距离很近）。` +
      '请你**主动向对方打一声招呼**。用**不超过 24 个字**、符合你人设的口头问候；只输出问候正文，不要前后说明、不要引号、不要换行、不要 `@` 转发同事。';

    return { walkerSid, peerSid, walkerLabel, prompt };
  }

  /** Get peer reply prompt after walker completes their greeting. */
  getPeerReplyPrompt(
    walkerLabel: string,
    walkerResponse: string,
    peerSid: string,
  ): string {
    const said = walkerResponse.trim() || '嗨～';
    return (
      `【办公室偶遇】同事「${walkerLabel}」路过你身边，主动对你说：「${said}」` +
      '请用**不超过 24 个字**口头回复一句；只输出回复正文，不要前后说明、不要引号、不要换行、不要 `@` 转交同事。'
    );
  }

  /** Play the delegation approach animation (walker walks to near peer). */
  async playDelegationApproach(
    fromAgentId: string,
    toAgentId: string,
  ): Promise<void> {
    if (this.ctx.obstacleGrid.length === 0) return;
    const fromCont = this.ctx.agentSprites.get(fromAgentId);
    const toCont = this.ctx.agentSprites.get(toAgentId);
    if (!fromCont || !toCont) return;

    const walkGrid = buildWalkGrid(
      this.ctx.obstacleGrid,
      fromAgentId,
      this.ctx.tileW,
      this.ctx.tileH,
      this.ctx.agentSprites,
    );
    const { tx: ix, ty: iy } = worldToTile(fromCont.x, fromCont.y, this.ctx.tileW, this.ctx.tileH);
    const { tx: px, ty: py } = worldToTile(toCont.x, toCont.y, this.ctx.tileW, this.ctx.tileH);
    const rows = walkGrid.length;
    const cols = walkGrid[0]?.length ?? 0;
    const dirs = [[0, -1], [1, 0], [0, 1], [-1, 0]] as const;
    const candidates: { x: number; y: number }[] = [];
    for (const [dx, dy] of dirs) {
      const nx = px + dx;
      const ny = py + dy;
      if (ny < 0 || ny >= rows || nx < 0 || nx >= cols) continue;
      if (!walkGrid[ny]![nx]!) continue;
      candidates.push({ x: nx, y: ny });
    }
    if (candidates.length === 0) {
      this.faceToFace(fromAgentId, toAgentId);
      return;
    }

    let bestPath: { x: number; y: number }[] | null = null;
    for (const c of candidates) {
      const snapped = snapPathEndpoints(walkGrid, ix, iy, c.x, c.y);
      if (!snapped) continue;
      const path = astar(walkGrid, snapped.sx, snapped.sy, snapped.gx, snapped.gy);
      if (!path.length) continue;
      if (!bestPath || path.length < bestPath.length) bestPath = path;
    }
    if (!bestPath?.length) {
      this.faceToFace(fromAgentId, toAgentId);
      return;
    }

    await new Promise<void>((resolve) => {
      runAgentPath(this.ctx, fromAgentId, bestPath!, () => {
        this.faceToFace(fromAgentId, toAgentId);
        resolve();
      });
    });
  }
}
