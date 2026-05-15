/**
 * MemoryPrunePanel — 记忆淘汰建议面板
 *
 * 显示评分最低的记忆候选列表，支持一键批量清理。
 */

import { useState, useEffect, useCallback } from 'react';
import { apiGetScoringCandidates, apiPostPruneMemories } from '../api/memory';
import type { ScoringCandidate } from '../api/types';

export interface MemoryPrunePanelProps {
  agentId: string | null;
  onPruned?: () => void;
}

export function MemoryPrunePanel({ agentId, onPruned }: MemoryPrunePanelProps) {
  const [candidates, setCandidates] = useState<ScoringCandidate[]>([]);
  const [checked, setChecked] = useState<Set<string>>(new Set());
  const [loading, setLoading] = useState(false);
  const [pruning, setPruning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const loadCandidates = useCallback(async () => {
    if (!agentId) return;
    setLoading(true);
    setError(null);
    try {
      const data = await apiGetScoringCandidates(agentId, 10, 200);
      setCandidates(data.candidates);
      setChecked(new Set());
    } catch (e) {
      setError('加载淘汰建议失败');
    } finally {
      setLoading(false);
    }
  }, [agentId]);

  useEffect(() => {
    loadCandidates();
  }, [loadCandidates]);

  const toggleCheck = (id: string) => {
    setChecked((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const toggleAll = () => {
    if (checked.size === candidates.length) {
      setChecked(new Set());
    } else {
      setChecked(new Set(candidates.map((c) => c.memory_id)));
    }
  };

  const handlePrune = async () => {
    if (!agentId || checked.size === 0) return;
    setPruning(true);
    setError(null);
    setMessage(null);
    try {
      const ids = Array.from(checked);
      const result = await apiPostPruneMemories(agentId, ids);
      setMessage(`已清理 ${result.deletedCount} 条记忆`);
      onPruned?.();
      await loadCandidates();
    } catch (e) {
      setError('清理失败');
    } finally {
      setPruning(false);
    }
  };

  if (!agentId) {
    return <div className="prune-panel prune-panel--empty">选择 Agent 以管理记忆</div>;
  }

  if (loading) {
    return <div className="prune-panel prune-panel--loading">分析中...</div>;
  }

  if (error && candidates.length === 0) {
    return <div className="prune-panel prune-panel--error">{error}</div>;
  }

  if (candidates.length === 0) {
    return <div className="prune-panel prune-panel--empty">暂无淘汰建议，记忆数未超限</div>;
  }

  return (
    <div className="prune-panel">
      <div className="prune-panel__header">
        <span>淘汰建议 ({candidates.length})</span>
        <button
          className="prune-panel__toggle-all"
          onClick={toggleAll}
          disabled={pruning}
        >
          {checked.size === candidates.length ? '取消全选' : '全选'}
        </button>
      </div>

      <ul className="prune-panel__list">
        {candidates.map((c) => (
          <li
            key={c.memory_id}
            className={`prune-panel__item ${checked.has(c.memory_id) ? 'checked' : ''}`}
            onClick={() => toggleCheck(c.memory_id)}
          >
            <input
              type="checkbox"
              checked={checked.has(c.memory_id)}
              onChange={() => {}}
            />
            <div className="prune-panel__item-info">
              <span className="prune-panel__item-score">
                {c.score.toFixed(2)}
              </span>
              <span className="prune-panel__item-source">{c.source}</span>
              <span className="prune-panel__item-summary">
                {c.summary || '(无摘要)'}
              </span>
            </div>
          </li>
        ))}
      </ul>

      {message && <div className="prune-panel__message">{message}</div>}
      {error && <div className="prune-panel__error">{error}</div>}

      <button
        className="prune-panel__action"
        onClick={handlePrune}
        disabled={pruning || checked.size === 0}
      >
        {pruning ? '清理中...' : `清理选中 (${checked.size})`}
      </button>
    </div>
  );
}
