/**
 * ChatBubble — React replacement for ChatBubbleRenderer.
 * Renders a chat message bubble for user or assistant messages.
 */
import { useRef, useEffect, useMemo } from 'react';
import { escapeHtml } from '../lib/formatUtils';
import { avatarInitial, formatTime, toMediaUrl } from '../lib/formatUtils';
import { stripStudioToolLines } from '../lib/studioInlineMarkers';
import { splitReasoning } from '../lib/reasoning';
import {
  formatUserBubbleText,
} from '../lib/legacyTextFormat';
import { assistantVisibleBodyWhileStreaming } from '../lib/planArtifact';
import { PERSON_FRAME_W, PERSON_FRAME_H, getPersonSheetUrl, personFrameIndex } from '../ui/personSprites';
import type { ChatRow, AgentInfo } from '../types';

interface Props {
  message: ChatRow;
  layout: 'initiator' | 'responder';
  agents: AgentInfo[];
  /** Agent → facing direction map (for avatar animation) */
  agentFacing: Map<string, 'down' | 'up' | 'left' | 'right'>;
  onResolveAgent?: (m: ChatRow) => AgentInfo | null;
  onAgentLabel?: (agent: AgentInfo) => string;
}

export function ChatBubble({
  message: m,
  layout,
  agents,
  agentFacing,
  onResolveAgent,
  onAgentLabel,
}: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const isUser = m.role === 'user';
  const isResponder = layout === 'responder';
  const time = formatTime(m.timestamp);
  const fromVoice = !isUser && !!(m as { fromVoice?: boolean }).fromVoice;
  const metadata = !isUser ? ((m as { metadata?: Record<string, unknown> }).metadata) : undefined;
  const isBacktalk = !isUser && metadata?.backtalk === true;
  const backtalkIntensity = isBacktalk ? (Number(metadata?.intensity) || 1) : 0;
  const backtalkLabel = isBacktalk ? String(metadata?.intensityLabel || 'gentle') : '';
  const backtalkBorderColors: Record<number, string> = { 1: '#5b8cff', 2: '#f0a060', 3: '#e53935' };

  // Narrow user properties before render
  const userAttrs = isUser ? (m as Extract<ChatRow, { role: 'user' }>) : null;
  const attachments = userAttrs?.attachments;
  const userName = userAttrs?.userName ?? '';

  // Text processing
  const displayText = (): string => {
    if (isUser) return formatUserBubbleText(m.text ?? '');
    // Assistant
    const raw = stripStudioToolLines(m.text ?? '');
    if (m.streaming) {
      const v = assistantVisibleBodyWhileStreaming(raw);
      return v || '…';
    }
    const body = (m as Record<string, unknown>).bodyText as string | undefined;
    const source = body ?? raw;
    const split = splitReasoning(source);
    let text = split.text.trim() || (body ? '…' : '');
    // 过滤掉模型残留的语音已发送标记（SKILL.md 已改为输出实际文本，但模型可能仍输出旧格式）
    text = text.replace(/\*\*语音已发送\*\*\s*🎙️/g, '').trim();
    return text;
  };

  // Resolve agent (shared between name display and avatar drawing)
  const resolvedAgent = useMemo(
    () =>
      isUser
        ? null
        : (onResolveAgent?.(m) ??
            agents.find(
              (a) =>
                a.agentId === m.agentId ||
                (a.displayName || '').trim() === (m.agentName || '').trim(),
            ) ??
            null),
    [m, agents, isUser, onResolveAgent],
  );

  // Display name: resolved agent's displayName, or message agentName, or empty
  const displayName: string = isUser
    ? ''
    : (resolvedAgent?.displayName || String((m as Record<string, unknown>).agentName ?? '') || '');

  // 未配置的 agent 消息不展示
  if (!isUser && !resolvedAgent && !(m as Record<string, unknown>).agentName) {
    return null;
  }

  // Avatar animation — self-contained 3-frame animation (like AgentSpriteCanvas)
  useEffect(() => {
    if (isUser) return;
    const canvas = canvasRef.current;
    if (!canvas) return;
    const cvs: HTMLCanvasElement = canvas; // capture for closure

    const avatar = resolvedAgent?.avatar || m.agentAvatar || 'badboy';
    const base = getPersonSheetUrl(avatar);
    const dir = agentFacing.get(resolvedAgent?.agentId ?? '') ?? 'down';

    const img = new Image();
    let intervalId: number | undefined;
    let tick = 0;

    function drawFrame(col: number) {
      const ctx = cvs.getContext('2d');
      if (!ctx) return;
      ctx.imageSmoothingEnabled = false;
      ctx.clearRect(0, 0, cvs.width, cvs.height);
      const frameIdx = personFrameIndex(dir, col % 3);
      const row = Math.floor(frameIdx / 3);
      const colF = frameIdx % 3;
      // Center the 32x48 sprite vertically in the 32x32 canvas
      const yOff = (cvs.height - PERSON_FRAME_H) / 2;
      ctx.drawImage(
        img,
        colF * PERSON_FRAME_W,
        row * PERSON_FRAME_H,
        PERSON_FRAME_W,
        PERSON_FRAME_H,
        0,
        yOff,
        cvs.width,
        PERSON_FRAME_H,
      );
    }

    img.onload = () => {
      console.log('[ChatBubble] avatar loaded:', base);
      drawFrame(0);
      intervalId = window.setInterval(() => {
        tick = (tick + 1) % 3;
        drawFrame(tick);
      }, 220);
    };
    img.onerror = () => {
      console.error('[ChatBubble] avatar load failed:', base);
    };
    img.src = base;

    return () => {
      if (intervalId !== undefined) clearInterval(intervalId);
    };
  }, [resolvedAgent, m, isUser, agentFacing]);

  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: isResponder ? 'flex-start' : 'flex-end',
        marginBottom: 10,
      }}
    >
      {/* Header */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 6,
          marginBottom: 3,
          flexDirection: isResponder ? 'row' : 'row-reverse',
        }}
      >
        {/* Avatar */}
        {isUser ? (
          <div
            style={{
              width: 24,
              height: 24,
              borderRadius: '50%',
              background: '#5b8cff',
              color: '#fff',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              fontSize: 12,
              fontWeight: 600,
              flexShrink: 0,
            }}
          >
            {avatarInitial(userName)}
          </div>
        ) : (
          <canvas
            ref={canvasRef}
            width={32}
            height={32}
            style={{
              borderRadius: '50%',
              flexShrink: 0,
              imageRendering: 'pixelated',
            }}
          />
        )}

        {/* Name */}
        {userName && (
          <span style={{ fontSize: 11, color: '#8b93a7' }}>
            {userName}
          </span>
        )}
        {!isUser && (
          <span style={{ fontSize: 11, color: '#8b93a7' }}>
            {displayName}
          </span>
        )}

        {/* Time */}
        {time && <span style={{ fontSize: 10, color: '#5a6478' }}>{time}</span>}
      </div>

      {/* Bubble */}
      <div
        style={{
          maxWidth: '80%',
          background: isUser ? 'rgba(91,140,255,0.15)' : 'rgba(42,49,64,0.5)',
          border: `1px solid ${isUser ? 'rgba(91,140,255,0.3)' : '#2a3140'}`,
          borderRadius: 8,
          padding: '8px 12px',
          ...(isBacktalk ? {
            borderLeft: `3px solid ${backtalkBorderColors[backtalkIntensity] || '#f0a060'}`,
            paddingLeft: 11,
          } : {}),
        }}
      >
        {/* Backtalk label */}
        {isBacktalk && (
          <div style={{
            fontSize: 10,
            color: backtalkBorderColors[backtalkIntensity] || '#f0a060',
            marginBottom: 4,
            fontWeight: 500,
          }}>
            💢 顶嘴 ({backtalkLabel} lvl {backtalkIntensity})
          </div>
        )}
        {/* Voice playback button (only for fromVoice messages) */}
        {fromVoice && (
          <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 4 }}>
            <button
              title="播放语音"
              onClick={() => {
                const mediaUrls = (m as { mediaUrls?: string[] }).mediaUrls;
                if (mediaUrls && mediaUrls.length > 0) {
                  const audio = new Audio(mediaUrls[0]);
                  audio.play().catch(() => {
                    const fullText = m.text ?? '';
                    if (!fullText) return;
                    const utterance = new SpeechSynthesisUtterance(fullText);
                    utterance.lang = 'zh-CN';
                    window.speechSynthesis.speak(utterance);
                  });
                } else {
                  const fullText = m.text ?? '';
                  if (!fullText) return;
                  const utterance = new SpeechSynthesisUtterance(fullText);
                  utterance.lang = 'zh-CN';
                  window.speechSynthesis.speak(utterance);
                }
              }}
              style={{
                background: 'none',
                border: '1px solid rgba(91,140,255,0.3)',
                borderRadius: 4,
                color: '#5b8cff',
                cursor: 'pointer',
                fontSize: 12,
                padding: '1px 6px',
                lineHeight: 1.4,
                flexShrink: 0,
              }}
            >
              🔊 播放
            </button>
          </div>
        )}

        <div
          style={{ fontSize: 12, lineHeight: 1.55, color: '#e8eaef', whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}
          dangerouslySetInnerHTML={{ __html: escapeHtml(displayText()).replace(/\n/g, '<br>') }}
        />

        {/* Attachments */}
        {attachments?.map((att, i) =>
          att.contentType?.startsWith('image/') ? (
            <img
              key={i}
              src={toMediaUrl(att.url)}
              alt={att.filename}
              style={{ maxWidth: '100%', maxHeight: 200, borderRadius: 4, marginTop: 6 }}
            />
          ) : (
            <div
              key={i}
              style={{
                marginTop: 4,
                padding: '4px 8px',
                background: 'rgba(42,49,64,0.4)',
                borderRadius: 4,
                fontSize: 11,
                color: '#8b93a7',
              }}
            >
              📎 {att.filename}
            </div>
          ),
        )}
      </div>
    </div>
  );
}
