/**
 * Legacy text formatting utilities for user chat messages.
 * Migrated from scenes/UIMainScene_Constants.ts
 */

const LEGACY_STUDIO_PEER_USER_PREFIX =
  '【Studio 同伴回合】本条由 Hermes Digital Studio 服务器代发，' +
  '当前对话已绑定你的 Agent 会话；请在会话内直接处理下方任务，' +
  '不要向用户索取 session_id 或让其调本地 WebUI。\n\n';

const LEGACY_PEER_CTX_HEADER_LINES = new Set([
  '──────── 同伴本轮输出（@ 转交行已剥离）────────',
  '──────── 对方要你处理的任务 ────────',
]);

export function stripLegacyStudioPeerUserPrefix(text: string): string {
  if (text.startsWith(LEGACY_STUDIO_PEER_USER_PREFIX)) {
    return text.slice(LEGACY_STUDIO_PEER_USER_PREFIX.length);
  }
  return text;
}

export function stripLegacyPeerCtxHeaders(text: string): string {
  return text
    .split('\n')
    .filter((line) => !LEGACY_PEER_CTX_HEADER_LINES.has(line))
    .join('\n');
}

export function formatUserBubbleText(text: string): string {
  return stripLegacyPeerCtxHeaders(stripLegacyStudioPeerUserPrefix(text));
}
