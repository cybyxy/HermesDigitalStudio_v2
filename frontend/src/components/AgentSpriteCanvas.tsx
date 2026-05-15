/**
 * AgentSpriteCanvas — renders an animated pixel-art sprite from a spritesheet.
 * Shared by AgentList and MemoryList.
 */
import { useEffect, useRef } from 'react';
import {
  PERSON_FRAME_W, PERSON_FRAME_H,
  getPersonSheetUrl, personFrameIndex,
} from '../ui/personSprites';
import type { AgentInfo } from '../types';

export function AgentSpriteCanvas({ agent }: { agent: AgentInfo }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const tickRef = useRef(0);
  const imgRef = useRef<HTMLImageElement | null>(null);

  useEffect(() => {
    const img = new Image();
    img.src = getPersonSheetUrl(agent.avatar || 'badboy');
    img.onload = () => {
      imgRef.current = img;
      draw(0);
    };

    const interval = setInterval(() => {
      tickRef.current = (tickRef.current + 1) % 3;
      draw(tickRef.current);
    }, 220);

    function draw(col: number) {
      const canvas = canvasRef.current;
      const img = imgRef.current;
      if (!canvas || !img) return;
      const ctx = canvas.getContext('2d');
      if (!ctx) return;
      ctx.imageSmoothingEnabled = false;
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      const fi = personFrameIndex('down', col % 3);
      const row = Math.floor(fi / 3);
      const colF = fi % 3;
      ctx.drawImage(
        img,
        colF * PERSON_FRAME_W, row * PERSON_FRAME_H,
        PERSON_FRAME_W, PERSON_FRAME_H,
        0, 0, canvas.width, canvas.height,
      );
    }

    return () => clearInterval(interval);
  }, [agent.avatar]);

  return (
    <canvas
      ref={canvasRef}
      width={PERSON_FRAME_W}
      height={PERSON_FRAME_H}
      style={{ imageRendering: 'pixelated', display: 'block' }}
    />
  );
}
