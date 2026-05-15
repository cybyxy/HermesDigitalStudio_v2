/**
 * ClarifyPrompt — 澄清弹窗组件。
 * 当 Agent 需要用户澄清问题时显示此模态对话框。
 */
import { useState, useCallback, useRef, useEffect, type KeyboardEvent } from 'react';
import { useApprovalFlow } from '../hooks/useApprovalFlow';
import { ModalPanel } from './ModalPanel';

export function ClarifyPrompt() {
  const { clarify, respondClarify, dismissClarify } = useApprovalFlow();
  const [answer, setAnswer] = useState('');
  const inputRef = useRef<HTMLInputElement>(null);

  // 弹窗打开时自动聚焦输入框
  useEffect(() => {
    if (clarify) {
      setAnswer('');
      setTimeout(() => inputRef.current?.focus(), 50);
    }
  }, [clarify]);

  const handleSubmit = useCallback(() => {
    const trimmed = answer.trim();
    if (!trimmed) return;
    respondClarify(trimmed);
  }, [answer, respondClarify]);

  const handleChoiceClick = useCallback(
    (choice: string) => {
      respondClarify(choice);
    },
    [respondClarify],
  );

  const handleKeyDown = useCallback(
    (e: KeyboardEvent<HTMLInputElement>) => {
      if (e.key === 'Enter') {
        e.preventDefault();
        handleSubmit();
      } else if (e.key === 'Escape') {
        dismissClarify();
      }
    },
    [handleSubmit, dismissClarify],
  );

  if (!clarify) return null;

  const choices: string[] = Array.isArray(clarify.choices) ? clarify.choices : [];

  return (
    <ModalPanel title="需要澄清" modal onClose={dismissClarify}>
      <div style={{ fontSize: 13, lineHeight: 1.7, color: '#c8ccd4' }}>
        {/* 问题 */}
        <div
          style={{
            background: 'rgba(91,140,255,0.08)',
            border: '1px solid rgba(91,140,255,0.2)',
            borderRadius: 6,
            padding: '10px 12px',
            marginBottom: 16,
            fontSize: 14,
            color: '#e8eaef',
            lineHeight: 1.6,
          }}
        >
          {clarify.question}
        </div>

        {/* 预设选项 */}
        {choices.length > 0 && (
          <div style={{ marginBottom: 14 }}>
            <div style={{ fontWeight: 600, color: '#8b93a7', marginBottom: 8, fontSize: 11, textTransform: 'uppercase', letterSpacing: '0.5px' }}>
              可选回复
            </div>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
              {choices.map((choice, i) => (
                <button
                  key={i}
                  onClick={() => handleChoiceClick(choice)}
                  style={{
                    background: 'rgba(91,140,255,0.12)',
                    border: '1px solid rgba(91,140,255,0.25)',
                    borderRadius: 6,
                    padding: '6px 14px',
                    fontSize: 12,
                    color: '#5b8cff',
                    cursor: 'pointer',
                    transition: 'background 0.15s',
                  }}
                  onMouseEnter={(e) => {
                    (e.currentTarget as HTMLButtonElement).style.background = 'rgba(91,140,255,0.22)';
                  }}
                  onMouseLeave={(e) => {
                    (e.currentTarget as HTMLButtonElement).style.background = 'rgba(91,140,255,0.12)';
                  }}
                >
                  {choice}
                </button>
              ))}
            </div>
          </div>
        )}

        {/* 自定义输入 */}
        <div style={{ marginBottom: 12 }}>
          <div style={{ fontWeight: 600, color: '#8b93a7', marginBottom: 8, fontSize: 11, textTransform: 'uppercase', letterSpacing: '0.5px' }}>
            输入回复
          </div>
          <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            <input
              ref={inputRef}
              type="text"
              value={answer}
              onChange={(e) => setAnswer(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="输入你的回复..."
              style={{
                flex: 1,
                background: '#0f1218',
                color: '#e8eaef',
                border: '1px solid #2a3140',
                borderRadius: 6,
                padding: '8px 12px',
                fontSize: 13,
                fontFamily: 'inherit',
                outline: 'none',
                transition: 'border-color 0.15s',
              }}
              onFocus={(e) => {
                e.currentTarget.style.borderColor = '#5b8cff';
              }}
              onBlur={(e) => {
                e.currentTarget.style.borderColor = '#2a3140';
              }}
            />
            <button
              onClick={handleSubmit}
              disabled={!answer.trim()}
              style={{
                background: answer.trim() ? '#5b8cff' : '#2a3140',
                color: '#fff',
                border: 'none',
                borderRadius: 6,
                padding: '8px 20px',
                fontSize: 13,
                fontWeight: 600,
                cursor: answer.trim() ? 'pointer' : 'default',
                whiteSpace: 'nowrap',
              }}
            >
              发送
            </button>
          </div>
        </div>

        {/* 操作提示 */}
        <div style={{ fontSize: 11, color: '#5a6478' }}>
          Enter 发送 · Esc 取消 · 点击上方选项快速回复
        </div>
      </div>
    </ModalPanel>
  );
}
