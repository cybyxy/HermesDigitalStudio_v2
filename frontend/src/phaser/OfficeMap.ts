/**
 * Office Map Module — map loading, obstacle grid, and pixel utilities.
 * Extracted from UIMainScene_OfficeMixin.
 */
import Phaser from 'phaser';
import { mountBungalowOfficeMap, releaseBungalowOfficeTextures } from './bungalowOfficeLoader';
import type { OfficeSceneSpawn } from './officeTiledMap';

// ─── Types ───────────────────────────────────────────────────────────────

export interface MapState {
  officeRoot: Phaser.GameObjects.Container;
  officePixelW: number;
  officePixelH: number;
  officeTextureKeys: string[];
  obstacleGrid: boolean[][];
  gridW: number;
  gridH: number;
  tileW: number;
  tileH: number;
  spawns: OfficeSceneSpawn[];
}

// ─── Map Loading ─────────────────────────────────────────────────────────

export interface LoadMapResult {
  mapState: MapState;
  agentLayer: Phaser.GameObjects.Container;
}

/** Load the HermesBungalow office map into a Phaser scene. */
export async function loadOfficeMap(
  scene: Phaser.Scene,
  hintCb?: (msg: string) => void,
): Promise<LoadMapResult | null> {
  const agentLayer = scene.add.container(0, 0);
  agentLayer.setDepth(0.5);

  const mounted = await mountBungalowOfficeMap(scene, (msg) => {
    hintCb?.(msg);
  });
  if (!mounted) return null;

  const mapState: MapState = {
    officeRoot: mounted.root,
    officePixelW: mounted.pixelW,
    officePixelH: mounted.pixelH,
    officeTextureKeys: mounted.textureKeys,
    obstacleGrid: mounted.obstacleGrid,
    gridW: mounted.gridW,
    gridH: mounted.gridH,
    tileW: mounted.tileW,
    tileH: mounted.tileH,
    spawns: mounted.spawns,
  };

  return { mapState, agentLayer };
}

/** Release all office map textures from the Phaser cache. */
export function releaseOfficeMap(scene: Phaser.Scene, textureKeys: string[]): void {
  releaseBungalowOfficeTextures(scene, textureKeys);
}

// ─── Pixel / Tile Utilities ─────────────────────────────────────────────

/** Clamp a pixel position to within the map bounds. */
export function clampAgentPixelPos(
  px: number,
  py: number,
  mapW: number,
  mapH: number,
): { x: number; y: number } {
  const pad = 12;
  const w = Math.max(mapW, pad * 2 + 1);
  const h = Math.max(mapH, pad * 2 + 1);
  return {
    x: Math.min(Math.max(px, pad), w - pad),
    y: Math.min(Math.max(py, pad), h - pad),
  };
}

/** World-pixel position from tile coordinates. */
export function tileToWorld(
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

/** Tile coordinates from world-pixel position. */
export function worldToTile(
  wx: number,
  wy: number,
  tileW: number,
  tileH: number,
): { tx: number; ty: number } {
  return {
    tx: Math.floor(wx / tileW),
    ty: Math.floor(wy / tileH),
  };
}
