/**
 * StatusBar — React replacement for class-based StatusBarRenderer.
 * Reads from domain stores and fires callbacks via props.
 */
import { useState, useCallback, useRef, useEffect, type ChangeEvent, type KeyboardEvent } from 'react';
import { useUiStore } from '../stores/uiStore';
import { useSessionStore } from '../stores/sessionStore';
import { useAgentStore } from '../stores/agentStore';
import { useAppStore } from '../stores/appStore';
import { useVoiceRecognition } from '../hooks/useVoiceRecognition';
import { apiPostOrchestratedRun, apiPostSession, apiPostInterrupt } from '../api/chat';
import { EmotionIndicator } from './EmotionIndicator';
import type { Attachment } from '../types';

export interface StatusBarProps {
  onSend: () => Promise<void>;
  onUploadImage: (file: File) => Promise<void>;
  onUploadFile: (file: File) => Promise<void>;
  pendingAttachments?: Attachment[];
  onRemoveAttachment?: (index: number) => void;
}

export function StatusBar({ onSend, onUploadImage, onUploadFile, pendingAttachments, onRemoveAttachment }: StatusBarProps) {
  const fileImageRef = useRef<HTMLInputElement>(null);
  const fileDocRef = useRef<HTMLInputElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Store reads
  const wsConnected = useAppStore((s) => s.wsConnected);
  const heartbeatMessage = useAppStore((s) => s.heartbeatMessage);
  const heartbeatThinking = useAppStore((s) => s.heartbeatThinking);
  const smallThought = useAppStore((s) => s.smallThought);
  const input = useSessionStore((s) => s.input);
  const sending = useSessionStore((s) => s.sending);
  const activeId = useSessionStore((s) => s.activeId);
  const setSending = useSessionStore((s) => s.setSending);
  const showAgentList = useUiStore((s) => s.showAgentList);
  const showTaskManager = useUiStore((s) => s.showTaskManager);
  const showChannelManager = useUiStore((s) => s.showChannelManager);
  const showModelManager = useUiStore((s) => s.showModelManager);
  const showSkillManager = useUiStore((s) => s.showSkillManager);
  const showMemoryManager = useUiStore((s) => s.showMemoryManager);
  const showSettings = useUiStore((s) => s.showSettings);
  const selectedAgentId = useAgentStore((s) => s.selectedAgentId);

  const setInput = useSessionStore((s) => s.setInput);

  // ── Push-to-talk: 按住空格录音，松开发送 ────────────────────

  const [voiceEnabled, setVoiceEnabled] = useState(true); // 启用/禁用空格键语音
  const [recording, setRecording] = useState(false);       // 当前是否正在录音

  const {
    isRecording,
    lastResult,
    transcript,
  } = useVoiceRecognition({ recording });

  // 全局空格键：仅在 textarea 未聚焦时触发录音
  useEffect(() => {
    const handleKeyDown = (e: globalThis.KeyboardEvent) => {
      if (!voiceEnabled) return;
      if (e.key !== ' ') return;
      // 如果焦点在 textarea 中，不触发（让用户正常打字）
      if (document.activeElement === textareaRef.current) return;
      e.preventDefault();
      if (!recording) setRecording(true);
    };

    const handleKeyUp = (e: globalThis.KeyboardEvent) => {
      if (e.key !== ' ') return;
      if (recording) setRecording(false);
    };

    document.addEventListener('keydown', handleKeyDown);
    document.addEventListener('keyup', handleKeyUp);
    return () => {
      document.removeEventListener('keydown', handleKeyDown);
      document.removeEventListener('keyup', handleKeyUp);
    };
  }, [voiceEnabled, recording]);

  // ── 小心思自动消失（15 秒后清除） ────────────────────────────
  useEffect(() => {
    if (!smallThought) return;
    const timer = setTimeout(() => {
      useAppStore.getState().clearSmallThought();
    }, 15000);
    return () => clearTimeout(timer);
  }, [smallThought]);

  // ── 录音停止后自动提交结果；推理中则先中断 ──────────────────

  useEffect(() => {
    const rawText = lastResult?.replace(/\s/g, '');
    if (!rawText) return;

    // 如果当前有推理正在进行，先中断
    if (useSessionStore.getState().sending) {
      const aid = useSessionStore.getState().activeId;
      if (aid) {
        apiPostInterrupt(aid).catch(() => {});
        useSessionStore.getState().setSending(false);
      }
    }

    const chatState = useSessionStore.getState();

    // 查找 "default" agent
    const defaultAgent = useAgentStore.getState().agents.find(
      (a) => a.agentId.toLowerCase() === 'default',
    );
    if (!defaultAgent) {
      console.warn('[Voice] 未找到 default agent');
      return;
    }

    // 查找已有 session，或创建新的
    let session = chatState.sessions.find(
      (s) => s.agentId === defaultAgent.agentId,
    );

    (async () => {
      try {
        let sid = session?.id;
        if (!sid) {
          const info = await apiPostSession(defaultAgent.agentId);
          sid = info.sessionId;
          useSessionStore.getState().addSession({
            id: sid,
            agentId: defaultAgent.agentId,
            title: '',
            messages: [],
            processRows: [],
            streaming: false,
            unread: false,
          });
        }

        // 切换到 default agent 的 session
        useSessionStore.getState().setActiveId(sid);

        const voicePrefix = '\u204D';

        // 在聊天面板展示用户消息（带语音标识）
        useSessionStore.getState().appendChat(sid, {
          role: 'user',
          text: `${voicePrefix} ${rawText}`,
          timestamp: Date.now(),
          userName: voicePrefix,
        });

        // 等待 SSE 连接建立
        await new Promise((r) => setTimeout(r, 300));

        // 提交编排请求
        const result = await apiPostOrchestratedRun({
          sessionId: sid,
          text: `${voicePrefix} ${rawText}`,
        });

        if (!result.ok || !result.run_id) {
          console.error('[Voice] 编排提交失败');
          return;
        }

        // 收集回复文本和媒体 URL
        let assistantText = '';
        let mediaUrls: string[] = [];

        await new Promise<void>((resolve) => {
          const es = new EventSource(
            `/api/chat/orchestrated/stream?run_id=${encodeURIComponent(result.run_id!)}`,
          );
          es.onmessage = (e) => {
            try {
              const evt = JSON.parse(e.data) as {
                type: string;
                text?: string;
                media_urls?: string[];
                audio_url?: string;
                mp3_url?: string;
                result?: string;
              };
              if (evt.type === 'message.delta') {
                assistantText += evt.text ?? '';
              } else if (evt.type === 'message.complete') {
                if (evt.text) assistantText = evt.text;
                if (Array.isArray(evt.media_urls)) {
                  mediaUrls = evt.media_urls;
                } else if (evt.audio_url) {
                  mediaUrls = [evt.audio_url];
                } else if (evt.mp3_url) {
                  mediaUrls = [evt.mp3_url];
                }
              } else if (evt.type === 'tool.complete') {
                try {
                  if (evt.result) {
                    const parsed = JSON.parse(evt.result);
                    const filePath = parsed.file_path || parsed.audio_url || parsed.mp3_url;
                    if (filePath && typeof filePath === 'string') {
                      const audioUrl = filePath.startsWith('http')
                        ? filePath
                        : `/api/media/${encodeURIComponent(filePath)}`;
                      mediaUrls.push(audioUrl);
                    }
                  }
                } catch { /* ignore */ }
              } else if (evt.type === 'orch_done' || evt.type === 'orch_error') {
                es.close();
                resolve();
              }
            } catch { /* ignore */ }
          };
          es.onerror = () => {
            es.close();
            resolve();
          };
          setTimeout(() => {
            es.close();
            resolve();
          }, 60000);
        });

        const store = useSessionStore.getState();
        const curSession = store.sessions.find((s) => s.id === sid);
        const lastIsAssistant = curSession?.messages?.length &&
          curSession.messages[curSession.messages.length - 1].role === 'assistant';
        if (lastIsAssistant) {
          store.patchSession(sid, (session) => {
            const msgs = [...session.messages];
            const last = msgs[msgs.length - 1];
            if (last && last.role === 'assistant') {
              msgs[msgs.length - 1] = {
                ...last,
                fromVoice: true,
                ...(mediaUrls.length > 0 ? { mediaUrls } : {}),
              };
            }
            return { ...session, messages: msgs };
          });
        } else {
          store.appendChat(sid, {
            role: 'assistant',
            text: assistantText || '',
            timestamp: Date.now(),
            mediaUrls: mediaUrls.length > 0 ? mediaUrls : undefined,
            fromVoice: true,
          });
        }

        // TTS 播放
        if (mediaUrls.length > 0) {
          const audio = new Audio(mediaUrls[0]);
          audio.play().catch(() => {
            const utterance = new SpeechSynthesisUtterance(assistantText);
            utterance.lang = 'zh-CN';
            window.speechSynthesis.speak(utterance);
          });
        } else {
          const utterance = new SpeechSynthesisUtterance(assistantText);
          utterance.lang = 'zh-CN';
          window.speechSynthesis.speak(utterance);
        }
      } catch (err) {
        console.error('[Voice] 自动提交异常:', err);
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [lastResult]);

  // ── Menu button clicks ─────────────────────────────────────────

  const toggle = useCallback(
    (key: string) => {
      const s = useUiStore.getState();
      switch (key) {
        case 'agents': s.setShowAgentList(!s.showAgentList); break;
        case 'tasks': s.setShowTaskManager(!s.showTaskManager); break;
        case 'channels': s.setShowChannelManager(!s.showChannelManager); break;
        case 'models': s.setShowModelManager(!s.showModelManager); break;
        case 'skills': s.setShowSkillManager(!s.showSkillManager); break;
        case 'memory': s.setShowMemoryManager(!s.showMemoryManager); break;
        case 'settings': s.setShowSettings(!s.showSettings); break;
      }
    },
    [],
  );

  // ── Input handlers ─────────────────────────────────────────────

  const handleKeyDown = useCallback(
    (e: KeyboardEvent<HTMLTextAreaElement>) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        onSend();
      }
    },
    [onSend],
  );

  const handlePaste = useCallback(
    (e: React.ClipboardEvent) => {
      const file = e.clipboardData?.files?.[0];
      if (file?.type.startsWith('image/')) {
        e.preventDefault();
        onUploadImage(file);
      }
    },
    [onUploadImage],
  );

  const handleFileImage = useCallback(
    (e: ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0];
      if (file) onUploadImage(file);
      e.target.value = '';
    },
    [onUploadImage],
  );

  const handleFileDoc = useCallback(
    (e: ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0];
      if (file) onUploadFile(file);
      e.target.value = '';
    },
    [onUploadFile],
  );

  // ── Voice toggle: 启用/禁用空格键语音 ──────────────────────────

  const handleVoiceToggle = useCallback(() => {
    setVoiceEnabled((prev) => !prev);
    if (recording) setRecording(false);
  }, [recording]);

  // ── Stop inference ─────────────────────────────────────────────

  const handleStop = useCallback(async () => {
    if (!activeId) return;
    try {
      await apiPostInterrupt(activeId);
    } catch (err) {
      console.error('[StatusBar] 中断请求失败:', err);
    }
    setSending(false);
  }, [activeId, setSending]);

  // ── Panel helpers ──────────────────────────────────────────────

  const isPanelActive = (key: string): boolean => {
    switch (key) {
      case 'agents': return showAgentList;
      case 'tasks': return showTaskManager;
      case 'channels': return showChannelManager;
      case 'models': return showModelManager;
      case 'skills': return showSkillManager;
      case 'memory': return showMemoryManager;
      case 'settings': return showSettings;
      default: return false;
    }
  };

  const menuBtnStyle = (key: string): React.CSSProperties => ({
    background: isPanelActive(key) ? 'rgba(91,140,255,0.2)' : 'transparent',
    border: '1px solid #2a3140',
    borderRadius: 4,
    color: isPanelActive(key) ? '#5b8cff' : '#8b93a7',
    cursor: 'pointer',
    padding: '4px 10px',
    fontSize: 12,
  });

  // ── Mic button ─────────────────────────────────────────────────

  function micButtonStyle(): React.CSSProperties {
    if (isRecording) {
      return {
        background: 'rgba(229,57,53,0.25)',
        border: '1px solid rgba(229,57,53,0.5)',
        borderRadius: 4,
        color: '#e53935',
        cursor: 'pointer',
        padding: '4px 8px',
        fontSize: 13,
        flexShrink: 0,
        animation: 'pulse 1s ease-in-out infinite',
      };
    }
    if (!voiceEnabled) {
      return {
        background: 'none',
        border: '1px solid #2a3140',
        borderRadius: 4,
        color: '#8b93a7',
        cursor: 'pointer',
        padding: '4px 8px',
        fontSize: 13,
        flexShrink: 0,
        opacity: 0.5,
      };
    }
    return {
      background: 'none',
      border: '1px solid #2a3140',
      borderRadius: 4,
      color: '#8b93a7',
      cursor: 'pointer',
      padding: '4px 8px',
      fontSize: 13,
      flexShrink: 0,
    };
  }

  function micTooltip(): string {
    if (!voiceEnabled) return '点击开启空格键语音';
    if (isRecording) return '正在录音... 松开空格发送';
    return '按住空格键录音';
  }

  // ── Textarea config ────────────────────────────────────────────

  function textareaPlaceholder(): string {
    if (isRecording) return '录音中... 松开空格发送';
    if (voiceEnabled) return '输入消息，或按住空格键语音输入...';
    return '输入消息，Enter 发送，Shift+Enter 换行...';
  }

  function textareaStyle(): React.CSSProperties {
    const base: React.CSSProperties = {
      flex: 1,
      minWidth: 0,
      borderRadius: 6,
      padding: '6px 10px',
      fontSize: 13,
      fontFamily: 'inherit',
      resize: 'none',
      outline: 'none',
    };
    if (isRecording) {
      return { ...base, background: '#1a1020', color: '#d4a8ff', border: '1px solid rgba(156, 110, 255, 0.4)' };
    }
    return { ...base, background: '#0f1218', color: '#e8eaef', border: '1px solid #2a3140' };
  }

  return (
    <>
    <div style={{ display: 'flex', gap: 6, alignItems: 'center', width: '100%' }}>
      {/* Menu buttons */}
      <button style={menuBtnStyle('agents')} onClick={() => toggle('agents')}>
        🤖 Agent
      </button>
      <button style={menuBtnStyle('tasks')} onClick={() => toggle('tasks')}>
        📋 任务
      </button>
      <button style={menuBtnStyle('channels')} onClick={() => toggle('channels')}>
        📡 通道
      </button>
      <button style={menuBtnStyle('models')} onClick={() => toggle('models')}>
        🧠 模型
      </button>
      <button style={menuBtnStyle('skills')} onClick={() => toggle('skills')}>
        ⚡ 技能
      </button>
      <button style={menuBtnStyle('memory')} onClick={() => toggle('memory')}>
        📌 记忆
      </button>
      <button style={menuBtnStyle('settings')} onClick={() => toggle('settings')}>
        ⚙ 设置
      </button>

      {/* Upload buttons */}
      <input
        ref={fileImageRef}
        type="file"
        accept="image/*"
        style={{ display: 'none' }}
        onChange={handleFileImage}
      />
      <button
        onClick={() => fileImageRef.current?.click()}
        style={{
          background: 'none',
          border: '1px solid #2a3140',
          borderRadius: 4,
          color: '#8b93a7',
          cursor: 'pointer',
          padding: '4px 8px',
          fontSize: 13,
          flexShrink: 0,
        }}
        title="上传图片"
      >
        🖼
      </button>

      <input
        ref={fileDocRef}
        type="file"
        accept=".pdf,.txt,.md,.json,.html,.csv"
        style={{ display: 'none' }}
        onChange={handleFileDoc}
      />
      <button
        onClick={() => fileDocRef.current?.click()}
        style={{
          background: 'none',
          border: '1px solid #2a3140',
          borderRadius: 4,
          color: '#8b93a7',
          cursor: 'pointer',
          padding: '4px 8px',
          fontSize: 13,
          flexShrink: 0,
        }}
        title="上传文件"
      >
        📎
      </button>

      {/* Microphone button: toggle voice enabled */}
      <button
        onClick={handleVoiceToggle}
        title={micTooltip()}
        style={micButtonStyle()}
      >
        🎤
      </button>

      {/* Stop button (sending) */}
      {sending && (
        <button
          onClick={handleStop}
          style={{
            background: 'rgba(229,57,53,0.15)',
            border: '1px solid rgba(229,57,53,0.4)',
            borderRadius: 4,
            color: '#e53935',
            cursor: 'pointer',
            padding: '4px 8px',
            fontSize: 12,
            flexShrink: 0,
          }}
          title="中断推理"
        >
          ⏹
        </button>
      )}

      {/* Textarea */}
      <textarea
        ref={textareaRef}
        value={input}
        onChange={(e) => setInput(e.target.value)}
        onKeyDown={handleKeyDown}
        onPaste={handlePaste}
        rows={1}
        disabled={sending}
        placeholder={textareaPlaceholder()}
        style={textareaStyle()}
      />

      {/* Attachment previews */}
      {pendingAttachments && pendingAttachments.length > 0 && (
        <>
          {pendingAttachments.map((att, i) =>
            att.contentType?.startsWith('image/') ? (
              <span
                key={i}
                style={{
                  flexShrink: 0,
                  position: 'relative',
                  width: 28,
                  height: 28,
                  borderRadius: 4,
                  overflow: 'hidden',
                  border: '1px solid #2a3140',
                }}
                title={att.filename}
              >
                <img
                  src={att.url}
                  alt={att.filename}
                  style={{ width: '100%', height: '100%', objectFit: 'cover' }}
                />
                <span
                  onClick={() => onRemoveAttachment?.(i)}
                  style={{
                    position: 'absolute',
                    top: 0,
                    right: 0,
                    width: 12,
                    height: 12,
                    borderRadius: '0 4px 0 4px',
                    background: 'rgba(0,0,0,0.7)',
                    color: '#e53935',
                    fontSize: 9,
                    lineHeight: '12px',
                    textAlign: 'center',
                    cursor: 'pointer',
                  }}
                >
                  ✕
                </span>
              </span>
            ) : (
              <span
                key={i}
                style={{
                  flexShrink: 0,
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: 4,
                  background: 'rgba(91,140,255,0.1)',
                  border: '1px solid #2a3140',
                  borderRadius: 4,
                  padding: '2px 6px',
                  fontSize: 11,
                  color: '#8b93a7',
                  maxWidth: 120,
                  overflow: 'hidden',
                }}
                title={att.filename}
              >
                <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  📎 {att.filename}
                </span>
                <span
                  onClick={() => onRemoveAttachment?.(i)}
                  style={{ color: '#e53935', cursor: 'pointer', fontSize: 10, flexShrink: 0 }}
                >
                  ✕
                </span>
              </span>
            ),
          )}
        </>
      )}

      {/* Send button */}
      <button
        onClick={onSend}
        disabled={sending || (!input.trim() && !(pendingAttachments && pendingAttachments.length > 0))}
        style={{
          background: sending ? '#2a3140' : '#5b8cff',
          color: '#fff',
          border: 'none',
          borderRadius: 6,
          padding: '6px 16px',
          fontSize: 13,
          fontWeight: 600,
          cursor: sending || (!input.trim() && !(pendingAttachments && pendingAttachments.length > 0)) ? 'default' : 'pointer',
          whiteSpace: 'nowrap',
          flexShrink: 0,
        }}
      >
        {sending ? '…' : '发送'}
      </button>

      {/* Status dot + voice indicator */}
      <span
        style={{
          flexShrink: 0,
          fontSize: 12,
          color: '#8b93a7',
          display: 'flex',
          alignItems: 'center',
          gap: 6,
        }}
      >
        <span
          style={{
            display: 'inline-block',
            width: 6,
            height: 6,
            borderRadius: '50%',
            background: wsConnected ? '#4caf50' : '#e53935',
          }}
        />
        {isRecording && (
          <>
            <span style={{ color: '#e53935', fontSize: 11 }}>🔴 录音中</span>
            {transcript && (
              <span style={{ color: '#d4a8ff', fontSize: 11, maxWidth: 120, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {transcript}
              </span>
            )}
          </>
        )}
        {!isRecording && voiceEnabled && (
          <span style={{ color: '#5b8cff', fontSize: 11 }}>空格=语音</span>
        )}
      </span>

      {/* Heartbeat thinking stream indicator */}
      {heartbeatThinking && (
        <span
          style={{
            flexShrink: 0,
            fontSize: 11,
            color: '#a0c4ff',
            maxWidth: 280,
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            whiteSpace: 'nowrap',
            background: 'rgba(91,140,255,0.08)',
            border: '1px solid rgba(91,140,255,0.2)',
            borderRadius: 4,
            padding: '2px 8px',
          }}
        >
          <span style={{
            display: 'inline-block',
            animation: 'pulse 1.5s ease-in-out infinite',
            marginRight: 4,
          }}>
            ⚡
          </span>
          {heartbeatThinking.slice(-80)}
        </span>
      )}

      {/* Heartbeat reasoning notification */}
      {heartbeatMessage && (
        <span
          style={{
            flexShrink: 0,
            fontSize: 11,
            color: '#a0e8a0',
            maxWidth: 260,
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            whiteSpace: 'nowrap',
            background: 'rgba(76,175,80,0.08)',
            border: '1px solid rgba(76,175,80,0.2)',
            borderRadius: 4,
            padding: '2px 8px',
          }}
          title={heartbeatMessage.content}
        >
          💭 {heartbeatMessage.content.slice(0, 50)}{heartbeatMessage.content.length > 50 ? '...' : ''}
        </span>
      )}

      {/* Small thought notification */}
      {smallThought && (
        <span
          style={{
            flexShrink: 0,
            fontSize: 11,
            color: '#f0c0a0',
            maxWidth: 260,
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            whiteSpace: 'nowrap',
            background: 'rgba(240,192,160,0.08)',
            border: '1px solid rgba(240,192,160,0.2)',
            borderRadius: 4,
            padding: '2px 8px',
          }}
          title={smallThought.content}
        >
          💬 {smallThought.content.slice(0, 50)}{smallThought.content.length > 50 ? '...' : ''}
        </span>
      )}
    </div>
      <EmotionIndicator agentId={selectedAgentId} />
    </>
  );
}
