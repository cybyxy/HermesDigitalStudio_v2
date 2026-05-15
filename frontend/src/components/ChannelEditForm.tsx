/**
 * ChannelEditForm — React replacement for class-based ChannelEditForm.
 * Full form for creating/editing a communication channel.
 */
import { useState, useCallback } from 'react';
import type { AgentInfo } from '../types';
import * as api from '../api';

export interface ChannelFormData {
  name: string;
  platform: string;
  enabled: boolean;
  token?: string;
  apiKey?: string;
  chatId?: string;
  replyToMode?: string;
  extra?: string;
  agentId?: string;
}

interface Props {
  channelId?: string;
  initialData?: Partial<ChannelFormData>;
  agents?: AgentInfo[];
  agentOccupancy?: Record<string, string>;
  onSubmit: (data: ChannelFormData) => Promise<void>;
  onCancel: () => void;
}

const PLATFORMS = [
  'feishu', 'dingtalk', 'wecom', 'slack', 'telegram',
  'whatsapp', 'discord', 'line', 'teams', 'signal',
  'matrix', 'zulip', 'mattermost', 'email', 'custom',
];

const PLATFORM_HINTS: Record<string, string> = {
  feishu: '{"app_id":"...","app_secret":"..."}',
  dingtalk: '{"app_key":"...","app_secret":"..."}',
  wecom: '{"corp_id":"...","agent_id":"...","secret":"..."}',
  slack: '{"bot_token":"...","signing_secret":"..."}',
  telegram: '{"bot_token":"..."}',
  discord: '{"bot_token":"..."}',
  custom: '{"type":"...","endpoint":"..."}',
};

export function ChannelEditForm({
  channelId, initialData = {}, agents = [], agentOccupancy = {}, onSubmit, onCancel,
}: Props) {
  const isEdit = !!channelId;
  const [name, setName] = useState(initialData.name || '');
  const [platform, setPlatform] = useState(initialData.platform || 'feishu');
  const [enabled, setEnabled] = useState(initialData.enabled ?? true);
  const [token, setToken] = useState(initialData.token || '');
  const [apiKey, setApiKey] = useState(initialData.apiKey || '');
  const [chatId, setChatId] = useState(initialData.chatId || '');
  const [replyToMode, setReplyToMode] = useState(initialData.replyToMode || 'off');
  const [extra, setExtra] = useState(initialData.extra || '');
  const [agentId, setAgentId] = useState(initialData.agentId || '');
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const validate = useCallback((): string | null => {
    if (!name.trim()) return '名称不可为空';
    if (!platform) return '平台不可为空';
    try {
      if (extra.trim()) JSON.parse(extra);
    } catch {
      return 'extra JSON 格式错误';
    }
    if (agentId && agentOccupancy[agentId]) {
      return `Agent 已被通道「${agentOccupancy[agentId]}」占用`;
    }
    return null;
  }, [name, platform, extra, agentId, agentOccupancy]);

  const handleSubmit = useCallback(async () => {
    const err = validate();
    if (err) {
      setError(err);
      return;
    }
    setSubmitting(true);
    setError('');
    try {
      await onSubmit({
        name: name.trim(),
        platform,
        enabled,
        token: token || undefined,
        apiKey: apiKey || undefined,
        chatId: chatId || undefined,
        replyToMode,
        extra: extra.trim() || undefined,
        agentId: agentId || undefined,
      });
    } catch {
      setError('提交失败');
    } finally {
      setSubmitting(false);
    }
  }, [name, platform, enabled, token, apiKey, chatId, replyToMode, extra, agentId, validate, onSubmit]);

  const labelStyle: React.CSSProperties = { fontSize: 11, color: '#8b93a7', marginBottom: 2 };
  const inputStyle: React.CSSProperties = {
    width: '100%', background: '#0f1218', color: '#e8eaef',
    border: '1px solid #2a3140', borderRadius: 4,
    padding: '6px 8px', fontSize: 12, outline: 'none',
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
      {error && (
        <div style={{ background: 'rgba(229,57,53,0.1)', color: '#e53935', padding: '6px 10px', borderRadius: 4, fontSize: 12 }}>
          {error}
        </div>
      )}

      <div>
        <div style={labelStyle}>名称</div>
        <input style={inputStyle} value={name} onChange={(e) => setName(e.target.value)} placeholder="通道名称" />
      </div>

      <div>
        <div style={labelStyle}>平台</div>
        <select style={{ ...inputStyle, cursor: 'pointer' }} value={platform} onChange={(e) => setPlatform(e.target.value)}>
          {PLATFORMS.map((p) => (
            <option key={p} value={p}>{p}</option>
          ))}
        </select>
      </div>

      <div>
        <div style={labelStyle}>Token</div>
        <input style={inputStyle} type="password" value={token} onChange={(e) => setToken(e.target.value)} placeholder="平台 token" />
      </div>

      <div>
        <div style={labelStyle}>API Key</div>
        <input style={inputStyle} type="password" value={apiKey} onChange={(e) => setApiKey(e.target.value)} placeholder="平台 API Key" />
      </div>

      <div>
        <div style={labelStyle}>Chat ID</div>
        <input style={inputStyle} value={chatId} onChange={(e) => setChatId(e.target.value)} placeholder="聊天会话 ID" />
      </div>

      <div>
        <div style={labelStyle}>回复模式</div>
        <select style={{ ...inputStyle, cursor: 'pointer' }} value={replyToMode} onChange={(e) => setReplyToMode(e.target.value)}>
          <option value="off">关闭</option>
          <option value="first">首条回复</option>
          <option value="all">全部回复</option>
        </select>
      </div>

      <div>
        <div style={labelStyle}>绑定 Agent</div>
        <select style={{ ...inputStyle, cursor: 'pointer' }} value={agentId} onChange={(e) => setAgentId(e.target.value)}>
          <option value="">不绑定</option>
          {agents.map((a) => (
            <option key={a.agentId} value={a.agentId}>
              {a.displayName || a.agentId}
            </option>
          ))}
        </select>
      </div>

      <div>
        <div style={labelStyle}>Extra (JSON)</div>
        <textarea
          style={{ ...inputStyle, minHeight: 60, fontFamily: 'monospace', resize: 'vertical' }}
          value={extra}
          onChange={(e) => setExtra(e.target.value)}
          placeholder={PLATFORM_HINTS[platform] || '{"key":"value"}'}
        />
      </div>

      <label style={{ display: 'flex', alignItems: 'center', gap: 6, cursor: 'pointer' }}>
        <input type="checkbox" checked={enabled} onChange={(e) => setEnabled(e.target.checked)} />
        <span style={{ fontSize: 12, color: '#e8eaef' }}>启用通道</span>
      </label>

      <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end', marginTop: 4 }}>
        <button
          onClick={onCancel}
          style={{ background: 'none', border: '1px solid #2a3140', borderRadius: 4, color: '#8b93a7', cursor: 'pointer', padding: '6px 14px', fontSize: 12 }}
        >
          取消
        </button>
        <button
          onClick={handleSubmit}
          disabled={submitting}
          style={{ background: '#5b8cff', color: '#fff', border: 'none', borderRadius: 4, padding: '6px 14px', fontSize: 12, cursor: submitting ? 'default' : 'pointer', opacity: submitting ? 0.6 : 1 }}
        >
          {submitting ? '提交中...' : isEdit ? '保存修改' : '确认创建'}
        </button>
      </div>
    </div>
  );
}
