/**
 * 从 HermesBungalow 迁入：加载 office_layer.json + 多 tileset PNG，绘制为 Phaser Container。
 */
import type { Scene } from 'phaser';
import {
  buildObstacleGrid,
  collectOfficeTilesFromMap,
  collectOfficeSpawnsFromMap,
  createOfficeTileContainer,
  officeMapPixelExtent,
  type ResolvedOfficeTileset,
  type OfficeSceneSpawn,
} from './officeTiledMap';
import { publicAssetUrl } from '../lib/publicAssetUrl';

/**
 * 将图集绘制到离屏 Canvas 再 `addSpriteSheet`，避免「先 addImage 再 textures.remove」破坏源与帧数据导致瓦片不显示。
 */
function loadOfficeTilesetSpriteSheet(
  scene: Scene,
  textureKey: string,
  imageUrl: string,
  tw: number,
  th: number,
): Promise<boolean> {
  return new Promise((resolve) => {
    const img = new Image();
    /** 同源静态资源不要设 anonymous，否则部分环境下会触发多余 CORS 校验导致 onerror */
    img.onload = () => {
      try {
        const w = img.naturalWidth;
        const h = img.naturalHeight;
        if (w < tw || h < th) {
          resolve(false);
          return;
        }
        const canvas = document.createElement('canvas');
        canvas.width = w;
        canvas.height = h;
        const ctx = canvas.getContext('2d');
        if (!ctx) {
          resolve(false);
          return;
        }
        ctx.drawImage(img, 0, 0);
        if (scene.textures.exists(textureKey)) scene.textures.remove(textureKey);
        const tex = scene.textures.addSpriteSheet(textureKey, canvas as unknown as HTMLImageElement, { frameWidth: tw, frameHeight: th });
        resolve(tex != null);
      } catch {
        resolve(false);
      }
    };
    img.onerror = () => resolve(false);
    img.src = imageUrl;
  });
}

function tilesetSourceToJsonCandidates(source: string): string[] {
  const s = source.replace(/^\.\//, '').trim();
  const out: string[] = [];
  if (s.toLowerCase().endsWith('.tsx')) {
    out.push(s.replace(/\.tsx$/i, '.json'));
    out.push(s);
  } else {
    out.push(s);
  }
  return [...new Set(out)];
}

function imageFileCandidates(tilesetSourceFile: string, imageField: string): string[] {
  const img0 = imageField.replace(/^\.\//, '');
  const out: string[] = [img0];
  const stem = tilesetSourceFile.replace(/\.(json|tsx)$/i, '');
  const derived = `${stem}.png`;
  if (!out.includes(derived)) out.push(derived);
  if (/^SST-/i.test(img0)) {
    const alt = img0.replace(/^SST-/i, 'ST-');
    if (!out.includes(alt)) out.push(alt);
  }
  return [...new Set(out)];
}

export type BungalowOfficeMountResult = {
  root: Phaser.GameObjects.Container;
  pixelW: number;
  pixelH: number;
  textureKeys: string[];
  /** 2D grid for A* pathfinding: grid[y][x] = true (walkable). */
  obstacleGrid: boolean[][];
  gridW: number;
  gridH: number;
  /** Pixel size of each tile (for coordinate conversion). */
  tileW: number;
  tileH: number;
  /** Spawn points read from the sp objectgroup. */
  spawns: OfficeSceneSpawn[];
};

/**
 * 加载 HermesBungalow 办公室 Tiled 地图并返回根容器（未定位/缩放，由调用方 layout）。
 */
export async function mountBungalowOfficeMap(
  scene: Scene,
  onStatus?: (msg: string) => void,
): Promise<BungalowOfficeMountResult | null> {
  const textureKeys: string[] = [];

  const status = (msg: string) => {
    onStatus?.(msg);
  };

  try {
    const mapRes = await fetch(publicAssetUrl('assets/tiles/office_layer.json'));
    if (!mapRes.ok) {
      status(`地图 office_layer.json 读取失败 ${mapRes.status}`);
      return null;
    }

    const mapData = (await mapRes.json()) as {
      layers?: unknown[];
      tilewidth?: number;
      tileheight?: number;
      width?: number;
      height?: number;
      tilesets?: { firstgid?: number; source?: string }[];
    };

    const tw = Number(mapData.tilewidth ?? 32);
    const th = Number(mapData.tileheight ?? 32);

    const tsRefs = (mapData.tilesets ?? [])
      .filter((t) => Number(t.firstgid) > 0 && typeof t.source === 'string')
      .sort((a, b) => Number(a.firstgid) - Number(b.firstgid)) as { firstgid: number; source: string }[];

    if (!tsRefs.length) {
      status('office_layer 未声明 tilesets');
      return null;
    }

    const resolved: ResolvedOfficeTileset[] = [];

    for (let i = 0; i < tsRefs.length; i++) {
      const ref = tsRefs[i]!;
      const firstGid = Number(ref.firstgid);
      const source = ref.source;
      const sourceBase = source.split('/').pop() ?? 'tileset.json';

      type TsDocShape = { image?: string; tilecount?: number; tilewidth?: number; tileheight?: number };
      let tsDoc: TsDocShape | null = null;
      for (const rel of tilesetSourceToJsonCandidates(source)) {
        const r = await fetch(publicAssetUrl(`assets/tiles/${rel}`));
        if (r.ok) {
          tsDoc = (await r.json()) as TsDocShape;
          break;
        }
      }
      if (!tsDoc?.image) {
        if (i === 0) {
          status(`无法读取首个 tileset（${source}）`);
          return null;
        }
        continue;
      }

      const nextFirst = i + 1 < tsRefs.length ? Number(tsRefs[i + 1]!.firstgid) : null;
      const tileCount = Number(tsDoc.tilecount ?? 0);
      const lastGidExclusive =
        nextFirst != null && nextFirst > firstGid ? nextFirst : firstGid + (tileCount > 0 ? tileCount : 512);

      const tsw = Number(tsDoc.tilewidth ?? tw);
      const tsh = Number(tsDoc.tileheight ?? th);
      const textureKey = `bungalow-ts-${firstGid}`;
      let loaded = false;
      for (const img of imageFileCandidates(sourceBase, tsDoc.image)) {
        const url = publicAssetUrl(`assets/tiles/${img}`);
        if (await loadOfficeTilesetSpriteSheet(scene, textureKey, url, tsw, tsh)) {
          textureKeys.push(textureKey);
          resolved.push({
            firstGid,
            lastGidExclusive,
            textureKey,
            tileW: tsw,
            tileH: tsh,
          });
          loaded = true;
          break;
        }
      }
      if (!loaded && i === 0) {
        const tried = imageFileCandidates(sourceBase, tsDoc.image)
          .map((f) => publicAssetUrl(`assets/tiles/${f}`))
          .join(', ');
        status(`主图集 PNG 加载失败，已尝试：${tried}`);
        return null;
      }
    }

    if (!resolved.length) return null;

    const cr = collectOfficeTilesFromMap(
      mapData as Parameters<typeof collectOfficeTilesFromMap>[0],
      resolved,
    );
    const tiles = cr.tiles;
    if (!tiles.length) {
      status('解析后无图块');
      return null;
    }

    const root = createOfficeTileContainer(scene, tiles, tw, th);
    root.setDepth(0.15);

    const extentMeta: { width?: number; height?: number } = mapData;
    const { w: pixelW, h: pixelH } = officeMapPixelExtent(extentMeta, tw, th, tiles);

    // Build A* grid from obstacle tiles
    const { grid: obstacleGrid, gridW, gridH } = buildObstacleGrid(cr.obstacleTiles, tw, th);

    // Collect spawn points
    const spawns = collectOfficeSpawnsFromMap(
      mapData as Parameters<typeof collectOfficeSpawnsFromMap>[0],
    );

    status('办公室地图已加载（HermesBungalow）');
    return { root, pixelW, pixelH, textureKeys, obstacleGrid, gridW, gridH, tileW: tw, tileH: th, spawns };
  } catch (e) {
    status(`地图加载异常：${(e as Error).message}`);
    return null;
  }
}

export function releaseBungalowOfficeTextures(scene: Scene, keys: string[]): void {
  for (const k of keys) {
    if (scene.textures.exists(k)) scene.textures.remove(k);
  }
}
