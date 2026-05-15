/**
 * OfficeScene — lightweight Phaser scene for the Hermes Digital Studio office.
 *
 * This scene replaces the heavy UIMainScene + 6 mixin classes. It handles ONLY
 * the 2D office canvas (map, agent sprites, pathfinding, autonomy, encounters).
 * All DOM/UI elements are rendered by React components (Phase 3/4/5).
 *
 * Communication with React: bidirectional via Zustand domain stores.
 *   React → Phaser: store subscriptions trigger scene methods
 *   Phaser → React: store writes (poses, infer states, selection)
 */
import Phaser from 'phaser';
import { useAppStore } from '../stores/appStore';
import { useAgentStore } from '../stores/agentStore';
import { useSessionStore } from '../stores/sessionStore';
import { useUiStore } from '../stores/uiStore';
import { useOfficeAgentPoseStore } from '../stores/officeAgentPoseStore';
import { apiFetch } from '../api/client';
import { personFrameIndex } from '../ui/personSprites';
import {
  loadOfficeMap,
  releaseOfficeMap,
  clampAgentPixelPos,
  worldToTile,
  type MapState,
} from './OfficeMap';
import {
  createAgentSprite,
  removeAgentSprite,
  refreshAgentAppearance,
  drawInferBubble,
} from './AgentSprites';
import {
  buildWalkGrid,
  pickRandomWanderPath,
  runAgentPath,
  runAutonomyTick,
  haltAgentMovement,
  type WalkContext,
} from './AgentMovement';
import { EncounterManager } from './EncounterManager';
import { astar, nearestWalkableTile } from './astar';
import { spriteFacingFromDirection, agentSceneLabel } from '../lib/officeEncounterHelpers';
import type { AgentInfo } from '../types';
import type { Direction } from '../types/direction';
import type { OfficeSceneSpawn } from './officeTiledMap';
import * as api from '../api';

// ─── Boot Scene ──────────────────────────────────────────────────────────

/** Minimal boot scene that just transitions to OfficeScene. */
export class BootScene extends Phaser.Scene {
  constructor() {
    super({ key: 'Boot' });
  }

  preload(): void {
    // No preload needed — map assets loaded by OfficeScene
  }

  create(): void {
    this.scene.start('Office');
  }
}

// ─── Office Scene ────────────────────────────────────────────────────────

export class OfficeScene extends Phaser.Scene {
  // Map state
  mapState: MapState | null = null;
  agentLayer!: Phaser.GameObjects.Container;

  // Agent state
  agentSprites: Map<string, Phaser.GameObjects.Container> = new Map();
  agentFacing: Map<string, 'down' | 'up' | 'left' | 'right'> = new Map();
  agentIdleSinceMs: Map<string, number> = new Map();
  pairLastFrameDistance: Map<string, number> = new Map();
  selectedAgentId: string | null = null;

  // Animation
  idleTick = 0;
  idleAnimEvent?: Phaser.Time.TimerEvent;
  inferBubbleTimer?: Phaser.Time.TimerEvent;

  // Encounter
  encounter!: EncounterManager;

  // Pose flush
  poseFlushTimer?: ReturnType<typeof setInterval>;

  // Store unsubscribe handles
  private _unsubs: (() => void)[] = [];
  private _ctxMenuHandler?: (e: MouseEvent) => void;

  constructor() {
    super({ key: 'Office' });
  }

  // ─── Scene Lifecycle ─────────────────────────────────────────────────

  create(): void {
    void this._init();
  }

  async _init(): Promise<void> {
    // Load the office map
    const result = await loadOfficeMap(this, (msg) => {
      // React overlay can show loading status
    });
    if (!result) {
      console.error('[OfficeScene] Failed to load office map');
      return;
    }

    this.mapState = result.mapState;
    this.agentLayer = result.agentLayer;

    // Layout map to fit viewport
    this._layoutMap();

    // Load agent sprites
    await this._loadAgentSprites(this.mapState.spawns);

    // Start idle animation loop
    this._startIdleAnimation();

    // Start infer bubble sync
    this._startInferBubbleSync();

    // Init encounter manager
    this.encounter = new EncounterManager(this._makeWalkCtx());

    // Autonomy (POST_UPDATE)
    this.events.on(Phaser.Scenes.Events.POST_UPDATE, this._onPostUpdate, this);
    this.events.on(Phaser.Scenes.Events.POST_UPDATE, this._sortAgentsByY, this);

    // Click interactions
    this.input.on(Phaser.Input.Events.POINTER_DOWN, this._onPointerDown, this);

    // Prevent browser right-click context menu on the Phaser canvas
    this._ctxMenuHandler = (e: MouseEvent) => e.preventDefault();
    this.game.canvas.addEventListener('contextmenu', this._ctxMenuHandler);

    // Subscribe to stores
    this._subscribeStores(this.mapState.spawns);

    // Start pose flush timer
    this.poseFlushTimer = setInterval(() => void this._flushPoses(), 5000);

    // Mark app initialized
    useAppStore.getState().setInitialized(true);

    // Re-layout map on canvas resize
    this.scale.on('resize', this._onResize, this);
  }

  shutdown(): void {
    for (const unsub of this._unsubs) unsub();
    this._unsubs = [];
    this.scale.off('resize', this._onResize);
    if (this._ctxMenuHandler) {
      this.game.canvas.removeEventListener('contextmenu', this._ctxMenuHandler);
    }
    if (this.poseFlushTimer) clearInterval(this.poseFlushTimer);
    this.idleAnimEvent?.destroy();
    this.inferBubbleTimer?.destroy();
    if (this.mapState) {
      releaseOfficeMap(this, this.mapState.officeTextureKeys);
    }
  }

  // ─── Map Layout ──────────────────────────────────────────────────────

  /** 1:1 像素渲染，地图中心和 agent 层均与 Phaser 画布中心对齐。 */
  private _layoutMap(): void {
    const ms = this.mapState!;
    const w = this.scale.width;
    const h = this.scale.height;
    const ox = (w - ms.officePixelW) / 2;
    const oy = (h - ms.officePixelH) / 2;
    ms.officeRoot.setScale(1).setPosition(ox, oy);
    this.agentLayer.setPosition(ox, oy);
  }

  /** Re-layout map on canvas resize. */
  private _onResize = (): void => {
    if (this.mapState) this._layoutMap();
  };

  private _makeWalkCtx(): WalkContext {
    return {
      scene: this,
      tileW: this.mapState!.tileW,
      tileH: this.mapState!.tileH,
      obstacleGrid: this.mapState!.obstacleGrid,
      agentSprites: this.agentSprites,
      agentFacing: this.agentFacing,
      agentIdleSinceMs: this.agentIdleSinceMs,
      idleTick: this.idleTick,
    };
  }

  // ─── Agent Sprite Lifecycle ──────────────────────────────────────────

  private async _loadAgentSprites(spawns: OfficeSceneSpawn[]): Promise<void> {
    const agents = useAgentStore.getState().agents;

    for (const agent of agents) {
      const spawn = spawns.find(
        (s) => s.agentAttr === agent.profile || s.agentAttr === agent.agentId,
      );
      const { px, py, initialFacing } = this._resolveSpawn(agent.agentId, spawn);
      const container = await createAgentSprite(
        this,
        this.agentLayer,
        agent.agentId,
        agent.avatar ?? 'badboy',
        px,
        py,
        initialFacing,
        agentSceneLabel(agent),
      );
      if (container) {
        this.agentSprites.set(agent.agentId, container);
        const facing = spriteFacingFromDirection(initialFacing);
        this.agentFacing.set(agent.agentId, facing);
        this.agentIdleSinceMs.set(agent.agentId, Date.now());
      }
    }
  }

  private _resolveSpawn(
    agentId: string,
    spawn: OfficeSceneSpawn | undefined,
  ): { px: number; py: number; initialFacing: Direction } {
    const ms = this.mapState!;
    const saved = useOfficeAgentPoseStore.getState().poses[agentId];
    if (saved && ms.officePixelW > 0 && ms.officePixelH > 0) {
      const c = clampAgentPixelPos(saved.x, saved.y, ms.officePixelW, ms.officePixelH);
      const f = saved.facing;
      const initialFacing: Direction =
        f === 'up' || f === 'left' || f === 'right' || f === 'down' ? f : 'down';
      return { px: c.x, py: c.y, initialFacing };
    }
    const px = spawn ? spawn.px : ms.officePixelW / 2;
    const py = spawn ? spawn.py : ms.officePixelH / 2 - 32;
    return { px, py, initialFacing: spawn?.direction ?? 'down' };
  }

  private _startIdleAnimation(): void {
    this.idleAnimEvent?.destroy();
    this.idleAnimEvent = this.time.addEvent({
      delay: 220,
      loop: true,
      callback: () => {
        for (const [id, cont] of this.agentSprites) {
          if (this.tweens.isTweening(cont)) continue;
          const img = cont.list[0] as Phaser.GameObjects.Image;
          const dir = this.agentFacing.get(id) ?? 'down';
          img.setFrame(personFrameIndex(dir, this.idleTick));
        }
        this.idleTick = (this.idleTick + 1) % 3;
      },
    });
  }

  private _startInferBubbleSync(): void {
    this.inferBubbleTimer?.destroy();
    this.inferBubbleTimer = this.time.addEvent({
      delay: 200,
      loop: true,
      callback: () => {
        const infer = useAgentStore.getState().agentSceneInfer;
        const now = Date.now();
        for (const [agentId, container] of this.agentSprites) {
          const st = infer[agentId];
          if (!st) continue;
          drawInferBubble(container, st, now);
        }
      },
    });
  }

  // ─── Post Update ─────────────────────────────────────────────────────

  private _onPostUpdate(): void {
    const ctx = this._makeWalkCtx();
    const { crossedPairs } = runAutonomyTick(
      ctx,
      this.encounter.frozen,
      this.pairLastFrameDistance,
      this.encounter.greetPairLastMs,
    );

    for (const [walkerId, peerId] of crossedPairs) {
      if (this.encounter.isInferBusy(walkerId) || this.encounter.isInferBusy(peerId)) continue;
      if (this.encounter.isSessionBusy(walkerId) || this.encounter.isSessionBusy(peerId)) continue;
      if (this.encounter.frozen.has(walkerId) || this.encounter.frozen.has(peerId)) continue;

      const greet = this.encounter.getGreetPrompt(walkerId, peerId);
      if (!greet) continue;

      this.encounter.freeze(walkerId, peerId);
      this.encounter.haltBoth(walkerId, peerId);
      this.encounter.faceToFace(walkerId, peerId);

      // Fire-and-forget greeting prompt
      void this._doGreeting(greet);
    }
  }

  private _sortAgentsByY(): void {
    if (this.agentSprites.size === 0) return;
    this.agentLayer.sort('y');
  }

  // ─── Greeting Protocol ───────────────────────────────────────────────

  private async _doGreeting(
    greet: { walkerSid: string; peerSid: string; walkerLabel: string; prompt: string },
  ): Promise<void> {
    const { walkerSid, peerSid, walkerLabel, prompt } = greet;
    const pending = this.encounter.pendingReplies;

    const sessionId = async (agentId: string): Promise<string | null> => {
      const sessionStore = useSessionStore.getState();
      const agentStore = useAgentStore.getState();
      const sid = sessionStore.sessions.find((s) => s.agentId === agentId)?.id?.trim();
      if (sid) return sid;
      const def = agentStore.agents.find((a) => a.agentId === agentId)?.defaultSessionId?.trim();
      return def || null;
    };

    // We need to extract walker/peer IDs from the promise
    // For now, fire-and-forget with SSE-driven completion
  }

  // ─── Click Interaction ───────────────────────────────────────────────

  private _onPointerDown(pointer: Phaser.Input.Pointer): void {
    // Right-click: move the selected agent to the clicked position
    if (pointer.rightButtonDown()) {
      this._onRightClick(pointer);
      return;
    }

    const hitId = this._agentIdFromPointer(pointer);
    if (hitId) {
      if (this.selectedAgentId === hitId) {
        this._clearSelection();
      } else {
        this._setSelection(hitId);
        void this._switchAgent(hitId);
        useUiStore.getState().setShowAgentList(false);
      }
      return;
    }

    if (this.selectedAgentId) {
      this._clearSelection();
    }
  }

  /** Right-click on the map: move the selected agent to the clicked tile. */
  private _onRightClick(pointer: Phaser.Input.Pointer): void {
    if (!this.selectedAgentId) return;
    const container = this.agentSprites.get(this.selectedAgentId);
    if (!container) return;

    const ms = this.mapState!;
    // 减去地图居中偏移，转为地图本地像素坐标
    const offsetX = this.agentLayer.x;
    const offsetY = this.agentLayer.y;
    const wp = this.cameras.main.getWorldPoint(pointer.x, pointer.y);
    const gx = Math.floor((wp.x - offsetX) / ms.tileW);
    const gy = Math.floor((wp.y - offsetY) / ms.tileH);
    const sx = Math.floor(container.x / ms.tileW);
    const sy = Math.floor(container.y / ms.tileH);
    const walkGrid = buildWalkGrid(
      ms.obstacleGrid,
      this.selectedAgentId,
      ms.tileW,
      ms.tileH,
      this.agentSprites,
    );

    const s = nearestWalkableTile(walkGrid, sx, sy);
    const g = nearestWalkableTile(walkGrid, gx, gy);
    if (!s || !g) return;

    const path = astar(walkGrid, s.x, s.y, g.x, g.y);
    if (!path.length) return;

    const ctx = this._makeWalkCtx();
    runAgentPath(ctx, this.selectedAgentId, path);
  }

  private _agentIdFromPointer(pointer: Phaser.Input.Pointer): string | null {
    const hits = this.input.hitTestPointer(pointer);
    for (const obj of hits) {
      let current: Phaser.GameObjects.GameObject | null = obj;
      while (current) {
        for (const [id, container] of this.agentSprites) {
          if (container === current) return id;
          if (container.list.includes(current as Phaser.GameObjects.GameObject)) return id;
        }
        current = current.parentContainer;
      }
    }
    return null;
  }

  private _clearSelection(): void {
    this.selectedAgentId = null;
    this.agentSprites.forEach((cont) => {
      (cont.list[1] as Phaser.GameObjects.Text).setStyle({ backgroundColor: '#5b8cffaa' });
    });
  }

  private _setSelection(agentId: string): void {
    this.selectedAgentId = agentId;
    this.agentSprites.forEach((cont, id) => {
      (cont.list[1] as Phaser.GameObjects.Text).setStyle({
        backgroundColor: id === agentId ? '#ff5b8caa' : '#5b8cffaa',
      });
    });
  }

  private async _switchAgent(agentId: string): Promise<void> {
    useAgentStore.getState().setSelectedAgentId(agentId);
    const store = useSessionStore.getState();
    const sess = store.sessions.find((s) => s.agentId === agentId);
    if (sess) {
      store.setActiveId(sess.id);
      return;
    }

    // 没有现有 session，需要创建
    try {
      const data = await apiFetch<{ sessionId: string }>('/api/chat/sessions', {
        method: 'POST',
        json: { agentId, timeoutMinutes: 120 },
      });
      const { sessionId } = data;
      store.addSession({
        id: sessionId,
        agentId,
        title: '',
        messages: [],
        processRows: [],
        streaming: false,
        unread: false,
      });
      store.setActiveId(sessionId);
    } catch (err) {
      console.error('[OfficeScene] _switchAgent 异常:', err);
    }
  }

  // ─── Store Subscriptions ─────────────────────────────────────────────

  private _subscribeStores(spawns: OfficeSceneSpawn[]): void {
    // Agent changes — new agents, removed agents, profile updates
    this._unsubs.push(useAgentStore.subscribe((s, prev) => {
      if (s.agents === prev.agents) return;

      const prevById = new Map(prev.agents.map((a) => [a.agentId, a]));
      const prevIds = new Set(prev.agents.map((a) => a.agentId));

      for (const a of s.agents) {
        if (!prevIds.has(a.agentId)) {
          const spawn = spawns.find(
            (sp) => sp.agentAttr === a.profile || sp.agentAttr === a.agentId,
          );
          const { px, py, initialFacing } = this._resolveSpawn(a.agentId, spawn);
          void createAgentSprite(
            this, this.agentLayer, a.agentId, a.avatar ?? 'badboy',
            px, py, initialFacing, agentSceneLabel(a),
          ).then((container) => {
            if (container) {
              this.agentSprites.set(a.agentId, container);
              this.agentFacing.set(a.agentId, spriteFacingFromDirection(initialFacing));
              this.agentIdleSinceMs.set(a.agentId, Date.now());
            }
          });
        } else {
          const p = prevById.get(a.agentId);
          if (p && (p.displayName !== a.displayName || p.avatar !== a.avatar)) {
            const cont = this.agentSprites.get(a.agentId);
            if (cont) {
              const facing = this.agentFacing.get(a.agentId) ?? 'down';
              void refreshAgentAppearance(this, cont, a, facing as Direction);
            }
          }
        }
      }

      for (const [id, container] of this.agentSprites) {
        if (!s.agents.find((ag) => ag.agentId === id)) {
          removeAgentSprite(container, id);
          this.agentSprites.delete(id);
          this.agentFacing.delete(id);
          this.agentIdleSinceMs.delete(id);
          for (const k of this.pairLastFrameDistance.keys()) {
            const [a, b] = k.split('\0');
            if (a === id || b === id) this.pairLastFrameDistance.delete(k);
          }
        }
      }
    }));

  }

  // ─── Pose Persistence ────────────────────────────────────────────────

  private async _flushPoses(): Promise<void> {
    const { dirty, poses } = useOfficeAgentPoseStore.getState();
    if (!dirty || Object.keys(poses).length === 0) return;
    try {
      await api.apiPostOfficePoses(poses);
      useOfficeAgentPoseStore.getState().clearDirty();
    } catch {
      // Retry on next tick
    }
  }

  // ─── Public API (for React hooks to call) ────────────────────────────

  /** Send an agent to walk to a tile position. */
  sendAgentToPos(agentId: string, tileX: number, tileY: number): boolean {
    const ms = this.mapState;
    if (!ms) return false;
    const container = this.agentSprites.get(agentId);
    if (!container) return false;

    const walkGrid = buildWalkGrid(
      ms.obstacleGrid, agentId, ms.tileW, ms.tileH, this.agentSprites,
    );
    const sx = Math.floor(container.x / ms.tileW);
    const sy = Math.floor(container.y / ms.tileH);
    const s = nearestWalkableTile(walkGrid, sx, sy);
    const g = nearestWalkableTile(walkGrid, tileX, tileY);
    if (!s || !g) return false;

    const path = astar(walkGrid, s.x, s.y, g.x, g.y);
    if (!path.length) return false;

    runAgentPath(this._makeWalkCtx(), agentId, path);
    return true;
  }

  /** Select an agent in the scene. */
  selectAgent(agentId: string): void {
    this._setSelection(agentId);
  }

  /** Clear agent selection. */
  clearSelection(): void {
    this._clearSelection();
  }

  /** Play delegation approach animation. */
  async playDelegationApproach(fromAgentId: string, toAgentId: string): Promise<void> {
    await this.encounter.playDelegationApproach(fromAgentId, toAgentId);
  }
}
