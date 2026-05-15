/**
 * SkillEditForm — React replacement for class-based SkillEditForm.
 * Dual-mode (view/edit) skill editor using ModalPanel.
 */
import { useState, useEffect, useCallback } from 'react';
import { ModalPanel } from './ModalPanel';
import * as api from '../api';
import { parseSkillContent, serializeSkillContent } from '../lib/skillFrontmatter';
import type { SkillFrontmatter } from '../lib/skillFrontmatter';
import { renderMarkdown } from '../lib/markdownRenderer';

interface SkillInfo {
  path?: string;
  name?: string;
  description?: string;
}

interface Props {
  skill: SkillInfo;
  open: boolean;
  onClose: () => void;
  onSaved?: (newContent: string) => void;
}

export function SkillEditForm({ skill, open, onClose, onSaved }: Props) {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [mode, setMode] = useState<'view' | 'edit'>('view');
  const [parsed, setParsed] = useState<ReturnType<typeof parseSkillContent> | null>(null);
  const [rawContent, setRawContent] = useState('');
  const [editText, setEditText] = useState('');
  const [saving, setSaving] = useState(false);

  // Load skill content
  useEffect(() => {
    if (!open || !skill.path) return;
    setLoading(true);
    setError('');
    setMode('view');

    api.apiGetSkillMd(skill.path)
      .then((content) => {
        setRawContent(content);
        setEditText(content);
        setParsed(parseSkillContent(content));
      })
      .catch(() => setError('无法加载技能内容'))
      .finally(() => setLoading(false));
  }, [open, skill.path]);

  const handleSave = useCallback(async () => {
    if (!skill.path || editText === rawContent) return;
    setSaving(true);
    setError('');
    try {
      await api.apiPutSkillMd(skill.path, editText);
      setRawContent(editText);
      setParsed(parseSkillContent(editText));
      setMode('view');
      onSaved?.(editText);
      setTimeout(onClose, 1500);
    } catch {
      setError('保存失败');
    } finally {
      setSaving(false);
    }
  }, [skill.path, editText, rawContent, onSaved, onClose]);

  if (!open) return null;

  const md = parsed?.frontmatter;

  return (
    <ModalPanel
      title={`${mode === 'edit' ? '编辑' : ''} ${skill.name || skill.path || '技能'}`}
      icon="⚡"
      maxWidth="48rem"
      modal
      onClose={onClose}
    >
      {loading ? (
        <div style={{ textAlign: 'center', padding: 20, color: '#8b93a7' }}>加载中...</div>
      ) : error ? (
        <div style={{ color: '#e53935', padding: 12 }}>{error}</div>
      ) : mode === 'view' ? (
        /* View mode */
        <div>
          {skill.path && (
            <div style={{ fontSize: 11, color: '#5a6478', marginBottom: 8 }}>📁 {skill.path}</div>
          )}

          {/* Metadata */}
          {md && (
            <div style={{
              background: 'rgba(42,49,64,0.3)',
              borderRadius: 6,
              padding: 10,
              marginBottom: 12,
            }}>
              {(md as SkillFrontmatter).name && <h2 style={{ margin: '0 0 4px', fontSize: 16, color: '#e8eaef' }}>{(md as SkillFrontmatter).name}</h2>}
              {md.description && <p style={{ margin: 0, fontSize: 12, color: '#8b93a7' }}>{md.description}</p>}
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginTop: 6, fontSize: 10, color: '#5a6478' }}>
                {md.version && <span>v{String(md.version)}</span>}
                {md.author && <span>@{String(md.author)}</span>}
                {md.license && <span>{String(md.license)}</span>}
              </div>
            </div>
          )}

          {/* Markdown body */}
          <div
            style={{ fontSize: 12, lineHeight: 1.6, color: '#e8eaef' }}
            dangerouslySetInnerHTML={{
              __html: renderMarkdown(parsed?.markdownContent || ''),
            }}
          />

          <div style={{ marginTop: 12, textAlign: 'right' }}>
            <button
              onClick={() => { setMode('edit'); setEditText(rawContent); }}
              style={{
                background: '#5b8cff',
                color: '#fff',
                border: 'none',
                borderRadius: 4,
                padding: '6px 16px',
                fontSize: 12,
                cursor: 'pointer',
              }}
            >
              编辑全文
            </button>
          </div>
        </div>
      ) : (
        /* Edit mode */
        <div>
          <div style={{ display: 'flex', gap: 8, marginBottom: 8, alignItems: 'center' }}>
            <button
              onClick={() => setMode('view')}
              style={{ background: 'none', border: '1px solid #2a3140', borderRadius: 4, color: '#8b93a7', cursor: 'pointer', fontSize: 11, padding: '4px 10px' }}
            >
              返回预览
            </button>
            <div style={{ flex: 1 }} />
            {saving && <span style={{ fontSize: 11, color: '#5b8cff' }}>保存中...</span>}
            <button
              onClick={onClose}
              style={{ background: 'none', border: '1px solid #2a3140', borderRadius: 4, color: '#8b93a7', cursor: 'pointer', fontSize: 11, padding: '4px 10px' }}
            >
              取消
            </button>
            <button
              onClick={handleSave}
              disabled={saving || editText === rawContent}
              style={{
                background: editText === rawContent ? '#1a2230' : '#5b8cff',
                color: editText === rawContent ? '#8b93a7' : '#fff',
                border: 'none',
                borderRadius: 4,
                padding: '4px 12px',
                fontSize: 11,
                cursor: editText === rawContent ? 'default' : 'pointer',
              }}
            >
              保存
            </button>
          </div>

          <textarea
            value={editText}
            onChange={(e) => setEditText(e.target.value)}
            style={{
              width: '100%',
              minHeight: 300,
              background: '#0f1218',
              color: '#e8eaef',
              border: '1px solid #2a3140',
              borderRadius: 4,
              padding: 10,
              fontSize: 12,
              fontFamily: 'monospace',
              resize: 'vertical',
              outline: 'none',
            }}
          />
        </div>
      )}
    </ModalPanel>
  );
}
