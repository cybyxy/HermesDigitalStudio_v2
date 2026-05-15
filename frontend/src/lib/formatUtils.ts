/**
 * Pure text formatting utilities.
 * Previously duplicated across UIMainScene_MessagesMixin, ChatBubbleRenderer,
 * ProcessPanelRenderer, and PlanTimelineRenderer.
 */

/** Escape HTML special characters. */
export function escapeHtml(text: string): string {
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

/** Escape HTML and replace newlines with `<br>`. */
export function renderText(text: string): string {
  return escapeHtml(text).replace(/\n/g, '<br>');
}

/** First character of a name, uppercased. Falls back to '?'. */
export function avatarInitial(name: string): string {
  return (name.trim()[0] ?? '?').toUpperCase();
}

/** Format a timestamp to HH:MM string. */
export function formatTime(ts: number | undefined): string {
  if (ts == null || !Number.isFinite(ts)) return '';
  const d = new Date(ts);
  const hh = String(d.getHours()).padStart(2, '0');
  const mm = String(d.getMinutes()).padStart(2, '0');
  return `${hh}:${mm}`;
}

/**
 * Convert a URL that may be a local filesystem path into a web-accessible
 * `/api/media/` URL. Absolute paths (starting with `/`) are URL-encoded
 * and routed through the backend media proxy. Other URLs pass through unchanged.
 */
export function toMediaUrl(rawUrl: string): string {
  if (rawUrl.startsWith('/')) {
    return `/api/media/${encodeURIComponent(rawUrl)}`;
  }
  return rawUrl;
}
