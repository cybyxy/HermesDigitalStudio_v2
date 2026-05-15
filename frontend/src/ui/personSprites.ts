/// <reference types="vite/client" />
import { publicAssetUrl } from '../lib/publicAssetUrl';

/**
 * Vite `import.meta.glob` 路径相对**本文件**（`src/ui/personSprites.ts`），
 * 必须指向 `public/assets/person/...`（`./assets` 会错解到 `src/ui/assets`，匹配为空）。
 */
const _MALE_GLOB = import.meta.glob('../../public/assets/person/male/*.png', {
  eager: true,
  import: 'default',
});
const _FEMALE_GLOB = import.meta.glob('../../public/assets/person/female/*.png', {
  eager: true,
  import: 'default',
});

function spriteBasesFromGlob(glob: Record<string, unknown>): string[] {
  return Object.keys(glob).map(k => {
    const filename = k.split('/').pop() ?? '';
    return filename.replace(/\.png$/i, '');
  });
}

const _MALE_BASES_LIST = spriteBasesFromGlob(_MALE_GLOB);
const _FEMALE_BASES_LIST = spriteBasesFromGlob(_FEMALE_GLOB);

/** `public/assets/person/male/*.png` 下的全部 base 名 */
export const PERSON_MALE_BASES = _MALE_BASES_LIST as readonly string[];

/** `public/assets/person/female/*.png` 下的全部 base 名 */
export const PERSON_FEMALE_BASES = _FEMALE_BASES_LIST as readonly string[];

/** 全部人物 sprite base（两目录合并，用于预加载等） */
export const PERSON_SHEET_BASES = [..._MALE_BASES_LIST, ..._FEMALE_BASES_LIST] as readonly string[];

export type PersonBase = string;

export const PERSON_FRAME_W = 32;
export const PERSON_FRAME_H = 48;

/** 根据磁盘上所在目录决定 URL（避免硬编码列表与 public 不一致） */
function _genderDir(base: string): 'male' | 'female' {
  const inMale = _MALE_BASES_LIST.includes(base);
  const inFemale = _FEMALE_BASES_LIST.includes(base);
  if (inFemale && !inMale) return 'female';
  if (inMale) return 'male';
  if (inFemale) return 'female';
  return 'male';
}

export function getPersonSheetUrl(base: string): string {
  return publicAssetUrl(`assets/person/${_genderDir(base)}/${base}.png`);
}

/** 获取指定性别目录下的 sprite base（来自 glob，与 public 一致） */
export function getSpriteBasesByGender(gender: 'male' | 'female'): string[] {
  return gender === 'female' ? [..._FEMALE_BASES_LIST] : [..._MALE_BASES_LIST];
}

/** Phaser texture key，避免与其它资源重名 */
export function personTextureKey(base: string): string {
  return `person__${base}`;
}

/** 雪碧 3×4：行=朝向，列=帧，Phaser 帧号行优先 0..11 */
export function personFrameIndex(dir: 'down' | 'up' | 'left' | 'right' | 'idle', colFrame: number): number {
  const col = Math.max(0, Math.min(2, colFrame));
  return spriteSheetRow(dir) * 3 + col;
}

/** 3×4 雪碧行索引：down / idle →0，left→1，right→2，up→3 */
export function spriteSheetRow(dir: 'down' | 'up' | 'left' | 'right' | 'idle'): number {
  switch (dir) {
    case 'down':
    case 'idle':
      return 0;
    case 'left':
      return 1;
    case 'right':
      return 2;
    case 'up':
      return 3;
    default:
      return 0;
  }
}

/**
 * Draw one animated sprite frame onto any canvas element.
 * Convenience wrapper around `personFrameIndex` + `getPersonSheetUrl`.
 */
export function drawAvatarFrame(
  canvas: HTMLCanvasElement,
  avatar: string,
  tick = 0,
): void {
  const img = new Image();
  img.onload = () => {
    const fi = personFrameIndex('down', tick % 3);
    const row = Math.floor(fi / 3);
    const col = fi % 3;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;
    canvas.width = PERSON_FRAME_W;
    canvas.height = PERSON_FRAME_H;
    ctx.imageSmoothingEnabled = false;
    ctx.clearRect(0, 0, PERSON_FRAME_W, PERSON_FRAME_H);
    ctx.drawImage(
      img,
      col * PERSON_FRAME_W,
      row * PERSON_FRAME_H,
      PERSON_FRAME_W,
      PERSON_FRAME_H,
      0,
      0,
      PERSON_FRAME_W,
      PERSON_FRAME_H,
    );
  };
  img.src = getPersonSheetUrl(avatar);
}
