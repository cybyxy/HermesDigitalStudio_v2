/**
 * DockPanel — React replacement for the class-based DockPanel.
 *
 * A bottom-docked sliding panel with header, scrollable content, and optional action bar.
 */
import { useState, useEffect, useRef, type ReactNode } from 'react';

export interface DockPanelContent {
  title: string;
  content: ReactNode;
  actionBar?: ReactNode;
}

export interface DockPanelProps {
  /** Panel content (can be swapped at runtime). */
  content: DockPanelContent;
  /** Whether the panel is open. */
  open: boolean;
  /** Called when close button is clicked. */
  onClose?: () => void;
}

export function DockPanel({ content, open, onClose }: DockPanelProps) {
  const scrollRef = useRef<HTMLDivElement>(null);

  return (
    <div
      id="dock-panel"
      style={{
        position: 'absolute',
        bottom: 'var(--menu-h)',
        left: 0,
        right: 0,
        transform: open ? 'translateY(0)' : 'translateY(100%)',
        transition: 'transform 0.3s ease',
        background: 'rgba(20,24,32,0.95)',
        backdropFilter: 'blur(14px)',
        borderTop: '1px solid #2a3140',
        borderTopLeftRadius: 8,
        borderTopRightRadius: 8,
        zIndex: 100,
        height: '20vh',
        display: 'flex',
        flexDirection: 'column',
        boxShadow: '0 -4px 24px rgba(0,0,0,0.3)',
        pointerEvents: 'auto',
      }}
    >
      {/* Header */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '8px 12px',
          borderBottom: '1px solid #2a3140',
          flexShrink: 0,
        }}
      >
        <h3
          style={{
            margin: 0,
            fontSize: 13,
            fontWeight: 600,
            color: '#e8eaef',
          }}
        >
          {content.title}
        </h3>
        <button
          onClick={onClose}
          style={{
            width: 24,
            height: 24,
            border: 'none',
            borderRadius: 4,
            background: '#1a2230',
            color: '#8b93a7',
            cursor: 'pointer',
            fontSize: 16,
            lineHeight: 1,
          }}
        >
          ×
        </button>
      </div>

      {/* Action Bar (optional) */}
      {content.actionBar && (
        <div
          style={{
            padding: '4px 12px',
            borderBottom: '1px solid #2a3140',
            flexShrink: 0,
          }}
        >
          {content.actionBar}
        </div>
      )}

      {/* Scrollable content */}
      <div
        ref={scrollRef}
        style={{
          flex: 1,
          overflow: 'auto',
          minHeight: 0,
          padding: 8,
        }}
      >
        {content.content}
      </div>
    </div>
  );
}
