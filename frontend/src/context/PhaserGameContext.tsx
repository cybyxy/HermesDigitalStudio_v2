/**
 * PhaserGameContext — initializes the Phaser game and provides the instance
 * to React components via context.
 *
 * This replaces the direct `new Phaser.Game(config)` in main.ts.
 * The game canvas is mounted inside the PhaserCanvas component.
 */
import { createContext, useContext, useRef, useState, useEffect, useCallback, type ReactNode } from 'react';
import Phaser from 'phaser';
import { BootScene, OfficeScene } from '../phaser/OfficeScene';

// ─── Types ───────────────────────────────────────────────────────────────

interface PhaserGameContextValue {
  game: Phaser.Game | null;
  /** Get the running OfficeScene instance (or null if not yet loaded). */
  getOfficeScene: () => OfficeScene | null;
}

const PhaserGameCtx = createContext<PhaserGameContextValue>({
  game: null,
  getOfficeScene: () => null,
});

// ─── Provider ────────────────────────────────────────────────────────────

interface Props {
  containerRef: React.RefObject<HTMLDivElement | null>;
  children: ReactNode;
}

export function PhaserGameProvider({ containerRef, children }: Props) {
  const gameRef = useRef<Phaser.Game | null>(null);
  const [game, setGame] = useState<Phaser.Game | null>(null);

  useEffect(() => {
    const el = containerRef.current;
    if (!el || gameRef.current) return;

    const config: Phaser.Types.Core.GameConfig = {
      type: Phaser.AUTO,
      parent: el,
      width: el.clientWidth || 800,
      height: el.clientHeight || 600,
      backgroundColor: '#0c0e12',
      scene: [BootScene, OfficeScene],
      render: { antialias: true },
      scale: {
        mode: Phaser.Scale.RESIZE,
        autoCenter: Phaser.Scale.NO_CENTER,
      },
    };

    const instance = new Phaser.Game(config);
    gameRef.current = instance;
    setGame(instance);

    return () => {
      instance.destroy(true);
      gameRef.current = null;
    };
  }, [containerRef]);

  // Keep Phaser canvas size in sync with container dimensions
  useEffect(() => {
    if (!game) return;
    const el = containerRef.current;
    if (!el) return;

    const resize = (): void => {
      const w = Math.max(64, el.clientWidth);
      const h = Math.max(64, el.clientHeight);
      game.scale.resize(w, h);
    };

    // Initial resize after layout settles
    requestAnimationFrame(resize);

    if (typeof ResizeObserver !== 'undefined') {
      const ro = new ResizeObserver(resize);
      ro.observe(el);
      return () => ro.disconnect();
    }

    window.addEventListener('resize', resize);
    return () => window.removeEventListener('resize', resize);
  }, [game, containerRef]);

  const getOfficeScene = useCallback((): OfficeScene | null => {
    const g = gameRef.current;
    if (!g) return null;
    const scene = g.scene.getScene('Office') as OfficeScene | undefined;
    return scene?.scene.isActive() ? scene : null;
  }, []);

  return (
    <PhaserGameCtx.Provider value={{ game, getOfficeScene }}>
      {children}
    </PhaserGameCtx.Provider>
  );
}

// ─── Hook ────────────────────────────────────────────────────────────────

export function usePhaserGame(): PhaserGameContextValue {
  return useContext(PhaserGameCtx);
}
