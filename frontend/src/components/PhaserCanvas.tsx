/**
 * PhaserCanvas — React component that hosts the Phaser game canvas.
 *
 * The Phaser game is initialized by PhaserGameProvider using a portal-like
 * pattern: the container div ref is passed up via context, and the game
 * mounts its canvas inside this element.
 */
import { useEffect, useRef } from 'react';
import { usePhaserGame } from '../context/PhaserGameContext';

export function PhaserCanvas() {
  const containerRef = useRef<HTMLDivElement>(null);
  const { game } = usePhaserGame();

  // Resize handler — keep Phaser canvas in sync with container size
  useEffect(() => {
    const el = containerRef.current;
    if (!game || !el) return;

    const resize = (): void => {
      const w = Math.max(64, el.clientWidth);
      const h = Math.max(64, el.clientHeight);
      game.scale.resize(w, h);
    };

    // Initial resize
    resize();

    if (typeof ResizeObserver !== 'undefined') {
      const ro = new ResizeObserver(resize);
      ro.observe(el);
      return () => ro.disconnect();
    }

    window.addEventListener('resize', resize);
    return () => window.removeEventListener('resize', resize);
  }, [game]);

  return (
    <div
      ref={containerRef}
      id="phaser-container"
      style={{ width: '100%', height: '100%', overflow: 'hidden' }}
    />
  );
}
