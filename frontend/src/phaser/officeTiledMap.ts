/**
 * Renders Tiled JSON from office_layer.json using office.png spritesheet.
 * 支持 infinite 图层的 `chunks`，以及有限地图的扁平 `data` + `width`/`height`。
 * GID flip decoding matches Phaser 3 ParseGID (MIT, photonstorm)。
 */
import { type Scene } from 'phaser';
import type { Direction } from '../types/direction';

const FLIPPED_HORIZONTAL = 0x80000000;
const FLIPPED_VERTICAL = 0x40000000;
const FLIPPED_ANTI_DIAGONAL = 0x20000000;

/** Same contract as Phaser.Tilemaps.Parsers.Tiled.ParseGID */
export function parseTiledGid(raw: number): { gid: number; rotation: number; flipped: boolean } {
  const flippedHorizontal = Boolean(raw & FLIPPED_HORIZONTAL);
  const flippedVertical = Boolean(raw & FLIPPED_VERTICAL);
  const flippedAntiDiagonal = Boolean(raw & FLIPPED_ANTI_DIAGONAL);
  let gid = raw & ~(FLIPPED_HORIZONTAL | FLIPPED_VERTICAL | FLIPPED_ANTI_DIAGONAL);

  let rotation = 0;
  let flipped = false;

  if (flippedHorizontal && flippedVertical && flippedAntiDiagonal) {
    rotation = Math.PI / 2;
    flipped = true;
  } else if (flippedHorizontal && flippedVertical && !flippedAntiDiagonal) {
    rotation = Math.PI;
    flipped = false;
  } else if (flippedHorizontal && !flippedVertical && flippedAntiDiagonal) {
    rotation = Math.PI / 2;
    flipped = false;
  } else if (flippedHorizontal && !flippedVertical && !flippedAntiDiagonal) {
    rotation = 0;
    flipped = true;
  } else if (!flippedHorizontal && flippedVertical && flippedAntiDiagonal) {
    rotation = (3 * Math.PI) / 2;
    flipped = false;
  } else if (!flippedHorizontal && flippedVertical && !flippedAntiDiagonal) {
    rotation = Math.PI;
    flipped = true;
  } else if (!flippedHorizontal && !flippedVertical && flippedAntiDiagonal) {
    rotation = (3 * Math.PI) / 2;
    flipped = true;
  } else {
    rotation = 0;
    flipped = false;
  }

  return { gid, rotation, flipped };
}

/** 单块精灵：对应 Tiled 中某一 tileset 的一帧（`sheetKey` 为 Phaser 精灵表 key）。 */
export type OfficeTileInst = {
  sheetKey: string;
  frame: number;
  px: number;
  py: number;
  rotation: number;
  flipped: boolean;
};

/** 已加载的 tileset 与 GID 区间（左闭右开），与 `office_layer.json` 中 tilesets 顺序一致。 */
export type ResolvedOfficeTileset = {
  firstGid: number;
  lastGidExclusive: number;
  textureKey: string;
  tileW: number;
  tileH: number;
};

export type OfficeCollectResult = {
  tiles: OfficeTileInst[];
  /**
   * 寻路静态障碍：同 `tiles` 但排除地板类图层（见 {@link isFloorTileLayer}）。
   * 人物等动态障碍不在此列，由运行时另行叠加。
   */
  obstacleTiles: OfficeTileInst[];
  /** 有 GID 但落在未加载/未知 tileset 区间的格子数 */
  unmappedCount: number;
  unmappedGidSamples: number[];
};

/** 图层名视为「可走地板」、不参与阻挡（如仓库图 `floot` 拼写） */
export function isFloorTileLayer(layerName: string | undefined): boolean {
  const n = (layerName ?? '').trim().toLowerCase();
  if (!n) return false;
  if (n === 'floor' || n === 'floot' || n === 'floors') return true;
  if (n === '地面' || n === '地板') return true;
  if (n.startsWith('floor')) return true;
  return false;
}

type TiledChunk = { x: number; y: number; width: number; height: number; data: number[] };

type TiledLayer = {
  type?: string;
  visible?: boolean;
  name?: string;
  x?: number;
  y?: number;
  offsetx?: number;
  offsety?: number;
  startx?: number;
  starty?: number;
  width?: number;
  height?: number;
  /** 有限地图：整层一维 data（Tiled 导出常见），与 infinite 的 chunks 二选一 */
  data?: number[];
  chunks?: TiledChunk[];
};

function resolveTilesetForGid(
  resolved: ResolvedOfficeTileset[],
  gid: number,
): ResolvedOfficeTileset | null {
  for (const r of resolved) {
    if (gid >= r.firstGid && gid < r.lastGidExclusive) return r;
  }
  return null;
}

/** 将 Tiled 格内原始值（含翻转高位）解析为精灵实例；GID 0 或无法映射时返回 null。 */
export function officeTileFromRawCell(
  resolved: ResolvedOfficeTileset[],
  rawCell: number,
  wtx: number,
  wty: number,
  tw: number,
  th: number,
  offx = 0,
  offy = 0,
): OfficeTileInst | null {
  const gidInfo = parseTiledGid(rawCell);
  if (gidInfo.gid <= 0) return null;
  const ts = resolveTilesetForGid(resolved, gidInfo.gid);
  if (!ts) return null;
  return {
    sheetKey: ts.textureKey,
    frame: gidInfo.gid - ts.firstGid,
    px: wtx * tw + offx,
    py: wty * th + offy,
    rotation: gidInfo.rotation,
    flipped: gidInfo.flipped,
  };
}

/**
 * 收集可绘制的图块：按 `resolved` 中多 tileset 的 GID 区间映射到对应精灵表与本地帧号。
 * 像素坐标与 Tiled 地图原点对齐（含 layer offset）。
 */
export function collectOfficeTilesFromMap(
  mapData: {
    layers?: TiledLayer[];
    tilewidth: number;
    tileheight: number;
    width?: number;
    height?: number;
    tilesets?: { firstgid?: number }[];
  },
  resolved: ResolvedOfficeTileset[],
): OfficeCollectResult {
  const tw = mapData.tilewidth || 32;
  const th = mapData.tileheight || 32;
  const layers = mapData.layers ?? [];
  const out: OfficeTileInst[] = [];
  const obstacleOut: OfficeTileInst[] = [];
  let unmappedCount = 0;
  const sampleSet = new Set<number>();

  const pushUnmapped = (gid: number) => {
    unmappedCount++;
    if (sampleSet.size < 40) sampleSet.add(gid);
  };

  for (const layer of layers) {
    if (layer.type !== 'tilelayer' || layer.visible === false) continue;
    const countAsObstacle = !isFloorTileLayer(layer.name);
    const offx = Number(layer.offsetx ?? 0);
    const offy = Number(layer.offsety ?? 0);
    const lx = Number(layer.x ?? 0);
    const ly = Number(layer.y ?? 0);

    const chunks = layer.chunks;
    if (chunks?.length) {
      /** Tiled：chunk 的 x,y 为该 chunk 左上角在「图块坐标」下的位置；格内 (cx,cy) 即世界格坐标 chunk+local。
       * 不要用 startx/starty 去减（那是 Phaser 层内打包索引用法，叠多层会错位）。 */
      for (const chunk of chunks) {
        let cx = 0;
        let cy = 0;
        for (let t = 0; t < chunk.data.length; t++) {
          const gidInfo = parseTiledGid(chunk.data[t]!);
          const wtx = chunk.x + cx;
          const wty = chunk.y + cy;
          if (gidInfo.gid > 0) {
            const ts = resolveTilesetForGid(resolved, gidInfo.gid);
            if (!ts) {
              pushUnmapped(gidInfo.gid);
            } else {
              const frame = gidInfo.gid - ts.firstGid;
              const inst: OfficeTileInst = {
                sheetKey: ts.textureKey,
                frame,
                px: wtx * tw + offx,
                py: wty * th + offy,
                rotation: gidInfo.rotation,
                flipped: gidInfo.flipped,
              };
              out.push(inst);
              if (countAsObstacle) obstacleOut.push(inst);
            }
          }
          cx++;
          if (cx === chunk.width) {
            cy++;
            cx = 0;
          }
        }
      }
      continue;
    }

    const flat = layer.data;
    const lw = Number(layer.width ?? 0);
    const lh = Number(layer.height ?? 0);
    if (!Array.isArray(flat) || lw <= 0 || lh <= 0) continue;
    const n = Math.min(flat.length, lw * lh);
    for (let i = 0; i < n; i++) {
      const cx = i % lw;
      const cy = Math.floor(i / lw);
      const gidInfo = parseTiledGid(flat[i]!);
      const wtx = lx + cx;
      const wty = ly + cy;
      if (gidInfo.gid > 0) {
        const ts = resolveTilesetForGid(resolved, gidInfo.gid);
        if (!ts) {
          pushUnmapped(gidInfo.gid);
        } else {
          const frame = gidInfo.gid - ts.firstGid;
          const inst: OfficeTileInst = {
            sheetKey: ts.textureKey,
            frame,
            px: wtx * tw + offx,
            py: wty * th + offy,
            rotation: gidInfo.rotation,
            flipped: gidInfo.flipped,
          };
          out.push(inst);
          if (countAsObstacle) obstacleOut.push(inst);
        }
      }
    }
  }

  return {
    tiles: out,
    obstacleTiles: obstacleOut,
    unmappedCount,
    unmappedGidSamples: [...sampleSet].sort((a, b) => a - b),
  };
}

export function officeMapPixelSize(tiles: OfficeTileInst[], tileW: number, tileH: number): { w: number; h: number } {
  let maxR = 0;
  let maxB = 0;
  for (const t of tiles) {
    maxR = Math.max(maxR, t.px + tileW);
    maxB = Math.max(maxB, t.py + tileH);
  }
  return { w: maxR, h: maxB };
}

/** 优先用 Tiled 地图 width/height（格）× 格尺寸，与编辑器整图边界一致；与图块包围盒取 max 兜底；缺省时退回包围盒。 */
export function officeMapPixelExtent(
  mapData: { width?: number; height?: number },
  tw: number,
  th: number,
  tiles: OfficeTileInst[],
): { w: number; h: number } {
  const bbox = officeMapPixelSize(tiles, tw, th);
  const gw = Number(mapData.width ?? 0);
  const gh = Number(mapData.height ?? 0);
  if (gw > 0 && gh > 0) {
    return { w: Math.max(gw * tw, bbox.w), h: Math.max(gh * th, bbox.h) };
  }
  return bbox;
}

/**
 * Build a 2D boolean grid for A* pathfinding.
 * grid[y][x] = true means walkable, false means obstacle.
 * Tile size is inferred from the maximum tile coordinates in obstacleTiles.
 */
export function buildObstacleGrid(
  obstacleTiles: OfficeTileInst[],
  tileW: number,
  tileH: number,
): { grid: boolean[][]; gridW: number; gridH: number } {
  let maxTx = 0;
  let maxTy = 0;
  for (const t of obstacleTiles) {
    const tx = Math.floor(t.px / tileW);
    const ty = Math.floor(t.py / tileH);
    if (tx > maxTx) maxTx = tx;
    if (ty > maxTy) maxTy = ty;
  }
  const gridW = maxTx + 1;
  const gridH = maxTy + 1;
  // start all walkable, mark obstacles
  const grid: boolean[][] = Array.from({ length: gridH }, () => Array<boolean>(gridW).fill(true));
  for (const t of obstacleTiles) {
    const tx = Math.floor(t.px / tileW);
    const ty = Math.floor(t.py / tileH);
    if (ty >= 0 && ty < gridH && tx >= 0 && tx < gridW) {
      grid[ty]![tx] = false;
    }
  }
  return { grid, gridW, gridH };
}


export function createOfficeTileContainer(
  scene: Scene,
  tiles: OfficeTileInst[],
  tileW: number,
  tileH: number,
): Phaser.GameObjects.Container {
  const c = scene.add.container(0, 0);
  /** 低于人物层（人物 depth 见 StudioScene），保证瓦片在下 */
  c.setDepth(0.2);
  // 对所有用到的纹理设置 NEAREST 滤波，避免缩放后出现亚像素间隙
  const usedKeys = [...new Set(tiles.map((t) => t.sheetKey))];
  for (const key of usedKeys) {
    if (scene.textures.exists(key)) {
      scene.textures.get(key).setFilter(Phaser.Textures.FilterMode.NEAREST);
    }
  }
  const hw = tileW / 2;
  const hh = tileH / 2;
  for (const t of tiles) {
    const img = scene.add.image(t.px + hw, t.py + hh, t.sheetKey, t.frame);
    img.setOrigin(0.5, 0.5);
    img.setRotation(t.rotation);
    img.setFlip(t.flipped, false);
    c.add(img);
  }
  return c;
}

/** Tiled 对象上 `properties` 数组项 */
export type TiledObjectProperty = { name?: string; type?: string; value?: unknown };

export type TiledMapObject = {
  id?: number;
  x?: number;
  y?: number;
  width?: number;
  height?: number;
  /** Tiled 1.9+ 对象类型 */
  class?: string;
  /** 旧版类型字段 */
  type?: string;
  visible?: boolean;
  properties?: TiledObjectProperty[];
};

/** 人物站位：与 Agent.profile（或 id/name）对齐的 `agent` 属性值，像素为地图坐标（脚底）。 */
export type OfficeSceneSpawn = {
  agentAttr: string;
  px: number;
  py: number;
  direction: Direction;
};

function readPropertyNumber(props: TiledObjectProperty[], key: string): number | null {
  const p = props.find((q) => q.name === key);
  if (!p) return null;
  const v = p.value;
  const n = typeof v === 'string' ? Number(String(v).trim()) : Number(v);
  return Number.isFinite(n) ? n : null;
}

/** `properties` 里 direction 的 value：0 上 1 下 2 左 3 右（支持 string / int）。 */
export function directionFromTiledPropertyValue(raw: unknown): Direction {
  const n = typeof raw === 'string' ? Number(String(raw).trim()) : Number(raw);
  if (n === 0) return 'up';
  if (n === 1) return 'down';
  if (n === 2) return 'left';
  if (n === 3) return 'right';
  return 'down';
}

/**
 * 从 `office_layer.json` 中 `type: objectgroup` 且 `class` 为 `sp` 的图层读取人物站位。
 * `properties`：`agent` → 对齐 profile / id / name；`direction` → 朝向；**`x` / `y` → 地图像素坐标（优先于 object 根上的 x/y）**。
 * 若图层本身不是 class=sp，则仅处理其中 `class`/`type` 为 `sp` 的单个 object。
 */
export function collectOfficeSpawnsFromMap(mapData: {
  layers?: Array<{
    type?: string;
    visible?: boolean;
    class?: string;
    name?: string;
    x?: number;
    y?: number;
    offsetx?: number;
    offsety?: number;
    objects?: TiledMapObject[];
  }>;
}): OfficeSceneSpawn[] {
  const out: OfficeSceneSpawn[] = [];

  for (const layer of mapData.layers ?? []) {
    if (layer.type !== 'objectgroup' || layer.visible === false) continue;
    const layerClass = String(layer.class ?? '').trim();
    const layerIsSp = layerClass === 'sp' || String(layer.name ?? '').toLowerCase() === 'sp';
    const loffx = Number(layer.offsetx ?? 0) + Number(layer.x ?? 0);
    const loffy = Number(layer.offsety ?? 0) + Number(layer.y ?? 0);

    for (const obj of layer.objects ?? []) {
      if (obj.visible === false) continue;
      const objClass = String(obj.class ?? '').trim();
      const objType = String(obj.type ?? '').trim();
      const objIsSp = objClass === 'sp' || objType === 'sp';
      if (!layerIsSp && !objIsSp) continue;

      const props = obj.properties ?? [];
      let agentAttr = '';
      let directionRaw: unknown = 1;
      for (const p of props) {
        if (p.name === 'agent') agentAttr = String(p.value ?? '').trim();
        if (p.name === 'direction') directionRaw = p.value;
      }
      if (!agentAttr) continue;

      const pxProp = readPropertyNumber(props, 'x');
      const pyProp = readPropertyNumber(props, 'y');
      const px = (pxProp != null ? pxProp : Number(obj.x ?? 0)) + loffx;
      const py = (pyProp != null ? pyProp : Number(obj.y ?? 0)) + loffy;
      out.push({
        agentAttr,
        px,
        py,
        direction: directionFromTiledPropertyValue(directionRaw),
      });
    }
  }

  return out;
}
