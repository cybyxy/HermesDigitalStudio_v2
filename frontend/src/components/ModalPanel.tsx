/**
 * ModalPanel — React replacement for the class-based ModalPanel.
 *
 * Supports both modal (backdrop, blocks interaction) and non-modal
 * (draggable, no backdrop) modes.
 */
import { useState, useRef, useEffect, useCallback, type ReactNode } from 'react';

export interface ModalPanelProps {
  title: string;
  icon?: string;
  maxWidth?: string;
  modal?: boolean;
  children?: ReactNode;
  onClose?: () => void;
}

export function ModalPanel({
  title,
  icon,
  maxWidth = '36rem',
  modal = false,
  children,
  onClose,
}: ModalPanelProps) {
  const [zIndex, setZIndex] = useState(modal ? 51000 : 1000);
  const cardRef = useRef<HTMLDivElement>(null);
  const dragRef = useRef<{ dx: number; dy: number; dragging: boolean }>({
    dx: 0,
    dy: 0,
    dragging: false,
  });

  const bringToFront = useCallback(() => {
    setZIndex((prev) => prev + 1);
  }, []);

  // Drag handling (non-modal only)
  const onMouseDown = useCallback(
    (e: React.MouseEvent) => {
      if (modal) return;
      const target = e.target as HTMLElement;
      if (target.closest('button[data-close]')) return;
      const card = cardRef.current;
      if (!card) return;
      dragRef.current = {
        dx: e.clientX - card.offsetLeft,
        dy: e.clientY - card.offsetTop,
        dragging: true,
      };
      bringToFront();
    },
    [modal, bringToFront],
  );

  useEffect(() => {
    if (modal) return;
    const onMove = (e: MouseEvent) => {
      const d = dragRef.current;
      if (!d.dragging || !cardRef.current) return;
      cardRef.current.style.left = `${e.clientX - d.dx}px`;
      cardRef.current.style.top = `${e.clientY - d.dy}px`;
    };
    const onUp = () => {
      dragRef.current.dragging = false;
    };
    document.addEventListener('mousemove', onMove);
    document.addEventListener('mouseup', onUp);
    return () => {
      document.removeEventListener('mousemove', onMove);
      document.removeEventListener('mouseup', onUp);
    };
  }, [modal]);

  return (
    <div
      style={{
        position: 'fixed',
        inset: 0,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        zIndex,
        background: modal ? 'rgba(0,0,0,0.5)' : 'transparent',
        pointerEvents: modal ? 'auto' : 'none',
      }}
      onClick={(e) => {
        if (modal && e.target === e.currentTarget) {
          onClose?.();
        }
      }}
    >
      <div
        ref={cardRef}
        style={{
          background: '#141820',
          border: '1px solid #2a3140',
          borderRadius: 8,
          boxShadow: '0 8px 28px rgba(0,0,0,0.45)',
          maxWidth,
          width: '100%',
          display: 'flex',
          flexDirection: 'column',
          maxHeight: '85vh',
          ...(modal
            ? {}
            : {
                position: 'absolute',
                top: '10%',
                left: '10%',
                minHeight: 120,
                minWidth: 280,
              }),
          pointerEvents: 'auto',
        }}
        onMouseDown={onMouseDown}
      >
        {/* Header */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            gap: 8,
            padding: '10px 12px',
            borderBottom: '1px solid #2a3140',
            flexShrink: 0,
            cursor: modal ? 'default' : 'grab',
            userSelect: 'none',
          }}
        >
          <span
            style={{
              fontSize: 12,
              fontWeight: 600,
              color: '#e8eaef',
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              whiteSpace: 'nowrap',
              flex: 1,
            }}
          >
            {icon ? `${icon} ` : ''}
            {title}
          </span>
          <button
            data-close
            onClick={onClose}
            style={{
              width: 28,
              height: 28,
              border: 'none',
              borderRadius: 4,
              background: '#1a2230',
              color: '#8b93a7',
              cursor: 'pointer',
              fontSize: 18,
              lineHeight: 1,
              flexShrink: 0,
            }}
          >
            ×
          </button>
        </div>

        {/* Body */}
        <div
          style={{
            margin: 0,
            padding: 12,
            overflow: 'auto',
            flex: 1,
            minHeight: 0,
          }}
        >
          {children}
        </div>
      </div>
    </div>
  );
}
