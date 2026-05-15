/**
 * React entry — replaces the old Phaser-only main.ts.
 *
 * Architecture:
 *   React owns the DOM (AppShell, panels, modals, dock)
 *   Phaser owns only the 2D office canvas (OfficeScene)
 *   Communication: bidirectional via Zustand domain stores
 */
import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { App } from './App';

const rootEl = document.getElementById('root');
if (!rootEl) throw new Error('Missing #root element');

createRoot(rootEl).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
