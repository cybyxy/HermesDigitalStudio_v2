/**
 * SkillList — Tabbed skill browser organized by agent, with expandable category groups.
 * Shows skill name, description, version, author, etc. with enable/disable toggle and delete.
 */
import { useState, useCallback } from 'react';
import type { AgentSkills, SkillInfo } from '../types';

// ─── localStorage key ──────────────────────────────────────────────────────
const LS_DISABLED_KEYS = 'skill_disabled_keys';

function loadDisabledKeys(): Set<string> {
  try {
    const raw = localStorage.getItem(LS_DISABLED_KEYS);
    if (raw) return new Set(JSON.parse(raw) as string[]);
  } catch { /* ignore */ }
  return new Set();
}

function saveDisabledKeys(keys: Set<string>) {
  localStorage.setItem(LS_DISABLED_KEYS, JSON.stringify([...keys]));
}

// ─── Props ────────────────────────────────────────────────────────────────

interface Props {
  data: AgentSkills[];
  onRefresh?: () => void;
  onOpenSkill?: (skill: SkillInfo) => void;
  onDeleteSkill?: (skill: SkillInfo) => Promise<void>;
}

// ─── Component ────────────────────────────────────────────────────────────

export function SkillList({ data, onRefresh, onOpenSkill, onDeleteSkill }: Props) {
  const [activeTab, setActiveTab] = useState(0);
  const [disabledKeys, setDisabledKeys] = useState<Set<string>>(loadDisabledKeys);
  const [confirmDelete, setConfirmDelete] = useState<SkillInfo | null>(null);
  const [deleting, setDeleting] = useState(false);

  const toggleEnabled = useCallback((skillId: string) => {
    setDisabledKeys((prev) => {
      const next = new Set(prev);
      if (next.has(skillId)) next.delete(skillId);
      else next.add(skillId);
      saveDisabledKeys(next);
      return next;
    });
  }, []);

  const handleDelete = useCallback(async () => {
    if (!confirmDelete || !onDeleteSkill) return;
    setDeleting(true);
    try {
      await onDeleteSkill(confirmDelete);
    } finally {
      setDeleting(false);
      setConfirmDelete(null);
    }
  }, [confirmDelete, onDeleteSkill]);

  if (!data.length) {
    return (
      <div style={{ textAlign: 'center', color: '#8b93a7', padding: 20, fontSize: 13 }}>
        暂无可显示技能
      </div>
    );
  }

  const current = data[activeTab];
  if (!current) return null;

  // Group skills by category
  const groups: Record<string, SkillInfo[]> = {};
  for (const s of current.skills) {
    const cat = s.category || '默认';
    if (!groups[cat]) groups[cat] = [];
    groups[cat]!.push(s);
  }

  return (
    <div style={{ display: 'flex', gap: 8, height: '100%', position: 'relative' }}>
      {/* Vertical tab bar — left side */}
      <div style={{
        display: 'flex',
        flexDirection: 'column',
        gap: 2,
        borderRight: '1px solid #2a3140',
        paddingRight: 6,
        flexShrink: 0,
        overflowY: 'auto',
      }}>
        {data.map((item, i) => (
          <button
            key={i}
            onClick={() => setActiveTab(i)}
            style={{
              padding: '6px 10px',
              border: 'none',
              borderRadius: 4,
              background: activeTab === i ? 'rgba(91,140,255,0.2)' : 'transparent',
              color: activeTab === i ? '#5b8cff' : '#8b93a7',
              cursor: 'pointer',
              fontSize: 12,
              fontWeight: activeTab === i ? 600 : 400,
              whiteSpace: 'nowrap',
              textAlign: 'left',
            }}
          >
            {item.agentName}
            <span style={{ fontSize: 10, marginLeft: 4, opacity: 0.6 }}>
              {item.skills.length}
            </span>
          </button>
        ))}
      </div>

      {/* Skill content — right side */}
      <div style={{ flex: 1, minWidth: 0, overflowY: 'auto' }}>
        {Object.keys(groups).length === 0 ? (
          <div style={{ textAlign: 'center', color: '#8b93a7', padding: 16, fontSize: 12 }}>
            该 Agent 暂无技能
          </div>
        ) : (
          Object.entries(groups).map(([category, skills]) => (
            <details key={category} open style={{ marginBottom: 4 }}>
              <summary style={{
                cursor: 'pointer',
                padding: '4px 8px',
                fontSize: 12,
                fontWeight: 600,
                color: '#e8eaef',
                background: 'rgba(42,49,64,0.3)',
                borderRadius: 4,
              }}>
                ▶ {category}
                <span style={{ fontSize: 10, color: '#8b93a7', marginLeft: 6 }}>
                  ({skills.length})
                </span>
              </summary>

              <div style={{ padding: '4px 0' }}>
                {skills.map((sk) => {
                  const isDisabled = disabledKeys.has(sk.id);
                  return (
                    <div
                      key={sk.id}
                      onClick={() => onOpenSkill?.(sk)}
                      style={{
                        display: 'flex',
                        alignItems: 'center',
                        gap: 6,
                        padding: '6px 8px',
                        borderBottom: '1px solid rgba(42,49,64,0.3)',
                        opacity: isDisabled ? 0.45 : 1,
                        transition: 'opacity 0.15s',
                        cursor: 'pointer',
                        borderRadius: 4,
                      }}
                    >
                      <span style={{ fontSize: 14, flexShrink: 0 }}>⚡</span>
                      <span style={{ fontSize: 12, fontWeight: 500, color: '#e8eaef', whiteSpace: 'nowrap', flexShrink: 0 }}>
                        {sk.name}
                      </span>
                      {sk.description && (
                        <span style={{ fontSize: 11, color: '#8b93a7', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', flexShrink: 1, minWidth: 0 }}>
                          {sk.description}
                        </span>
                      )}
                      <div style={{ display: 'flex', gap: 6, fontSize: 10, color: '#5a6478', whiteSpace: 'nowrap', flexShrink: 0, marginLeft: 'auto' }}>
                        {sk.version && <span>v{sk.version}</span>}
                        {sk.author && <span>@{sk.author}</span>}
                        {sk.license && <span>{sk.license}</span>}
                        {sk.platforms && <span>{sk.platforms.join(', ')}</span>}
                        {sk.commands && <span>⬡ {sk.commands.join(', ')}</span>}
                      </div>
                      <button
                        onClick={(e) => { e.stopPropagation(); toggleEnabled(sk.id); }}
                        title={isDisabled ? '点击启用' : '点击禁用'}
                        style={{ flexShrink: 0, width: 36, height: 20, borderRadius: 10, border: 'none', cursor: 'pointer', position: 'relative', background: isDisabled ? '#2a3140' : '#5b8cff', transition: 'background 0.2s', padding: 0 }}
                      >
                        <span style={{ position: 'absolute', top: 2, left: isDisabled ? 2 : 18, width: 16, height: 16, borderRadius: '50%', background: '#e8eaef', transition: 'left 0.2s' }} />
                      </button>
                      {onDeleteSkill && (
                        <button
                          onClick={() => setConfirmDelete(sk)}
                          title="删除此技能"
                          style={{ flexShrink: 0, background: 'none', border: 'none', color: '#8b93a7', cursor: 'pointer', fontSize: 14, padding: '2px 4px', lineHeight: 1 }}
                        >
                          🗑
                        </button>
                      )}
                    </div>
                  );
                })}
              </div>
            </details>
          ))
        )}

        {/* Refresh button */}
        {onRefresh && (
          <button
            onClick={onRefresh}
            style={{
              alignSelf: 'flex-end',
              background: 'none',
              border: '1px solid #2a3140',
              borderRadius: 4,
              color: '#8b93a7',
              cursor: 'pointer',
              fontSize: 11,
              padding: '4px 10px',
              marginTop: 4,
            }}
          >
            刷新列表
          </button>
        )}
      </div>

      {/* Delete confirmation overlay */}
      {confirmDelete && (
        <div style={{
          position: 'absolute',
          inset: 0,
          background: 'rgba(0,0,0,0.6)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          zIndex: 10,
          borderRadius: 8,
        }}>
          <div style={{
            background: '#1a2230',
            border: '1px solid #2a3140',
            borderRadius: 8,
            padding: '20px 24px',
            maxWidth: 360,
            textAlign: 'center',
          }}>
            <div style={{ fontSize: 14, fontWeight: 600, color: '#e8eaef', marginBottom: 8 }}>
              确认删除
            </div>
            <div style={{ fontSize: 12, color: '#8b93a7', marginBottom: 16 }}>
              确定要删除技能「<span style={{ color: '#e8eaef' }}>{confirmDelete.name}</span>」吗？<br />
              该操作将删除技能目录及其下所有文件，不可恢复。
            </div>
            <div style={{ display: 'flex', gap: 8, justifyContent: 'center' }}>
              <button
                onClick={() => setConfirmDelete(null)}
                disabled={deleting}
                style={{ padding: '6px 16px', border: '1px solid #2a3140', borderRadius: 4, background: 'transparent', color: '#8b93a7', cursor: 'pointer', fontSize: 12 }}
              >
                取消
              </button>
              <button
                onClick={handleDelete}
                disabled={deleting}
                style={{ padding: '6px 16px', border: 'none', borderRadius: 4, background: '#e53935', color: '#fff', cursor: 'pointer', fontSize: 12, fontWeight: 600 }}
              >
                {deleting ? '删除中...' : '确认删除'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
