/**
 * MemoryDetailModal — 非模态窗体，展示 Agent 完整记忆体系。
 *
 * 7 个 Tab：流水记忆 / 会话记忆 / 持久记忆 / 双重记忆 / 技能记忆 / 自我模型 / 髓鞘化
 */
import { useEffect, useState } from 'react';
import { ModalPanel } from './ModalPanel';
import {
  apiGetAgentMemory,
  apiSummarizeMemory,
  apiGetDualMemoryStats,
  apiGetKnowledgeGraph,
  apiSearchVectorMemory,
  apiGetSelfModel,
  apiGetSelfModelHistory,
  apiReflectSelfModel,
} from '../api/agents';
import {
  apiGetHistoryFromFile,
  apiResumeSession,
  apiForceDeleteSession,
  apiGetSessionFiles,
  apiGetSessionFileContent,
} from '../api/chat';
import { apiGetMyelinationStats, apiPostResetMyelination } from '../api/myelination';
import type { AgentMemoryDetail, HistoryMessage, MemorySummarizeResponse, DualMemoryStats, KnowledgeGraphData, KnowledgeGraphNode, KnowledgeGraphEdge, VectorMemorySearchResponse, SelfModelData, SelfModelReflectionEntry, SelfModelReflectResponse, MyelinationStats } from '../api/types';

interface Props {
  agentId: string;
  agentName: string;
  onClose: () => void;
}

type TabKey = 'session' | 'stateDb' | 'soul' | 'provider' | 'skills' | 'selfModel' | 'myelination';

const TABS: { key: TabKey; label: string }[] = [
  { key: 'session', label: '流水记忆' },
  { key: 'stateDb', label: '会话记忆' },
  { key: 'soul', label: '持久记忆' },
  { key: 'provider', label: '双重记忆' },
  { key: 'skills', label: '技能记忆' },
  { key: 'selfModel', label: '自我模型' },
  { key: 'myelination', label: '髓鞘化' },
];

function formatTime(ts: number): string {
  if (!ts) return '-';
  return new Date(ts * 1000).toLocaleString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  });
}

function SectionLabel({ label }: { label: string }) {
  return (
    <span style={{ color: '#5a6478', fontSize: 11, fontWeight: 500, flexShrink: 0, minWidth: 100 }}>
      {label}:
    </span>
  );
}

// ── 共享：消息列表渲染 ──────────────────────────────────────────

function MessageList({ messages }: { messages: HistoryMessage[] }) {
  if (messages.length === 0) {
    return <div style={{ color: '#5a6478', fontSize: 12, fontStyle: 'italic', textAlign: 'center', padding: 24 }}>暂无对话记录</div>;
  }
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
      {messages.map((msg, i) => {
        const isUser = msg.role === 'user';
        const hasReasoning = !isUser && (msg.reasoning || msg.reasoning_content);
        return (
          <div key={i}>
            <div
              style={{
                fontSize: 10,
                fontWeight: 600,
                color: isUser ? '#a78bfa' : '#5b8cff',
                marginBottom: 3,
              }}
            >
              {isUser ? '用户输入' : '推理结果'}
            </div>
            <div
              style={{
                fontSize: 11,
                color: '#ccd0d6',
                whiteSpace: 'pre-wrap',
                lineHeight: 1.6,
                background: isUser
                  ? 'rgba(167,139,250,0.08)'
                  : 'rgba(91,140,255,0.08)',
                border: isUser
                  ? '1px solid rgba(167,139,250,0.2)'
                  : '1px solid rgba(91,140,255,0.2)',
                borderRadius: 6,
                padding: '8px 10px',
                wordBreak: 'break-word',
              }}
            >
              {msg.text}
            </div>
            {hasReasoning && (
              <details style={{ marginTop: 4 }}>
                <summary style={{ fontSize: 10, color: '#6b7280', cursor: 'pointer' }}>
                  推理过程
                </summary>
                <div
                  style={{
                    fontSize: 10,
                    color: '#8b93a7',
                    whiteSpace: 'pre-wrap',
                    lineHeight: 1.5,
                    background: 'rgba(42,49,64,0.3)',
                    border: '1px solid #2a3140',
                    borderRadius: 4,
                    padding: '6px 8px',
                    marginTop: 4,
                    wordBreak: 'break-word',
                  }}
                >
                  {msg.reasoning || msg.reasoning_content}
                </div>
              </details>
            )}
          </div>
        );
      })}
    </div>
  );
}

// ── 流水记忆 Tab: 文件列表 + 选中查看内容 ──────────────────────────

function RenderSessionTab({ agentId }: { agentId: string }) {
  const [files, setFiles] = useState<{ name: string; size: number; mtime: number }[]>([]);
  const [filesLoading, setFilesLoading] = useState(true);
  const [filesError, setFilesError] = useState<string | null>(null);

  const [selectedFile, setSelectedFile] = useState<string | null>(null);
  const [messages, setMessages] = useState<HistoryMessage[]>([]);
  const [msgLoading, setMsgLoading] = useState(false);
  const [msgError, setMsgError] = useState<string | null>(null);

  // 加载文件列表
  useEffect(() => {
    setFilesLoading(true);
    setFilesError(null);
    apiGetSessionFiles(agentId)
      .then(setFiles)
      .catch((err) => setFilesError(err?.message || String(err)))
      .finally(() => setFilesLoading(false));
  }, [agentId]);

  // 选中文件时加载内容
  useEffect(() => {
    if (!selectedFile) {
      setMessages([]);
      return;
    }
    setMsgLoading(true);
    setMsgError(null);
    setMessages([]);
    apiGetSessionFileContent(agentId, selectedFile)
      .then((res) => {
        const all = (res.messages || []) as HistoryMessage[];
        setMessages(all.filter((m) => m.role === 'user' || m.role === 'assistant'));
        setMsgLoading(false);
      })
      .catch((err) => {
        setMsgError(err?.message || String(err));
        setMsgLoading(false);
      });
  }, [selectedFile, agentId]);

  if (filesLoading) {
    return <div style={{ color: '#6b7280', fontSize: 12, textAlign: 'center', padding: 24 }}>加载文件列表...</div>;
  }

  if (filesError) {
    return <div style={{ color: '#e53935', fontSize: 12, textAlign: 'center', padding: 24 }}>加载失败: {filesError}</div>;
  }

  if (files.length === 0) {
    return <div style={{ color: '#5a6478', fontSize: 12, fontStyle: 'italic', textAlign: 'center', padding: 32 }}>sessions 目录下暂无会话文件</div>;
  }

  return (
    <div style={{ display: 'flex', gap: 12, minHeight: 200 }}>
      {/* 左侧文件列表 */}
      <div
        style={{
          width: 220,
          flexShrink: 0,
          display: 'flex',
          flexDirection: 'column',
          gap: 4,
          maxHeight: '55vh',
          overflowY: 'auto',
        }}
      >
        <div style={{ fontSize: 11, color: '#5b8cff', fontWeight: 500, marginBottom: 4 }}>
          会话文件 ({files.length})
        </div>
        {files.map((f) => (
          <div
            key={f.name}
            onClick={() => setSelectedFile(f.name)}
            style={{
              padding: '6px 8px',
              borderRadius: 4,
              cursor: 'pointer',
              background: selectedFile === f.name ? 'rgba(91,140,255,0.18)' : 'rgba(42,49,64,0.2)',
              border: `1px solid ${selectedFile === f.name ? '#5b8cff' : '#2a3140'}`,
            }}
          >
            <div
              style={{
                fontSize: 10,
                color: selectedFile === f.name ? '#5b8cff' : '#ccd0d6',
                fontFamily: 'monospace',
                overflow: 'hidden',
                textOverflow: 'ellipsis',
                whiteSpace: 'nowrap',
                fontWeight: selectedFile === f.name ? 600 : 400,
              }}
            >
              {f.name}
            </div>
            <div style={{ fontSize: 9, color: '#6b7280', marginTop: 2 }}>
              {formatTime(f.mtime)} · {(f.size / 1024).toFixed(1)} KB
            </div>
          </div>
        ))}
      </div>

      {/* 右侧消息内容 */}
      <div
        style={{
          flex: 1,
          maxHeight: '55vh',
          overflowY: 'auto',
          minWidth: 0,
        }}
      >
        {!selectedFile ? (
          <div style={{ color: '#5a6478', fontSize: 12, fontStyle: 'italic', textAlign: 'center', padding: 32 }}>
            请从左侧选择一个会话文件查看内容
          </div>
        ) : msgLoading ? (
          <div style={{ color: '#6b7280', fontSize: 12, textAlign: 'center', padding: 24 }}>加载中...</div>
        ) : msgError ? (
          <div style={{ color: '#e53935', fontSize: 12, textAlign: 'center', padding: 24 }}>加载失败: {msgError}</div>
        ) : (
          <MessageList messages={messages} />
        )}
      </div>
    </div>
  );
}

// ── 会话记忆 Tab: Session 列表 + AI 汇总 + 内联对话内容 ───────────────

function RenderStateDbTab({
  data,
  onRefresh,
}: {
  data: AgentMemoryDetail;
  onRefresh: () => void;
}) {
  const sessions = data.sessionHistory;

  // 汇总状态
  const [summaryState, setSummaryState] = useState<{
    loading: boolean;
    error: string | null;
    data: MemorySummarizeResponse | null;
  }>({ loading: true, error: null, data: null });

  // 操作状态
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null);
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [actionMessage, setActionMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

  // 选中会话 + 对话内容加载
  const [selectedSessionId, setSelectedSessionId] = useState<string | null>(null);
  const [messages, setMessages] = useState<HistoryMessage[]>([]);
  const [msgLoading, setMsgLoading] = useState(false);
  const [msgError, setMsgError] = useState<string | null>(null);

  useEffect(() => {
    apiSummarizeMemory(data.agentId)
      .then((res) => {
        setSummaryState({ loading: false, error: null, data: res });
      })
      .catch((err) => {
        setSummaryState({ loading: false, error: err?.message || String(err), data: null });
      });
  }, [data.agentId]);

  // 选中会话时加载对话内容
  useEffect(() => {
    if (!selectedSessionId) {
      setMessages([]);
      return;
    }
    setMsgLoading(true);
    setMsgError(null);
    setMessages([]);
    apiGetHistoryFromFile(selectedSessionId)
      .then((res) => {
        const all = (res.messages || []) as HistoryMessage[];
        setMessages(all.filter((m) => m.role === 'user' || m.role === 'assistant'));
        setMsgLoading(false);
      })
      .catch((err) => {
        setMsgError(err?.message || String(err));
        setMsgLoading(false);
      });
  }, [selectedSessionId]);

  const handleResume = async (sessionId: string) => {
    setActionLoading(sessionId);
    setActionMessage(null);
    try {
      const result = await apiResumeSession(sessionId);
      const newId = result.sessionId;
      setActionMessage({ type: 'success', text: `已恢复会话: ${newId.substring(0, 12)}...` });
      setActionLoading(null);
      onRefresh();
    } catch (err: any) {
      setActionMessage({ type: 'error', text: err?.message || '恢复失败' });
      setActionLoading(null);
    }
  };

  const handleDelete = async (sessionId: string) => {
    setConfirmDeleteId(null);
    setActionLoading(sessionId);
    setActionMessage(null);
    try {
      const result = await apiForceDeleteSession(sessionId);
      if (result.deleted) {
        setActionMessage({ type: 'success', text: '会话已删除' });
        if (selectedSessionId === sessionId) {
          setSelectedSessionId(null);
        }
        onRefresh();
      } else {
        setActionMessage({ type: 'error', text: result.error || '删除失败' });
      }
      setActionLoading(null);
    } catch (err: any) {
      setActionMessage({ type: 'error', text: err?.message || '删除失败' });
      setActionLoading(null);
    }
  };

  const cardStyle: React.CSSProperties = {
    background: 'rgba(42,49,64,0.25)',
    border: '1px solid #2a3140',
    borderRadius: 6,
    padding: 8,
    display: 'flex',
    flexDirection: 'column',
    gap: 4,
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
      <div style={{ fontSize: 11, color: '#6b7280', fontStyle: 'italic', marginBottom: 4 }}>
        state.db 中存储的运行时状态
      </div>

      {/* 操作结果提示 */}
      {actionMessage && (
        <div
          style={{
            fontSize: 11,
            padding: '6px 10px',
            marginBottom: 2,
            borderRadius: 4,
            background: actionMessage.type === 'success' ? 'rgba(74,222,128,0.12)' : 'rgba(229,57,53,0.12)',
            border: `1px solid ${actionMessage.type === 'success' ? 'rgba(74,222,128,0.3)' : 'rgba(229,57,53,0.3)'}`,
            color: actionMessage.type === 'success' ? '#4ade80' : '#e53935',
          }}
        >
          {actionMessage.text}
          <button
            onClick={() => setActionMessage(null)}
            style={{
              background: 'none',
              border: 'none',
              color: 'inherit',
              cursor: 'pointer',
              fontSize: 10,
              marginLeft: 8,
              opacity: 0.6,
            }}
          >
            关闭
          </button>
        </div>
      )}

      {/* ── 会话内容总结 ── */}
      <div>
        <div style={{ fontSize: 11, color: '#5b8cff', fontWeight: 500, marginBottom: 4 }}>
          会话内容总结
        </div>
        <div style={cardStyle}>
          {summaryState.loading ? (
            <div style={{ color: '#5a6478', fontSize: 11, fontStyle: 'italic' }}>
              正在生成会话总结...
              <span
                style={{
                  display: 'inline-block',
                  width: 6,
                  height: 6,
                  borderRadius: '50%',
                  background: '#5b8cff',
                  marginLeft: 8,
                  animation: 'pulse 1.5s ease-in-out infinite',
                  verticalAlign: 'middle',
                }}
              />
            </div>
          ) : summaryState.error ? (
            <div style={{ color: '#e05566', fontSize: 11 }}>汇总失败: {summaryState.error}</div>
          ) : summaryState.data?.summarized ? (
            <div style={{ color: '#ccd0d6', fontSize: 11, lineHeight: 1.6 }}>
              {summaryState.data.summary}
            </div>
          ) : (
            <div style={{ color: '#5a6478', fontSize: 11, fontStyle: 'italic' }}>
              Agent 未运行，无法生成摘要
            </div>
          )}
        </div>
      </div>

      {/* ── Session 卡片列表 ── */}
      <div>
        <div style={{ fontSize: 11, color: '#5b8cff', fontWeight: 500, marginBottom: 4 }}>
          历史会话 ({sessions.length})
        </div>
        {sessions.length === 0 ? (
          <div style={{ color: '#5a6478', fontSize: 12, fontStyle: 'italic' }}>暂无 Session 记录</div>
        ) : (
          <div
            style={{
              display: 'flex',
              flexDirection: 'column',
              gap: 6,
              maxHeight: 300,
              overflowY: 'auto',
            }}
          >
            {sessions.map((s) => {
              const isSelected = s.sessionId === selectedSessionId;
              return (
                <div
                  key={s.sessionId}
                  style={{
                    background: isSelected
                      ? 'rgba(91,140,255,0.18)'
                      : 'rgba(42,49,64,0.25)',
                    border: `1px solid ${isSelected ? '#5b8cff' : '#2a3140'}`,
                    borderRadius: 6,
                    padding: 8,
                    opacity: actionLoading === s.sessionId ? 0.5 : 1,
                  }}
                >
                  <div
                    onClick={() => setSelectedSessionId(isSelected ? null : s.sessionId)}
                    style={{ cursor: 'pointer' }}
                  >
                    <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 4 }}>
                      <code
                        style={{
                          fontSize: 10,
                          color: isSelected ? '#5b8cff' : '#e8eaef',
                          fontFamily: 'monospace',
                          flex: 1,
                          overflow: 'hidden',
                          textOverflow: 'ellipsis',
                          whiteSpace: 'nowrap',
                        }}
                      >
                        {s.sessionKey || s.sessionId}
                      </code>
                      {s.isActive && (
                        <span
                          style={{
                            fontSize: 8,
                            background: 'rgba(91,140,255,0.25)',
                            color: '#5b8cff',
                            padding: '1px 4px',
                            borderRadius: 2,
                            fontWeight: 500,
                            flexShrink: 0,
                          }}
                        >
                          活跃
                        </span>
                      )}
                    </div>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 1, fontSize: 9, color: '#6b7280' }}>
                      <span>创建: {formatTime(s.createdAt)}</span>
                      <span>最后: {formatTime(s.lastUsedAt)}</span>
                      {s.parentSessionId && (
                        <span>父: {s.parentSessionId.slice(0, 12)}...</span>
                      )}
                    </div>
                  </div>
                  {/* 操作按钮 */}
                  <div style={{ display: 'flex', gap: 4, marginTop: 6 }}>
                    <button
                      onClick={(e) => { e.stopPropagation(); handleResume(s.sessionId); }}
                      disabled={actionLoading === s.sessionId}
                      style={{
                        flex: 1,
                        fontSize: 9,
                        padding: '3px 6px',
                        background: 'rgba(91,140,255,0.15)',
                        border: '1px solid rgba(91,140,255,0.3)',
                        borderRadius: 3,
                        color: '#5b8cff',
                        cursor: 'pointer',
                      }}
                    >
                      {actionLoading === s.sessionId ? '处理中...' : '恢复对话'}
                    </button>
                    <button
                      onClick={(e) => { e.stopPropagation(); setConfirmDeleteId(s.sessionId); }}
                      disabled={actionLoading === s.sessionId}
                      style={{
                        flex: 1,
                        fontSize: 9,
                        padding: '3px 6px',
                        background: 'rgba(229,57,53,0.1)',
                        border: '1px solid rgba(229,57,53,0.25)',
                        borderRadius: 3,
                        color: '#e53935',
                        cursor: 'pointer',
                      }}
                    >
                      删除会话
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* ── 选中会话的对话内容 ── */}
      {selectedSessionId && (
        <div>
          <div
            style={{
              fontSize: 11,
              color: '#5b8cff',
              fontWeight: 500,
              marginBottom: 6,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
            }}
          >
            <span>会话内容</span>
            <button
              onClick={() => setSelectedSessionId(null)}
              style={{
                fontSize: 9,
                color: '#8b93a7',
                background: 'none',
                border: 'none',
                cursor: 'pointer',
              }}
            >
              收起
            </button>
          </div>
          <div style={{ maxHeight: 300, overflowY: 'auto' }}>
            {msgLoading ? (
              <div style={{ color: '#6b7280', fontSize: 12, textAlign: 'center', padding: 24 }}>加载中...</div>
            ) : msgError ? (
              <div style={{ color: '#e53935', fontSize: 12, textAlign: 'center', padding: 24 }}>加载失败: {msgError}</div>
            ) : (
              <MessageList messages={messages} />
            )}
          </div>
        </div>
      )}

      {/* 删除确认对话框 */}
      {confirmDeleteId && (
        <div
          style={{
            position: 'fixed',
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            background: 'rgba(0,0,0,0.5)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 1000,
          }}
          onClick={() => setConfirmDeleteId(null)}
        >
          <div
            style={{
              background: '#1a1d24',
              border: '1px solid #2a3140',
              borderRadius: 8,
              padding: 20,
              maxWidth: 360,
              width: '90%',
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <div style={{ fontSize: 13, color: '#e8eaef', marginBottom: 8, fontWeight: 600 }}>
              确认删除会话
            </div>
            <div style={{ fontSize: 11, color: '#8b93a7', marginBottom: 12, lineHeight: 1.5 }}>
              将彻底删除该会话的以下内容：
              <ul style={{ margin: '6px 0 0 16px', padding: 0 }}>
                <li>state.db 中的消息记录</li>
                <li>sessions/ 目录下的会话文件</li>
                <li>Studio 中的会话记录</li>
              </ul>
              此操作不可撤销。
            </div>
            <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
              <button
                onClick={() => setConfirmDeleteId(null)}
                style={{
                  fontSize: 11,
                  padding: '5px 12px',
                  background: 'rgba(42,49,64,0.3)',
                  border: '1px solid #2a3140',
                  borderRadius: 4,
                  color: '#8b93a7',
                  cursor: 'pointer',
                }}
              >
                取消
              </button>
              <button
                onClick={() => handleDelete(confirmDeleteId)}
                style={{
                  fontSize: 11,
                  padding: '5px 12px',
                  background: 'rgba(229,57,53,0.2)',
                  border: '1px solid rgba(229,57,53,0.4)',
                  borderRadius: 4,
                  color: '#e53935',
                  cursor: 'pointer',
                  fontWeight: 500,
                }}
              >
                确认删除
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// ── 持久记忆 Tab: SOUL.md ──────────────────────────────────────────

function RenderSoulTab({ data }: { data: AgentMemoryDetail }) {
  const { soulMd } = data;
  const fields: { label: string; value: string }[] = [
    { label: 'Identity', value: soulMd.identity },
    { label: 'Style', value: soulMd.style },
    { label: 'Defaults', value: soulMd.defaults },
    { label: 'Avoid', value: soulMd.avoid },
    { label: 'Core Truths', value: soulMd.coreTruths },
  ];

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      <div style={{ fontSize: 11, color: '#6b7280', fontStyle: 'italic', marginBottom: 4 }}>
        SOUL.md 中的持久核心记忆
      </div>
      {fields.map((f) => (
        <div key={f.label}>
          <div style={{ fontSize: 11, color: '#5b8cff', fontWeight: 500, marginBottom: 4 }}>
            {f.label}
          </div>
          <div
            style={{
              fontSize: 11,
              color: f.value ? '#ccd0d6' : '#5a6478',
              fontStyle: f.value ? 'normal' : 'italic',
              whiteSpace: 'pre-wrap',
              lineHeight: 1.6,
              background: 'rgba(42,49,64,0.2)',
              border: '1px solid #2a3140',
              borderRadius: 6,
              padding: 8,
            }}
          >
            {f.value || '(未配置)'}
          </div>
        </div>
      ))}
    </div>
  );
}

// ── 双重记忆 Tab: 汇总统计 / 知识图谱可视化 / 历史详情 ──────────────

const TYPE_COLORS: Record<string, string> = {
  concept: '#5b8cff',
  tool: '#4ade80',
  project: '#f59e0b',
  person: '#a78bfa',
  decision: '#ef4444',
};

function DualMemoryStatsCards({
  stats,
  loading,
  error,
}: {
  stats: DualMemoryStats | null;
  loading: boolean;
  error: string | null;
}) {
  if (loading) {
    return (
      <div style={{ display: 'flex', gap: 10 }}>
        {[1, 2, 3].map((i) => (
          <div
            key={i}
            style={{
              flex: 1,
              background: 'rgba(42,49,64,0.25)',
              border: '1px solid #2a3140',
              borderRadius: 6,
              padding: 12,
              minHeight: 60,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
            }}
          >
            <div style={{ color: '#5a6478', fontSize: 11, fontStyle: 'italic' }}>加载中...</div>
          </div>
        ))}
      </div>
    );
  }

  if (error) {
    return (
      <div
        style={{
          fontSize: 11,
          color: '#e53935',
          background: 'rgba(229,57,53,0.1)',
          border: '1px solid rgba(229,57,53,0.25)',
          borderRadius: 6,
          padding: '8px 12px',
        }}
      >
        统计加载失败: {error}
      </div>
    );
  }

  if (!stats) return null;

  const cards = [
    {
      title: '向量记忆',
      icon: '🧠',
      lines: [
        { label: '记忆条目', value: stats.vectorMemory.count, color: stats.vectorMemory.count > 0 ? '#4ade80' : '#6b7280' },
        { label: '状态', value: stats.vectorMemory.status === 'active' ? '已就绪' : stats.vectorMemory.status === 'empty' ? '无数据' : '不可用', color: stats.vectorMemory.status === 'active' ? '#4ade80' : '#e53935' },
      ],
    },
    {
      title: '知识图谱',
      icon: '🔗',
      lines: [
        { label: '节点', value: stats.knowledgeGraph.nodeCount, color: stats.knowledgeGraph.nodeCount > 0 ? '#a78bfa' : '#6b7280' },
        { label: '边', value: stats.knowledgeGraph.edgeCount, color: stats.knowledgeGraph.edgeCount > 0 ? '#a78bfa' : '#6b7280' },
      ],
    },
    {
      title: '会话日志',
      icon: '📝',
      lines: [
        { label: 'Session 文件', value: stats.sessions.sessionFileCount, color: stats.sessions.sessionFileCount > 0 ? '#4ade80' : '#6b7280' },
        { label: '活动会话', value: stats.sessions.activeSessionCount, color: stats.sessions.activeSessionCount > 0 ? '#f59e0b' : '#6b7280' },
      ],
    },
  ];

  return (
    <div style={{ display: 'flex', gap: 10 }}>
      {cards.map((card) => (
        <div
          key={card.title}
          style={{
            flex: 1,
            background: 'rgba(42,49,64,0.25)',
            border: '1px solid #2a3140',
            borderRadius: 6,
            padding: 12,
          }}
        >
          <div style={{ fontSize: 12, color: '#e8eaef', fontWeight: 600, marginBottom: 8, display: 'flex', alignItems: 'center', gap: 4 }}>
            <span>{card.icon}</span>
            <span>{card.title}</span>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
            {card.lines.map((line) => (
              <div key={line.label} style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11 }}>
                <span style={{ color: '#8b93a7' }}>{line.label}</span>
                <span style={{ color: line.color, fontWeight: 500 }}>{line.value}</span>
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

function KnowledgeGraphSection({ agentId }: { agentId: string }) {
  const [graphData, setGraphData] = useState<KnowledgeGraphData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState(false);

  useEffect(() => {
    if (!expanded) return;
    setLoading(true);
    setError(null);
    apiGetKnowledgeGraph(agentId)
      .then(setGraphData)
      .catch((err) => setError(err?.message || String(err)))
      .finally(() => setLoading(false));
  }, [agentId, expanded]);

  const hasData = graphData && graphData.nodeCount > 0;

  return (
    <div>
      <div
        onClick={() => setExpanded(!expanded)}
        style={{
          fontSize: 12,
          color: '#5b8cff',
          fontWeight: 500,
          cursor: 'pointer',
          display: 'flex',
          alignItems: 'center',
          gap: 6,
          padding: '4px 0',
          userSelect: 'none',
        }}
      >
        <span style={{ fontSize: 10 }}>{expanded ? '▼' : '▶'}</span>
        <span>知识图谱可视化</span>
        {graphData && (
          <span style={{ fontSize: 10, color: '#6b7280', fontWeight: 400 }}>
            ({graphData.nodeCount} 节点 / {graphData.edgeCount} 边)
          </span>
        )}
      </div>

      {expanded && (
        <div style={{ marginTop: 8 }}>
          {loading ? (
            <div style={{ color: '#6b7280', fontSize: 11, fontStyle: 'italic', padding: 12, textAlign: 'center' }}>
              加载知识图谱...
            </div>
          ) : error ? (
            <div style={{ color: '#e53935', fontSize: 11, padding: 8 }}>
              加载失败: {error}
            </div>
          ) : !hasData ? (
            <div
              style={{
                color: '#5a6478',
                fontSize: 11,
                fontStyle: 'italic',
                textAlign: 'center',
                padding: 24,
                background: 'rgba(42,49,64,0.15)',
                border: '1px dashed #2a3140',
                borderRadius: 6,
              }}
            >
              暂无知识图谱数据
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              {/* 节点按 type 分组展示 */}
              <div>
                <div style={{ fontSize: 11, color: '#8b93a7', marginBottom: 6 }}>节点 ({graphData.nodeCount})</div>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                  {(() => {
                    const groups = new Map<string, KnowledgeGraphNode[]>();
                    for (const n of graphData.nodes) {
                      const t = n.type || '其他';
                      if (!groups.has(t)) groups.set(t, []);
                      groups.get(t)!.push(n);
                    }
                    return [...groups.entries()].map(([type, nodes]) => (
                      <div
                        key={type}
                        style={{
                          flex: '1 1 180px',
                          background: 'rgba(42,49,64,0.2)',
                          border: `1px solid #2a3140`,
                          borderRadius: 6,
                          padding: 8,
                        }}
                      >
                        <div style={{ fontSize: 10, color: TYPE_COLORS[type] || '#8b93a7', fontWeight: 600, marginBottom: 4, textTransform: 'uppercase' }}>
                          {type} ({nodes.length})
                        </div>
                        <div style={{ display: 'flex', flexDirection: 'column', gap: 2, maxHeight: 120, overflowY: 'auto' }}>
                          {nodes.map((n) => (
                            <div
                              key={n.id}
                              style={{
                                fontSize: 10,
                                color: '#ccd0d6',
                                background: 'rgba(0,0,0,0.15)',
                                borderRadius: 3,
                                padding: '3px 6px',
                                borderLeft: `2px solid ${TYPE_COLORS[type] || '#5a6478'}`,
                              }}
                              title={n.summary || n.label}
                            >
                              {n.label}
                            </div>
                          ))}
                        </div>
                      </div>
                    ));
                  })()}
                </div>
              </div>

              {/* 边列表 */}
              {graphData.edges.length > 0 && (
                <div>
                  <div style={{ fontSize: 11, color: '#8b93a7', marginBottom: 6 }}>关系边 ({graphData.edgeCount})</div>
                  <div
                    style={{
                      background: 'rgba(42,49,64,0.2)',
                      border: '1px solid #2a3140',
                      borderRadius: 6,
                      padding: 8,
                      maxHeight: 150,
                      overflowY: 'auto',
                    }}
                  >
                    {graphData.edges.slice(0, 30).map((e) => (
                      <div
                        key={e.id}
                        style={{
                          fontSize: 10,
                          color: '#8b93a7',
                          padding: '3px 0',
                          borderBottom: '1px solid rgba(42,49,64,0.3)',
                          display: 'flex',
                          gap: 4,
                        }}
                      >
                        <span style={{ color: '#ccd0d6' }}>{e.source_label}</span>
                        <span style={{ color: '#f59e0b' }}>─[{e.relation}]→</span>
                        <span style={{ color: '#ccd0d6' }}>{e.target_label}</span>
                      </div>
                    ))}
                    {graphData.edges.length > 30 && (
                      <div style={{ fontSize: 9, color: '#6b7280', textAlign: 'center', padding: 4, fontStyle: 'italic' }}>
                        仅显示前 30 条，共 {graphData.edgeCount} 条
                      </div>
                    )}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function MemoryHistorySection({
  agentId,
  stats,
  graphData,
}: {
  agentId: string;
  stats: DualMemoryStats | null;
  graphData: KnowledgeGraphData | null;
}) {
  const [vectorMemories, setVectorMemories] = useState<VectorMemorySearchResponse | null>(null);
  const [vmLoading, setVmLoading] = useState(false);
  const [vmError, setVmError] = useState<string | null>(null);

  const handleOpenVectorMemories = () => {
    if (vectorMemories || vmLoading) return;
    setVmLoading(true);
    setVmError(null);
    apiSearchVectorMemory(agentId, '', 20)
      .then(setVectorMemories)
      .catch((err) => setVmError(err?.message || String(err)))
      .finally(() => setVmLoading(false));
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
      <div style={{ fontSize: 11, color: '#8b93a7', marginBottom: 2 }}>历史详情</div>

      {/* Panel 1: 向量记忆条目 */}
      <details style={{ fontSize: 11 }} onToggle={(e) => { if ((e.target as HTMLDetailsElement).open) handleOpenVectorMemories(); }}>
        <summary style={{ color: '#5b8cff', cursor: 'pointer', fontWeight: 500, padding: '4px 0' }}>
          向量记忆条目 {vectorMemories ? `(${vectorMemories.count})` : ''}
        </summary>
        <div style={{ marginTop: 6 }}>
          {vmLoading ? (
            <div style={{ color: '#6b7280', fontStyle: 'italic', textAlign: 'center', padding: 12 }}>加载中...</div>
          ) : vmError ? (
            <div style={{ color: '#e53935' }}>加载失败: {vmError}</div>
          ) : vectorMemories && vectorMemories.results.length > 0 ? (
            <div
              style={{
                background: 'rgba(42,49,64,0.2)',
                border: '1px solid #2a3140',
                borderRadius: 6,
                padding: 8,
                maxHeight: 200,
                overflowY: 'auto',
                display: 'flex',
                flexDirection: 'column',
                gap: 6,
              }}
            >
              {vectorMemories.results.map((mem, i) => (
                <div
                  key={i}
                  style={{
                    fontSize: 10,
                    color: '#ccd0d6',
                    lineHeight: 1.5,
                    background: 'rgba(0,0,0,0.1)',
                    borderRadius: 4,
                    padding: '6px 8px',
                    border: '1px solid rgba(42,49,64,0.3)',
                    wordBreak: 'break-word',
                  }}
                >
                  {mem.length > 200 ? mem.slice(0, 200) + '...' : mem}
                </div>
              ))}
            </div>
          ) : (
            <div style={{ color: '#5a6478', fontStyle: 'italic' }}>暂无向量记忆数据</div>
          )}
        </div>
      </details>

      {/* Panel 2: 知识图谱节点 */}
      <details style={{ fontSize: 11 }}>
        <summary style={{ color: '#5b8cff', cursor: 'pointer', fontWeight: 500, padding: '4px 0' }}>
          知识图谱节点 {graphData ? `(${graphData.nodeCount} 节点 / ${graphData.edgeCount} 边)` : ''}
        </summary>
        <div style={{ marginTop: 6 }}>
          {graphData && graphData.nodeCount > 0 ? (
            <div
              style={{
                background: 'rgba(42,49,64,0.2)',
                border: '1px solid #2a3140',
                borderRadius: 6,
                padding: 8,
                maxHeight: 200,
                overflowY: 'auto',
              }}
            >
              {graphData.nodes.map((n) => (
                <div
                  key={n.id}
                  style={{
                    fontSize: 10,
                    color: '#ccd0d6',
                    padding: '4px 6px',
                    borderBottom: '1px solid rgba(42,49,64,0.3)',
                    display: 'flex',
                    gap: 6,
                  }}
                >
                  <span
                    style={{
                      color: TYPE_COLORS[n.type] || '#8b93a7',
                      fontWeight: 500,
                      flexShrink: 0,
                    }}
                  >
                    [{n.type}]
                  </span>
                  <span style={{ flex: 1 }}>{n.label}</span>
                  {n.summary && <span style={{ color: '#6b7280', maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{n.summary}</span>}
                </div>
              ))}
            </div>
          ) : (
            <div style={{ color: '#5a6478', fontStyle: 'italic' }}>暂无知识图谱数据</div>
          )}
        </div>
      </details>

      {/* Panel 3: 会话日志文件 */}
      <details style={{ fontSize: 11 }}>
        <summary style={{ color: '#5b8cff', cursor: 'pointer', fontWeight: 500, padding: '4px 0' }}>
          会话日志文件
        </summary>
        <div style={{ marginTop: 6 }}>
          <div
            style={{
              background: 'rgba(42,49,64,0.2)',
              border: '1px solid #2a3140',
              borderRadius: 6,
              padding: 8,
              display: 'flex',
              flexDirection: 'column',
              gap: 6,
            }}
          >
            <div style={{ display: 'flex', gap: 8, fontSize: 11 }}>
              <span style={{ color: '#8b93a7', flexShrink: 0, minWidth: 90 }}>Session 文件:</span>
              <span style={{ color: '#ccd0d6', fontWeight: 500 }}>{stats?.sessions.sessionFileCount ?? '-'} 个</span>
            </div>
            <div style={{ display: 'flex', gap: 8, fontSize: 11 }}>
              <span style={{ color: '#8b93a7', flexShrink: 0, minWidth: 90 }}>活动会话:</span>
              <span style={{ color: '#ccd0d6', fontWeight: 500 }}>{stats?.sessions.activeSessionCount ?? '-'} 个</span>
            </div>
          </div>
        </div>
      </details>
    </div>
  );
}

function RenderDualMemoryTab({ agentId }: { agentId: string }) {
  const [stats, setStats] = useState<DualMemoryStats | null>(null);
  const [statsLoading, setStatsLoading] = useState(true);
  const [statsError, setStatsError] = useState<string | null>(null);

  useEffect(() => {
    setStatsLoading(true);
    setStatsError(null);
    apiGetDualMemoryStats(agentId)
      .then(setStats)
      .catch((err) => setStatsError(err?.message || String(err)))
      .finally(() => setStatsLoading(false));
  }, [agentId]);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
      <div style={{ fontSize: 11, color: '#6b7280', fontStyle: 'italic', marginBottom: 2 }}>
        双重记忆 — 向量记忆 / 知识图谱 / 会话日志
      </div>

      {/* Section 1: 汇总统计 */}
      <DualMemoryStatsCards stats={stats} loading={statsLoading} error={statsError} />

      {/* Section 2: 知识图谱可视化（懒加载） */}
      <KnowledgeGraphSection agentId={agentId} />

      {/* Section 3: 历史详情 */}
      <MemoryHistorySectionWrapper agentId={agentId} stats={stats} />
    </div>
  );
}

/** 包装器：共享 graphData 状态给 MemoryHistorySection */
function MemoryHistorySectionWrapper({ agentId, stats }: { agentId: string; stats: DualMemoryStats | null }) {
  const [graphData, setGraphData] = useState<KnowledgeGraphData | null>(null);

  useEffect(() => {
    apiGetKnowledgeGraph(agentId)
      .then(setGraphData)
      .catch(() => { /* silently ignore, and let MemoryHistorySection handle it */ });
  }, [agentId]);

  return <MemoryHistorySection agentId={agentId} stats={stats} graphData={graphData} />;
}

// ── 技能记忆 Tab ────────────────────────────────────────────────────

function RenderSkillsTab({ data }: { data: AgentMemoryDetail }) {
  const { skills } = data;

  if (skills.length === 0) {
    return (
      <div style={{ color: '#5a6478', fontSize: 12, fontStyle: 'italic', textAlign: 'center', padding: 32 }}>
        该 Agent 暂无配置技能记忆
      </div>
    );
  }

  // 按 category 分组
  const groups = new Map<string, typeof skills>();
  for (const sk of skills) {
    const cat = sk.category || '其他';
    if (!groups.has(cat)) groups.set(cat, []);
    groups.get(cat)!.push(sk);
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
      <div style={{ fontSize: 11, color: '#6b7280', fontStyle: 'italic', marginBottom: 4 }}>
        Agent 所配置的技能（来自 hermes_home/skills/ 目录）
      </div>
      {[...groups.entries()].map(([category, skillList]) => (
        <details key={category} open>
          <summary style={{ fontSize: 12, color: '#5b8cff', fontWeight: 500, cursor: 'pointer', marginBottom: 6 }}>
            {category} ({skillList.length})
          </summary>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6, marginTop: 4 }}>
            {skillList.map((sk) => (
              <div
                key={sk.id}
                style={{
                  background: 'rgba(42,49,64,0.25)',
                  border: '1px solid #2a3140',
                  borderRadius: 6,
                  padding: 10,
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 4 }}>
                  <span style={{ fontSize: 12, color: '#e8eaef', fontWeight: 500 }}>
                    {sk.name}
                  </span>
                  {sk.version && (
                    <span style={{ fontSize: 9, color: '#5a6478', background: 'rgba(42,49,64,0.5)', padding: '1px 4px', borderRadius: 2 }}>
                      v{sk.version}
                    </span>
                  )}
                </div>
                {sk.description && (
                  <div style={{ fontSize: 10, color: '#8b93a7', marginBottom: 4, lineHeight: 1.5 }}>
                    {sk.description}
                  </div>
                )}
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4, fontSize: 9, color: '#6b7280' }}>
                  {sk.author && <span>作者: {sk.author}</span>}
                  {sk.license && <span>· {sk.license}</span>}
                  {sk.commands.length > 0 && <span>· 命令: {sk.commands.join(', ')}</span>}
                  {sk.tags.length > 0 && <span>· 标签: {sk.tags.join(', ')}</span>}
                </div>
                {sk.platforms.length > 0 && (
                  <div style={{ fontSize: 9, color: '#6b7280', marginTop: 2 }}>
                    平台: {sk.platforms.join(', ')}
                  </div>
                )}
              </div>
            ))}
          </div>
        </details>
      ))}
    </div>
  );
}

// ── 自我模型 Tab ──────────────────────────────────────────────────────

function RenderSelfModelTab({ agentId }: { agentId: string }) {
  const [modelData, setModelData] = useState<SelfModelData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [reflectResult, setReflectResult] = useState<SelfModelReflectResponse | null>(null);
  const [reflectLoading, setReflectLoading] = useState(false);

  const fetchData = () => {
    setLoading(true);
    setError(null);
    Promise.all([
      apiGetSelfModel(agentId),
      apiGetSelfModelHistory(agentId),
    ])
      .then(([model, historyRes]) => {
        setModelData({
          ...model,
          reflection_history: historyRes.history,
        });
        setLoading(false);
      })
      .catch((err) => {
        setError(err?.message || String(err));
        setLoading(false);
      });
  };

  useEffect(() => {
    fetchData();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [agentId]);

  if (loading) {
    return <div style={{ color: '#6b7280', fontSize: 12, textAlign: 'center', padding: 24 }}>加载自我模型...</div>;
  }

  if (error) {
    return <div style={{ color: '#e53935', fontSize: 12, textAlign: 'center', padding: 24 }}>加载失败: {error}</div>;
  }

  if (!modelData) {
    return <div style={{ color: '#6b7280', fontSize: 12, textAlign: 'center', padding: 24 }}>无数据</div>;
  }

  const fields: { label: string; key: keyof SelfModelData; desc: string }[] = [
    { label: '偏好', key: 'preferences', desc: '从对话中学习的偏好' },
    { label: '能力自知', key: 'capabilities', desc: '自我认知的能力边界' },
    { label: '行为模式', key: 'behavioral_patterns', desc: '观察到的行为习惯' },
    { label: '衍生特质', key: 'derived_traits', desc: '逐渐形成的特质' },
  ];

  const handleTriggerReflect = async () => {
    setReflectLoading(true);
    setReflectResult(null);
    try {
      const result = await apiReflectSelfModel(agentId);
      setReflectResult(result);
      fetchData();
    } catch (err: any) {
      setReflectResult({ triggered: false, message: err?.message || '触发反思失败' });
    } finally {
      setReflectLoading(false);
    }
  };

  const formatTimeDetailed = (ts: number) => {
    if (!ts) return '-';
    return new Date(ts * 1000).toLocaleString('zh-CN', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      <div style={{ fontSize: 11, color: '#6b7280', fontStyle: 'italic', marginBottom: 4 }}>
        Agent 的自我认知模型，通过反思对话自动更新
      </div>

      {/* 手动反思按钮 */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <button
          onClick={handleTriggerReflect}
          disabled={reflectLoading}
          style={{
            fontSize: 11,
            padding: '5px 12px',
            background: reflectLoading ? 'rgba(91,140,255,0.08)' : 'rgba(91,140,255,0.15)',
            border: '1px solid rgba(91,140,255,0.3)',
            borderRadius: 4,
            color: reflectLoading ? '#6b7280' : '#5b8cff',
            cursor: reflectLoading ? 'not-allowed' : 'pointer',
          }}
        >
          {reflectLoading ? '反思进行中...' : '手动触发反思'}
        </button>
        {reflectResult && (
          <span
            style={{
              fontSize: 10,
              color: reflectResult.triggered ? '#4ade80' : '#e53935',
            }}
          >
            {reflectResult.message}
          </span>
        )}
      </div>

      {/* 字段卡片 */}
      {fields.map((f) => {
        const value = modelData[f.key];
        const displayValue = typeof value === 'string' && value.trim() ? value.trim() : '';
        return (
          <div key={f.key}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 4 }}>
              <span style={{ fontSize: 11, color: '#5b8cff', fontWeight: 500 }}>{f.label}</span>
              <span style={{ fontSize: 9, color: '#6b7280' }}>{f.desc}</span>
            </div>
            <div
              style={{
                fontSize: 11,
                color: displayValue ? '#ccd0d6' : '#5a6478',
                fontStyle: displayValue ? 'normal' : 'italic',
                whiteSpace: 'pre-wrap',
                lineHeight: 1.6,
                background: 'rgba(42,49,64,0.2)',
                border: '1px solid #2a3140',
                borderRadius: 6,
                padding: 8,
                maxHeight: 200,
                overflowY: 'auto',
              }}
            >
              {displayValue || '(暂无)'}
            </div>
          </div>
        );
      })}

      {/* 反思历史 */}
      <div>
        <div style={{ fontSize: 11, color: '#5b8cff', fontWeight: 500, marginBottom: 6 }}>
          反思历史 ({modelData.reflection_history?.length || 0})
        </div>
        {modelData.reflection_history && modelData.reflection_history.length > 0 ? (
          <div
            style={{
              display: 'flex',
              flexDirection: 'column',
              gap: 6,
              maxHeight: 250,
              overflowY: 'auto',
            }}
          >
            {[...modelData.reflection_history].reverse().map((entry, i) => {
              const confidenceColors: Record<string, string> = {
                high: '#4ade80',
                medium: '#f59e0b',
                low: '#6b7280',
              };
              return (
                <div
                  key={i}
                  style={{
                    background: 'rgba(42,49,64,0.25)',
                    border: '1px solid #2a3140',
                    borderRadius: 6,
                    padding: 8,
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 4 }}>
                    <span style={{ fontSize: 9, color: '#6b7280' }}>
                      {formatTimeDetailed(entry.timestamp)}
                    </span>
                    <span
                      style={{
                        fontSize: 9,
                        padding: '1px 4px',
                        borderRadius: 2,
                        background: `${confidenceColors[entry.confidence] || '#6b7280'}22`,
                        color: confidenceColors[entry.confidence] || '#6b7280',
                        fontWeight: 500,
                      }}
                    >
                      {entry.confidence === 'high' ? '高置信' : entry.confidence === 'medium' ? '中置信' : '低置信'}
                    </span>
                  </div>
                  <div style={{ fontSize: 11, color: '#ccd0d6', lineHeight: 1.5, whiteSpace: 'pre-wrap' }}>
                    {entry.lesson}
                  </div>
                </div>
              );
            })}
          </div>
        ) : (
          <div style={{ color: '#5a6478', fontSize: 11, fontStyle: 'italic', textAlign: 'center', padding: 16, background: 'rgba(42,49,64,0.15)', border: '1px dashed #2a3140', borderRadius: 6 }}>
            暂无反思记录。点击"手动触发反思"让 Agent 回顾近期对话。
          </div>
        )}
      </div>
    </div>
  );
}

// ── 髓鞘化 Tab ───────────────────────────────────────────────────────

const STAGE_LABELS: Record<string, string> = {
  novel: '新接触',
  learning: '学习中',
  consolidating: '巩固中',
  instinct: '本能化',
};

const STAGE_COLORS: Record<string, string> = {
  novel: '#6b7280',
  learning: '#f59e0b',
  consolidating: '#3b82f6',
  instinct: '#10b981',
};

function RenderMyelinationTab({ agentId }: { agentId: string }) {
  const [stats, setStats] = useState<MyelinationStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [resetting, setResetting] = useState(false);

  const fetchStats = () => {
    setLoading(true);
    setError(null);
    apiGetMyelinationStats(agentId)
      .then(setStats)
      .catch((err) => setError(err?.message || String(err)))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    fetchStats();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [agentId]);

  const handleReset = () => {
    if (!window.confirm('确定要清除该 Agent 的所有髓鞘化路径吗？此操作不可撤销。')) return;
    setResetting(true);
    apiPostResetMyelination(agentId)
      .then(() => fetchStats())
      .catch((err) => alert(`重置失败: ${err?.message || String(err)}`))
      .finally(() => setResetting(false));
  };

  if (loading) {
    return <div style={{ color: '#6b7280', fontSize: 12, textAlign: 'center', padding: 24 }}>加载中...</div>;
  }
  if (error) {
    return <div style={{ color: '#e53935', fontSize: 12, textAlign: 'center', padding: 24 }}>加载失败: {error}</div>;
  }
  if (!stats) {
    return <div style={{ color: '#6b7280', fontSize: 12, textAlign: 'center', padding: 24 }}>无数据</div>;
  }

  const stages = ['novel', 'learning', 'consolidating', 'instinct'] as const;
  const maxCount = Math.max(...stages.map((s) => stats.by_stage[s]), 1);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
      <div style={{ fontSize: 11, color: '#6b7280', fontStyle: 'italic', marginBottom: 2 }}>
        髓鞘化 — 知识路径三阶段固化为本能反应
      </div>

      {/* 路径阶段分布 */}
      <div style={{ background: '#1a1d27', borderRadius: 8, padding: 14 }}>
        <div style={{ fontSize: 12, fontWeight: 600, color: '#cbd5e1', marginBottom: 10 }}>
          知识路径阶段分布
        </div>
        {stages.map((stage) => {
          const count = stats.by_stage[stage];
          const pct = maxCount > 0 ? Math.round((count / maxCount) * 100) : 0;
          return (
            <div key={stage} style={{ marginBottom: 8 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11, marginBottom: 2 }}>
                <span style={{ color: STAGE_COLORS[stage] }}>{STAGE_LABELS[stage]}</span>
                <span style={{ color: '#8b93a7' }}>{count}</span>
              </div>
              <div style={{ height: 6, background: '#24293a', borderRadius: 3, overflow: 'hidden' }}>
                <div style={{ height: '100%', width: `${pct}%`, background: STAGE_COLORS[stage], borderRadius: 3, transition: 'width 0.3s' }} />
              </div>
            </div>
          );
        })}
      </div>

      {/* 汇总统计 */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 8 }}>
        <div style={{ background: '#1a1d27', borderRadius: 8, padding: 12, textAlign: 'center' }}>
          <div style={{ fontSize: 20, fontWeight: 700, color: '#5b8cff' }}>{stats.total_paths}</div>
          <div style={{ fontSize: 10, color: '#8b93a7', marginTop: 4 }}>路径总数</div>
        </div>
        <div style={{ background: '#1a1d27', borderRadius: 8, padding: 12, textAlign: 'center' }}>
          <div style={{ fontSize: 20, fontWeight: 700, color: '#10b981' }}>{stats.llm_calls_saved}</div>
          <div style={{ fontSize: 10, color: '#8b93a7', marginTop: 4 }}>节省调用</div>
        </div>
        <div style={{ background: '#1a1d27', borderRadius: 8, padding: 12, textAlign: 'center' }}>
          <div style={{ fontSize: 20, fontWeight: 700, color: '#f59e0b' }}>{stats.tokens_saved.toLocaleString()}</div>
          <div style={{ fontSize: 10, color: '#8b93a7', marginTop: 4 }}>节省 Token</div>
        </div>
      </div>

      {/* 重置按钮 */}
      <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
        <button
          onClick={handleReset}
          disabled={resetting || stats.total_paths === 0}
          style={{
            padding: '6px 14px',
            background: stats.total_paths === 0 ? '#24293a' : '#e53935',
            color: '#fff',
            border: 'none',
            borderRadius: 4,
            fontSize: 11,
            cursor: stats.total_paths === 0 ? 'not-allowed' : 'pointer',
            opacity: stats.total_paths === 0 ? 0.4 : 1,
          }}
        >
          {resetting ? '重置中...' : '清除髓鞘化缓存'}
        </button>
      </div>
    </div>
  );
}

// ── Main Component ─────────────────────────────────────────────────────

export function MemoryDetailModal({ agentId, agentName, onClose }: Props) {
  const [activeTab, setActiveTab] = useState<TabKey>('session');
  const [data, setData] = useState<AgentMemoryDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchData = () => {
    setLoading(true);
    setError(null);
    apiGetAgentMemory(agentId)
      .then((res) => {
        setData(res);
        setLoading(false);
      })
      .catch((err) => {
        setError(err?.message || String(err));
        setLoading(false);
      });
  };

  useEffect(() => {
    fetchData();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [agentId]);

  const renderTabContent = () => {
    if (loading) {
      return <div style={{ color: '#6b7280', fontSize: 12, textAlign: 'center', padding: 24 }}>加载中...</div>;
    }
    if (error) {
      return <div style={{ color: '#e53935', fontSize: 12, textAlign: 'center', padding: 24 }}>加载失败: {error}</div>;
    }
    if (!data) {
      return <div style={{ color: '#6b7280', fontSize: 12, textAlign: 'center', padding: 24 }}>无数据</div>;
    }

    switch (activeTab) {
      case 'session':
        return <RenderSessionTab agentId={agentId} />;
      case 'stateDb':
        return <RenderStateDbTab data={data} onRefresh={fetchData} />;
      case 'soul':
        return <RenderSoulTab data={data} />;
      case 'provider':
        return <RenderDualMemoryTab agentId={agentId} />;
      case 'skills':
        return <RenderSkillsTab data={data} />;
      case 'selfModel':
        return <RenderSelfModelTab agentId={agentId} />;
      case 'myelination':
        return <RenderMyelinationTab agentId={agentId} />;
    }
  };

  return (
    <ModalPanel
      title={`${agentName} - 记忆体系`}
      maxWidth="56rem"
      onClose={onClose}
    >
      {/* Tab bar */}
      <div
        style={{
          display: 'flex',
          gap: 2,
          marginBottom: 12,
          borderBottom: '1px solid #2a3140',
          paddingBottom: 0,
        }}
      >
        {TABS.map((tab) => (
          <button
            key={tab.key}
            onClick={() => setActiveTab(tab.key)}
            style={{
              background: activeTab === tab.key ? 'rgba(91,140,255,0.18)' : 'transparent',
              color: activeTab === tab.key ? '#5b8cff' : '#8b93a7',
              border: 'none',
              borderBottom: activeTab === tab.key ? '2px solid #5b8cff' : '2px solid transparent',
              padding: '6px 12px',
              fontSize: 12,
              cursor: 'pointer',
              fontWeight: activeTab === tab.key ? 600 : 400,
              transition: 'color 0.15s',
              borderRadius: '4px 4px 0 0',
            }}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Tab content */}
      <div
        style={{
          maxHeight: '55vh',
          overflow: 'auto',
          minHeight: 120,
        }}
      >
        {renderTabContent()}
      </div>
    </ModalPanel>
  );
}
