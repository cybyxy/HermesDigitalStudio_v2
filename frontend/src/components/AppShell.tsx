/**
 * AppShell — main application layout shell.
 *
 * Layout (all absolute positioning):
 *   ┌─────────────┬──────────────────────┬──────────────┐
 *   │ Left Panel  │                      │ Right Panel  │  ← absolute, top→bottom
 *   │ (260px)     │     Phaser Canvas    │ ≤380px       │  ← absolute, top→(bottom-menuH)
 *   │             │     (full viewport   │              │
 *   │             │      minus bottom)    │              │
 *   ├─────────────┴──────────────────────┴──────────────┤
 *   │              Status Bar (full width)               │  ← absolute, bottom=0
 *   └────────────────────────────────────────────────────┘
 *
 * Panels and content are rendered by specialized React components
 * (Phase 4), replacing the old Phaser Mixin DOM manipulation.
 */
import { useState, useEffect, useCallback, useRef } from 'react';
import { useSessionStore } from '../stores/sessionStore';
import { useAgentStore } from '../stores/agentStore';
import { useUiStore } from '../stores/uiStore';
import { usePlanStore } from '../stores/planStore';
import { useChannelStore } from '../stores/channelStore';
import { useModelStore } from '../stores/modelStore';
import { useSkillStore } from '../stores/skillStore';
import { StatusBar } from './StatusBar';
import { DockPanel, type DockPanelContent } from './DockPanel';
import { AgentList } from './AgentList';
import { TaskList } from './TaskList';
import { ChatPanel } from './ChatPanel';
import { AgentStatusPanel } from './AgentStatusPanel';
import { ChannelList } from './ChannelList';
import { ChannelEditForm, type ChannelFormData } from './ChannelEditForm';
import { AgentEditForm, type AgentFormData } from './AgentEditForm';
import { ModalPanel } from './ModalPanel';
import { ClarifyPrompt } from './ClarifyPrompt';
import { ModelList } from './ModelList';
import { SkillList } from './SkillList';
import { MemoryList } from './MemoryList';
import { MemoryDetailModal } from './MemoryDetailModal';
import { ModelEditForm, type ModelFormData } from './ModelEditForm';
import { useAgentList } from '../hooks/useAgentList';
import { useAutoConnectAgents } from '../hooks/useAutoConnectAgents';
import { useModelManager } from '../hooks/useModelManager';
import { useSseSession, useSseEventHandler, useHeartbeatSse } from '../hooks';
import { apiPostUpload } from '../api/chat';
import { apiDeleteSkill, apiGetSkills } from '../api/skills';
import * as api from '../api';
import { useChannelManager } from '../hooks/useChannelManager';
import { toMediaUrl } from '../lib/formatUtils';
import type { AgentInfo, SkillInfo, Attachment } from '../types';
import type { PlanSummary } from '../api/types';

// ─── Constants ───────────────────────────────────────────────────────────

const CSS_VARS = {
  panelW: 260,
  menuH: 48,
};

const RIGHT_PANEL_W = 'min(380px, 38vw)';

// ─── Sub-components ──────────────────────────── 。───────────────────────

function LeftPanel({ collapsed, onToggle }: { collapsed: boolean; onToggle: () => void }) {
  return (
    <>
      <aside id="shell-left" className={`shell-panel${collapsed ? ' collapsed' : ''}`}>
        <div className="shell-panel-content">
          <div id="left-panel-title" style={{ padding: '12px', fontSize: 13, fontWeight: 600, color: 'var(--muted)', borderBottom: '1px solid var(--border)', flexShrink: 0 }}>
            📋 任务
          </div>
          <div id="plan-timeline-host" style={{ flex: 1, overflow: 'hidden auto', minHeight: 0 }} />
        </div>
      </aside>
      <div
        id="toggle-left"
        className="shell-panel-toggle"
        style={collapsed ? { display: 'flex', position: 'absolute', left: 0, top: 10, width: 20, height: 28, borderRadius: '0 6px 6px 0', alignItems: 'center', justifyContent: 'center', cursor: 'pointer', color: '#8b93a7', fontSize: 13, background: 'rgba(20,24,32,0.7)', zIndex: 6, writingMode: 'horizontal-tb' } : { display: 'none' }}
        onClick={onToggle}
      >
        ›
      </div>
    </>
  );
}

function RightPanel({ collapsed, onToggle, sessionId }: { collapsed: boolean; onToggle: () => void; sessionId: string | null }) {
  return (
    <>
      <aside id="shell-right" className={`shell-panel${collapsed ? ' collapsed' : ''}`}>
        <div className="shell-panel-content" id="right-panel-content">
          <div id="chat-header" style={{ padding: '8px 12px', borderBottom: '1px solid var(--border)', flexShrink: 0, fontSize: 13, color: 'var(--muted)' }}>
            会话
          </div>
          <ChatPanel sessionId={sessionId} />
        </div>
      </aside>
      <div
        id="toggle-right"
        className="shell-panel-toggle"
        style={collapsed ? { display: 'flex', position: 'absolute', right: 0, top: 10, width: 20, height: 28, borderRadius: '6px 0 0 6px', alignItems: 'center', justifyContent: 'center', cursor: 'pointer', color: '#8b93a7', fontSize: 13, background: 'rgba(20,24,32,0.7)', zIndex: 6 } : { display: 'none' }}
        onClick={onToggle}
      >
        ‹
      </div>
    </>
  );
}

// ─── Bottom Bar (full-width, absolutely positioned) ────────────────────

function BottomBar() {
  const [pendingAttachments, setPendingAttachments] = useState<Attachment[]>([]);
  const pendingAttachmentsRef = useRef<Attachment[]>([]);

  const onSend = useCallback(async () => {
    const sessionState = useSessionStore.getState();
    const text = sessionState.input.trim();

    // 抽取并清空待发送附件
    const attachments = [...pendingAttachmentsRef.current];
    pendingAttachmentsRef.current = [];
    setPendingAttachments([]);

    if ((!text && attachments.length === 0) || !sessionState.activeId) {
      // 恢复附件
      pendingAttachmentsRef.current = attachments;
      setPendingAttachments(attachments);
      return;
    }

    console.log('[onSend] 发送消息 sessionId:', sessionState.activeId, 'text:', text.slice(0, 50));

    sessionState.setInput('');
    sessionState.setSending(true);

    try {
      const result = await api.apiFetch<{ run_id?: string; ok?: boolean }>(
        '/api/chat/orchestrated/run',
        { method: 'POST', json: { sessionId: sessionState.activeId, text, ...(attachments.length > 0 ? { attachments } : {}) } },
      );

      console.log('[onSend] run_id:', result.run_id);
      if (!result.run_id) {
        useSessionStore.getState().appendError(sessionState.activeId!, '发送失败：未获取到 run_id');
        sessionState.setSending(false);
        // 发送失败时恢复附件
        pendingAttachmentsRef.current = attachments;
        setPendingAttachments(attachments);
        return;
      }

      // 将用户消息追加到右侧会话面板（后端不发用户消息回显）
      useSessionStore.getState().appendChat(sessionState.activeId!, {
        role: 'user',
        text,
        attachments: attachments.length > 0 ? attachments : undefined,
        timestamp: Date.now(),
      });

      await new Promise<void>((resolve) => {
        const es = new EventSource(
          `/api/chat/orchestrated/stream?run_id=${encodeURIComponent(result.run_id!)}`,
        );
        const finish = () => { es.close(); resolve(); };
        es.onmessage = (e) => {
          try {
            const evt = JSON.parse(e.data) as { type: string };
            if (evt.type === 'orch_done') { console.log('[onSend] orch_done'); finish(); }
            else if (evt.type === 'orch_error') { console.error('[onSend] orch_error'); finish(); }
          } catch { /* ignore */ }
        };
        es.onerror = finish;
        setTimeout(finish, 60000);
      });
    } catch (err) {
      console.error('发送异常:', err);
    } finally {
      useSessionStore.getState().setSending(false);
    }
  }, []);

  const handleUpload = useCallback(async (file: File) => {
    const sessionState = useSessionStore.getState();
    const session = sessionState.sessions.find((s) => s.id === sessionState.activeId);
    const formData = new FormData();
    formData.append('file', file);
    formData.append('agent_id', session?.agentId || '');
    try {
      const result = await apiPostUpload(formData);
      if (result.url) {
        const attachment: Attachment = {
          url: toMediaUrl(result.url),
          filename: result.filename || file.name,
          contentType: file.type,
          size: file.size,
        };
        pendingAttachmentsRef.current = [...pendingAttachmentsRef.current, attachment];
        setPendingAttachments([...pendingAttachmentsRef.current]);
      }
    } catch (err) {
      console.error('上传失败:', err);
    }
  }, []);

  const handleRemoveAttachment = useCallback((index: number) => {
    pendingAttachmentsRef.current = pendingAttachmentsRef.current.filter((_, i) => i !== index);
    setPendingAttachments([...pendingAttachmentsRef.current]);
  }, []);

  return (
    <footer
      id="shell-bottom"
      style={{
        position: 'absolute',
        bottom: 0,
        left: 0,
        right: 0,
        height: CSS_VARS.menuH,
        display: 'flex',
        background: 'var(--panel)',
        borderTop: '1px solid var(--border)',
        zIndex: 10,
      }}
    >
      <div style={{ flex: 1, padding: '8px 12px', display: 'flex', flexDirection: 'column' }}>
        <StatusBar
          onSend={onSend}
          onUploadImage={handleUpload}
          onUploadFile={handleUpload}
          pendingAttachments={pendingAttachments}
          onRemoveAttachment={handleRemoveAttachment}
        />
      </div>
    </footer>
  );
}

// ─── Main Shell ──────────────────────────────────────────────────────────

export function AppShell() {
  const { switchAgent } = useAgentList();
  const [leftCollapsed, setLeftCollapsed] = useState(false);
  const [rightCollapsed, setRightCollapsed] = useState(false);

  // Dock panel state
  const dockContent = useUiStore((s) => s.dockContent);
  const agents = useAgentStore((s) => s.agents);
  const activeId = useSessionStore((s) => s.activeId);
  const models = useModelStore((s) => s.models);
  const channels = useChannelStore((s) => s.channels);
  const skills = useSkillStore((s) => s.skills);
  const taskListPlans = usePlanStore((s) => s.taskListPlans);
  const leftPanelTaskPlanId = usePlanStore((s) => s.leftPanelTaskPlanId);
  const sessions = useSessionStore((s) => s.sessions);
  const showChannelModal = useChannelStore((s) => s.showChannelModal);
  const editingChannelId = useChannelStore((s) => s.editingChannelId);
  const showModelModal = useModelStore((s) => s.showModelModal);
  const editingModelId = useModelStore((s) => s.editingModelId);
  const showAgentModal = useUiStore((s) => s.showAgentModal);
  const editingAgentId = useAgentStore((s) => s.editingAgentId);
  const providers = useModelStore((s) => s.providers);
  const reasoningResultModal = useAgentStore((s) => s.reasoningResultModal);

  const [selectedSkill, setSelectedSkill] = useState<SkillInfo | null>(null);
  const [selectedMemoryAgentId, setSelectedMemoryAgentId] = useState<string | null>(null);

  // Full agent detail (from detail endpoint, includes SOUL.md fields)
  const [editingAgentData, setEditingAgentData] = useState<AgentInfo | null>(null);

  // Fetch agent detail when editingAgentId changes
  useEffect(() => {
    if (editingAgentId) {
      api.apiGetAgent(editingAgentId).then((agent) => {
        console.log('[AppShell] agent detail loaded:', agent.agentId, agent.displayName);
        setEditingAgentData(agent);
      }).catch((err) => console.error('获取 Agent 详情失败:', err));
    } else {
      setEditingAgentData(null);
    }
  }, [editingAgentId]);

  // Channel CRUD
  const { refreshChannels, createChannel, updateChannel, deleteChannel } = useChannelManager();

  // Model management
  const { refreshModels } = useModelManager();

  // Load models on mount
  useEffect(() => {
    refreshModels();
  }, [refreshModels]);

  // 自动连接所有 Agent（页面加载时无历史 session 的场景）
  const { handleEvent } = useSseEventHandler();
  useAutoConnectAgents(agents, (sessionId) => {
    console.log('[AppShell] 自动连接就绪，activeId:', sessionId);
  });

  // Connect SSE event stream for the active session
  useSseSession({ sessionId: activeId, onEvent: handleEvent });

  // Connect heartbeat SSE for background reasoning results
  useHeartbeatSse(true);

  // Delete skill handler: deletes skill directory & reloads all skills
  const handleDeleteSkill = useCallback(async (skill: { path: string }) => {
    await apiDeleteSkill(skill.path);
    const refreshed = await apiGetSkills();
    useSkillStore.getState().setSkills(refreshed);
  }, []);

  // Build dock panel content based on dockContent
  const buildDockContent = useCallback((): DockPanelContent | null => {
    switch (dockContent) {
      case 'agents':
        return {
          title: 'Agent 管理',
          content: (
            <AgentList
              agents={agents}
              activeAgentId={sessions.find(s => s.id === activeId)?.agentId ?? null}
              models={models.map((m) => ({
                id: m.id,
                name: m.model || m.name || m.provider,
                provider: m.provider,
                isDefault: m.isDefault,
              }))}
              onSelect={(agentId) => {
                useAgentStore.getState().setSelectedAgentId(agentId);
                const sessionStore = useSessionStore.getState();
                const existingSession = sessionStore.sessions.find((s) => s.agentId === agentId);
                if (existingSession) {
                  sessionStore.setActiveId(existingSession.id);
                } else {
                  switchAgent(agentId);
                }
              }}
              onEdit={(agentId) => {
                useAgentStore.getState().setEditingAgentId(agentId);
              }}
              onAdd={() => {
                useUiStore.getState().setShowAgentModal(true);
              }}
              onDelete={(agentId) => {
                api.apiDeleteAgent(agentId)
                  .then(() => useAgentStore.getState().removeAgent(agentId))
                  .catch((err) => console.error('删除 Agent 失败:', err));
              }}
              onModelChange={(agentId, model, provider) => {
                api.apiPutAgentModel(agentId, { model, modelProvider: provider })
                  .catch((err) => console.error('更新模型失败:', err));
              }}
            />
          ),
        };

      case 'tasks':
        return {
          title: '任务管理',
          content: (
            <TaskList
              bundles={taskListPlans.map((p: PlanSummary) => ({
                planId: p.id ?? 0,
                artifact: {
                  name: p.name,
                  planSummary: p.planSummary ?? '',
                  steps: (p.steps ?? []).map((s) => ({
                    id: s.stepIndex,
                    title: s.title ?? `Step ${s.stepIndex + 1}`,
                    action: s.action ?? '',
                    confidence: 'medium' as const,
                  })),
                  plannerAgentId: p.agentId,
                },
                anchorTs: p.createdAt,
                dbPlan: {
                  status: p.status,
                  steps: (p.steps ?? []).map((s) => ({
                    stepIndex: s.stepIndex,
                    stepTitle: s.title ?? undefined,
                    title: s.title ?? undefined,
                    status: s.stepStatus,
                    executor: s.executor,
                  })),
                },
                sessionId: p.sessionId,
              }))}
              agents={agents}
              selectedPlanId={leftPanelTaskPlanId}
              onSelectPlan={(planId) => {
                usePlanStore.getState().setLeftPanelTaskPlanId(planId);
              }}
              onDeletePlan={(planId) => {
                api.apiFetch(`/api/chat/plans/${planId}`, { method: 'DELETE' })
                  .then(() => usePlanStore.getState().deleteTaskPlan(planId))
                  .catch((err) => console.error('删除任务失败:', err));
              }}
            />
          ),
        };

      case 'channels':
        return {
          title: '通道管理',
          content: (
            <ChannelList
              channels={channels}
              agents={agents}
              onAdd={() => {
                useChannelStore.getState().setShowChannelModal(true, null);
              }}
              onEdit={(channelId) => {
                useChannelStore.getState().setShowChannelModal(true, channelId);
              }}
              onDelete={async (channelId) => {
                try {
                  await deleteChannel(channelId);
                } catch (err) {
                  console.error('删除通道失败:', err);
                }
              }}
            />
          ),
        };

      case 'models':
        return {
          title: '模型管理',
          content: (
            <ModelList
              models={models.map((m) => ({
                id: m.id,
                name: m.model || m.name || m.provider,
                provider: m.provider,
                isDefault: m.isDefault,
              }))}
              onAdd={() => {
                useModelStore.getState().setShowModelModal(true, null);
              }}
              onEdit={(modelId) => {
                useModelStore.getState().setShowModelModal(true, modelId);
              }}
              onDelete={async (modelId) => {
                try {
                  await api.apiDeleteModel(modelId);
                  await refreshModels();
                } catch (err) {
                  console.error('删除模型失败:', err);
                }
              }}
              onSetDefault={async (modelId) => {
                try {
                  await api.apiPutModel(modelId, { isDefault: true });
                  await refreshModels();
                } catch (err) {
                  console.error('设置默认模型失败:', err);
                }
              }}
            />
          ),
        };

      case 'skills':
        return {
          title: '技能管理',
          content: (
            <SkillList data={skills} onDeleteSkill={handleDeleteSkill} onOpenSkill={(sk) => setSelectedSkill(sk)} />
          ),
        };

      case 'memory':
        return {
          title: '记忆管理',
          content: (
            <MemoryList
              agents={agents}
              onSelectMemory={(agentId) => setSelectedMemoryAgentId(agentId)}
            />
          ),
        };

      default:
        return null;
    }
  }, [dockContent, agents, activeId, models, channels, skills, taskListPlans, leftPanelTaskPlanId, sessions, switchAgent, deleteChannel, refreshModels, handleDeleteSkill]);

  // Close handler: resets the active dock flag via store
  const handleDockClose = useCallback(() => {
    const s = useUiStore.getState();
    if (s.showAgentList) s.setShowAgentList(false);
    else if (s.showTaskManager) s.setShowTaskManager(false);
    else if (s.showChannelManager) s.setShowChannelManager(false);
    else if (s.showModelManager) s.setShowModelManager(false);
    else if (s.showSkillManager) s.setShowSkillManager(false);
    else if (s.showMemoryManager) s.setShowMemoryManager(false);
  }, []);

  const panelContent = buildDockContent();

  // Listen to uiStore for panel toggle commands
  useEffect(() => {
    const unsub = useUiStore.subscribe((s, prev) => {
      if (s.showTaskManager !== prev.showTaskManager) {
        setLeftCollapsed(!s.showTaskManager);
      }
    });
    return unsub;
  }, []);

  return (
    <div id="app-shell">
      <LeftPanel collapsed={leftCollapsed} onToggle={() => setLeftCollapsed(!leftCollapsed)} />
      <RightPanel collapsed={rightCollapsed} onToggle={() => setRightCollapsed(!rightCollapsed)} sessionId={activeId} />

      {/* Center area: pass-through area between left/right panels, above bottom bar */}
      <div
        id="center-area"
        style={{
          position: 'absolute',
          left: leftCollapsed ? 0 : CSS_VARS.panelW,
          right: rightCollapsed ? 0 : RIGHT_PANEL_W,
          top: 0,
          bottom: CSS_VARS.menuH,
          overflow: 'hidden',
          pointerEvents: 'none',
        }}
      />

      {/* Agent 状态浮动窗体 — 浮在场景上层，紧贴会话右侧面板 */}
      {(() => {
        const session = activeId ? sessions.find((s) => s.id === activeId) : null;
        return session?.agentId ? (
          <div style={{
            position: 'absolute',
            right: rightCollapsed ? 0 : RIGHT_PANEL_W,
            top: 10,
            zIndex: 15,
            pointerEvents: 'auto',
          }}>
            <AgentStatusPanel agentId={session.agentId} />
          </div>
        ) : null;
      })()}

      {/* Bottom bar: full width at bottom */}
      <BottomBar />

      {/* Dock panel: slides up from bottom when a dock is active */}
      {panelContent && (
        <DockPanel
          content={panelContent}
          open={true}
          onClose={handleDockClose}
        />
      )}

      {/* Channel edit/create modal */}
      {showChannelModal && (
        <ModalPanel
          title={editingChannelId ? '编辑通道' : '新建通道'}
          modal
          onClose={() => useChannelStore.getState().setShowChannelModal(false)}
        >
          <ChannelEditForm
            channelId={editingChannelId ?? undefined}
            initialData={(() => {
              if (!editingChannelId) return undefined;
              const ch = channels.find((c) => c.id === editingChannelId);
              if (!ch) return undefined;
              return {
                name: ch.name || '',
                platform: ch.platform || '',
                enabled: ch.enabled !== false,
                token: ch.token || '',
                chatId: ch.chatId || '',
                replyToMode: ch.replyToMode || 'off',
                extra: ch.extra ? JSON.stringify(ch.extra, null, 2) : '',
                agentId: ch.agentId || '',
              };
            })()}
            agents={agents}
            onSubmit={async (data: ChannelFormData) => {
              try {
                if (editingChannelId) {
                  await updateChannel(editingChannelId, data as unknown as Record<string, unknown>);
                } else {
                  await createChannel(data as unknown as Record<string, unknown>);
                }
                useChannelStore.getState().setShowChannelModal(false);
              } catch (err) {
                console.error('保存通道失败:', err);
              }
            }}
            onCancel={() => useChannelStore.getState().setShowChannelModal(false)}
          />
        </ModalPanel>
      )}

      {/* Model edit/create modal */}
      {showModelModal && (
        <ModalPanel
          title={editingModelId ? '编辑模型' : '新建模型'}
          modal
          onClose={() => useModelStore.getState().setShowModelModal(false)}
        >
          <ModelEditForm
            modelId={editingModelId ?? undefined}
            initialData={(() => {
              if (!editingModelId) return undefined;
              const m = models.find((md) => md.id === editingModelId);
              if (!m) return undefined;
              return {
                id: m.id,
                provider: m.provider,
                model: m.model,
                name: m.name ?? '',
                baseUrl: m.baseUrl ?? '',
                apiKey: m.apiKey ?? '',
                isDefault: m.isDefault ?? false,
              };
            })()}
            providers={providers}
            onSubmit={async (data: ModelFormData) => {
              try {
                if (editingModelId) {
                  await api.apiPutModel(editingModelId, {
                    name: data.name,
                    provider: data.provider,
                    modelId: data.model,
                    apiBase: data.baseUrl,
                    apiKey: data.apiKey,
                    isDefault: data.isDefault,
                  });
                } else {
                  await api.apiPostModel({
                    name: data.name,
                    provider: data.provider,
                    modelId: data.model,
                    apiBase: data.baseUrl,
                    apiKey: data.apiKey,
                    isDefault: data.isDefault,
                  });
                }
                await refreshModels();
                useModelStore.getState().setShowModelModal(false);
              } catch (err) {
                console.error('保存模型失败:', err);
              }
            }}
            onCancel={() => useModelStore.getState().setShowModelModal(false)}
          />
        </ModalPanel>
      )}

      {/* Agent create/edit modal */}
      {(showAgentModal || editingAgentId) && (
        <AgentEditForm
          agentId={editingAgentId ?? undefined}
          initialData={(() => {
            if (!editingAgentId) return undefined;
            if (!editingAgentData) return undefined;
            return {
              displayName: editingAgentData.displayName || '',
              profile: editingAgentData.profile || '',
              avatar: editingAgentData.avatar || '',
              gender: (editingAgentData.gender as 'male' | 'female') || 'male',
              personality: editingAgentData.personality || '',
              catchphrases: editingAgentData.catchphrases || '',
              memes: editingAgentData.memes || '',
              identity: editingAgentData.identity || '',
              style: editingAgentData.style || '',
              defaults: editingAgentData.defaults || '',
              avoid: editingAgentData.avoid || '',
              coreTruths: editingAgentData.coreTruths || '',
            } satisfies Partial<AgentFormData>;
          })()}
          onSubmit={async (data: AgentFormData) => {
            if (editingAgentId) {
              await api.apiFetch(`/api/chat/agents/${encodeURIComponent(editingAgentId)}`, {
                method: 'PUT',
                json: data,
              });
            } else {
              await api.apiPostAgent(data);
            }
            useUiStore.getState().setShowAgentModal(false);
            useAgentStore.getState().setEditingAgentId(null);
            // Refresh agents list
            const refreshed = await api.apiGetAgents();
            useAgentStore.getState().setAgents(refreshed);
          }}
          onCancel={() => {
            useUiStore.getState().setShowAgentModal(false);
            useAgentStore.getState().setEditingAgentId(null);
          }}
        />
      )}

      {/* Skill detail modal */}
      {selectedSkill && (
        <ModalPanel
          title={`技能详情 — ${selectedSkill.name}`}
          maxWidth="36rem"
          onClose={() => setSelectedSkill(null)}
        >
          <div style={{ fontSize: 13, color: '#c8ccd4', lineHeight: 1.8 }}>
            <div style={{ marginBottom: 12 }}>
              <div style={{ fontWeight: 600, color: '#e8eaef', fontSize: 15, marginBottom: 4 }}>
                {selectedSkill.name}
              </div>
              <div style={{ fontSize: 12, color: '#8b93a7', display: 'flex', gap: 12, flexWrap: 'wrap' }}>
                {selectedSkill.version && <span>版本: {selectedSkill.version}</span>}
                {selectedSkill.author && <span>作者: @{selectedSkill.author}</span>}
                {selectedSkill.license && <span>许可: {selectedSkill.license}</span>}
                {selectedSkill.category && <span>分类: {selectedSkill.category}</span>}
              </div>
            </div>

            {selectedSkill.description && (
              <div style={{ marginBottom: 12 }}>
                <div style={{ fontWeight: 600, color: '#e8eaef', marginBottom: 4, fontSize: 12 }}>描述</div>
                <div style={{ fontSize: 12, color: '#a8b0c4', whiteSpace: 'pre-wrap' }}>{selectedSkill.description}</div>
              </div>
            )}

            {selectedSkill.tags && selectedSkill.tags.length > 0 && (
              <div style={{ marginBottom: 12 }}>
                <div style={{ fontWeight: 600, color: '#e8eaef', marginBottom: 4, fontSize: 12 }}>标签</div>
                <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                  {selectedSkill.tags.map((t) => (
                    <span key={t} style={{ background: 'rgba(91,140,255,0.15)', color: '#5b8cff', borderRadius: 4, padding: '2px 8px', fontSize: 11 }}>{t}</span>
                  ))}
                </div>
              </div>
            )}

            {selectedSkill.platforms && selectedSkill.platforms.length > 0 && (
              <div style={{ marginBottom: 12 }}>
                <div style={{ fontWeight: 600, color: '#e8eaef', marginBottom: 4, fontSize: 12 }}>支持平台</div>
                <div style={{ fontSize: 12, color: '#a8b0c4' }}>{selectedSkill.platforms.join(', ')}</div>
              </div>
            )}

            {selectedSkill.commands && selectedSkill.commands.length > 0 && (
              <div style={{ marginBottom: 12 }}>
                <div style={{ fontWeight: 600, color: '#e8eaef', marginBottom: 4, fontSize: 12 }}>命令</div>
                <div style={{ fontSize: 12, color: '#a8b0c4', fontFamily: 'monospace' }}>
                  {selectedSkill.commands.map((c) => (
                    <div key={c} style={{ padding: '2px 0' }}>⬡ {c}</div>
                  ))}
                </div>
              </div>
            )}

            <div>
              <div style={{ fontWeight: 600, color: '#e8eaef', marginBottom: 4, fontSize: 12 }}>路径</div>
              <div style={{ fontSize: 11, color: '#5a6478', fontFamily: 'monospace', wordBreak: 'break-all' }}>
                {selectedSkill.path}
              </div>
            </div>
          </div>
        </ModalPanel>
      )}

      {/* Reasoning result modal */}
      {reasoningResultModal && (
        <ModalPanel
          title="推理结果"
          maxWidth="42rem"
          onClose={() => useAgentStore.getState().setReasoningResultModal(null)}
        >
          <div style={{ fontSize: 13, color: '#c8ccd4', lineHeight: 1.7, whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>
            {reasoningResultModal.text}
          </div>
        </ModalPanel>
      )}

      {/* Clarify prompt — Agent 请求用户澄清 */}
      <ClarifyPrompt />

      {/* Memory detail modal */}
      {selectedMemoryAgentId && (
        <MemoryDetailModal
          agentId={selectedMemoryAgentId}
          agentName={agents.find((a) => a.agentId === selectedMemoryAgentId)?.displayName || selectedMemoryAgentId}
          onClose={() => setSelectedMemoryAgentId(null)}
        />
      )}
    </div>
  );
}
