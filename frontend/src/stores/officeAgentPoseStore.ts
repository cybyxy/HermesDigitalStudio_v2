import { create } from 'zustand';

/** 与场景中 `agentFacing` / 雪碧行一致 */
export type OfficeSpriteFacing = 'down' | 'up' | 'left' | 'right';

export interface OfficeAgentPose {
  x: number;
  y: number;
  facing: OfficeSpriteFacing;
}

export interface OfficePoseHydrateInput {
  agentId: string;
  /** 后端有记录时为坐标；无记录时为 null */
  officePose?: { x: number; y: number; facing?: string } | null;
}

interface OfficeAgentPoseState {
  /** 内存缓存；定期同步到后端 SQLite */
  poses: Record<string, OfficeAgentPose>;
  /** 本地相对 DB 有未落库的修改 */
  dirty: boolean;
  setPose: (agentId: string, pose: OfficeAgentPose) => void;
  /** 从 GET /agents 的 officePose 合并；有未保存本地修改时不覆盖 */
  hydrateFromAgents: (agents: OfficePoseHydrateInput[]) => void;
  removePose: (agentId: string) => void;
  clearDirty: () => void;
}

function normalizeFacing(f: string | undefined): OfficeSpriteFacing {
  const v = (f || 'down').toLowerCase();
  if (v === 'up' || v === 'left' || v === 'right' || v === 'down') return v;
  return 'down';
}

export const useOfficeAgentPoseStore = create<OfficeAgentPoseState>((set) => ({
  poses: {},
  dirty: false,
  setPose: (agentId, pose) =>
    set((s) => ({
      poses: { ...s.poses, [agentId]: { ...pose } },
      dirty: true,
    })),
  hydrateFromAgents: (agents) =>
    set((s) => {
      if (s.dirty) return s;
      const next = { ...s.poses };
      for (const a of agents) {
        const p = a.officePose;
        if (p === null) {
          delete next[a.agentId];
          continue;
        }
        if (
          p &&
          typeof p.x === 'number' &&
          Number.isFinite(p.x) &&
          typeof p.y === 'number' &&
          Number.isFinite(p.y)
        ) {
          next[a.agentId] = {
            x: p.x,
            y: p.y,
            facing: normalizeFacing(p.facing),
          };
        }
      }
      return { poses: next, dirty: false };
    }),
  removePose: (agentId) =>
    set((s) => {
      const { [agentId]: _removed, ...rest } = s.poses;
      return { poses: rest, dirty: true };
    }),
  clearDirty: () => set({ dirty: false }),
}));
