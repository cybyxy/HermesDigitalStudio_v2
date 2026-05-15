/**
 * ModelList — React replacement for class-based ModelList.
 * Renders a card-grid of AI model configurations with a cost stats tab.
 */
import { useEffect, useState } from 'react';
import { apiGetGlobalCostStats } from '../api/model_cost';
import type { GlobalCostStats } from '../api/types';

interface ModelInfo {
  id: string;
  name: string;
  provider: string;
  isDefault?: boolean;
}

interface Props {
  models: ModelInfo[];
  onAdd?: () => void;
  onEdit?: (modelId: string) => void;
  onDelete?: (modelId: string) => void;
  onSetDefault?: (modelId: string) => void;
}

const PROVIDER_META: Record<string, { icon: string; label: string }> = {
  openai: { icon: '🔷', label: 'OpenAI' },
  anthropic: { icon: '🧠', label: 'Anthropic' },
  google: { icon: '🔺', label: 'Google' },
  deepseek: { icon: '🔍', label: 'DeepSeek' },
  moonshot: { icon: '🌙', label: 'Moonshot' },
  zhipu: { icon: '🏛', label: 'Zhipu' },
  baichuan: { icon: '🌊', label: 'Baichuan' },
  minimax: { icon: '💎', label: 'MiniMax' },
  qwen: { icon: '☁️', label: 'Qwen' },
  mistral: { icon: '🌪', label: 'Mistral' },
  cohere: { icon: '🔄', label: 'Cohere' },
  groq: { icon: '⚡', label: 'Groq' },
};

function resolveProvider(provider: string): { icon: string; label: string } {
  const key = Object.keys(PROVIDER_META).find(
    (k) => provider.toLowerCase().includes(k),
  );
  if (key) return PROVIDER_META[key]!;
  return { icon: '🧩', label: provider };
}

type ModelTabKey = 'models' | 'costs';

const MODEL_TABS: { key: ModelTabKey; label: string }[] = [
  { key: 'models', label: '模型列表' },
  { key: 'costs', label: '成本统计' },
];

const TIER_LABELS: Record<string, string> = {
  local: '本地/缓存',
  small: '轻量模型',
  medium: '标准模型',
  large: '大型模型',
};

const TIER_COLORS: Record<string, string> = {
  local: '#6b7280',
  small: '#10b981',
  medium: '#3b82f6',
  large: '#f59e0b',
};

function RenderCostStats() {
  const [stats, setStats] = useState<GlobalCostStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [days, setDays] = useState(7);

  const fetchStats = (d: number) => {
    setLoading(true);
    setError(null);
    apiGetGlobalCostStats(d)
      .then(setStats)
      .catch((err) => setError(err?.message || String(err)))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    fetchStats(days);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [days]);

  if (loading) {
    return <div style={{ color: '#6b7280', fontSize: 12, textAlign: 'center', padding: 24 }}>加载中...</div>;
  }
  if (error) {
    return <div style={{ color: '#e53935', fontSize: 12, textAlign: 'center', padding: 24 }}>加载失败: {error}</div>;
  }
  if (!stats || stats.total_calls === 0) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
        <DayRangeSelector days={days} onChange={setDays} />
        <div style={{ color: '#6b7280', fontSize: 12, textAlign: 'center', padding: 24, fontStyle: 'italic' }}>
          暂无模型调用记录
        </div>
      </div>
    );
  }

  const tiers = Object.keys(stats.by_tier);
  const providers = Object.keys(stats.by_provider);
  const maxTier = Math.max(...Object.values(stats.by_tier), 1);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
      <DayRangeSelector days={days} onChange={setDays} />

      {/* 汇总卡片 */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 8 }}>
        <div style={{ background: '#1a1d27', borderRadius: 8, padding: 12, textAlign: 'center' }}>
          <div style={{ fontSize: 20, fontWeight: 700, color: '#5b8cff' }}>{stats.total_calls}</div>
          <div style={{ fontSize: 10, color: '#8b93a7', marginTop: 4 }}>总调用次数</div>
        </div>
        <div style={{ background: '#1a1d27', borderRadius: 8, padding: 12, textAlign: 'center' }}>
          <div style={{ fontSize: 20, fontWeight: 700, color: '#10b981' }}>{stats.total_tokens.toLocaleString()}</div>
          <div style={{ fontSize: 10, color: '#8b93a7', marginTop: 4 }}>总 Token</div>
        </div>
        <div style={{ background: '#1a1d27', borderRadius: 8, padding: 12, textAlign: 'center' }}>
          <div style={{ fontSize: 20, fontWeight: 700, color: '#f59e0b' }}>${stats.estimated_cost.toFixed(4)}</div>
          <div style={{ fontSize: 10, color: '#8b93a7', marginTop: 4 }}>预估费用</div>
        </div>
      </div>

      {/* 按调用层级分布 */}
      <div style={{ background: '#1a1d27', borderRadius: 8, padding: 14 }}>
        <div style={{ fontSize: 12, fontWeight: 600, color: '#cbd5e1', marginBottom: 10 }}>
          按调用层级
        </div>
        {tiers.map((tier) => {
          const count = stats.by_tier[tier];
          const pct = Math.round((count / maxTier) * 100);
          return (
            <div key={tier} style={{ marginBottom: 6 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11, marginBottom: 2 }}>
                <span style={{ color: TIER_COLORS[tier] || '#8b93a7' }}>{TIER_LABELS[tier] || tier}</span>
                <span style={{ color: '#8b93a7' }}>{count} 次</span>
              </div>
              <div style={{ height: 5, background: '#24293a', borderRadius: 3, overflow: 'hidden' }}>
                <div style={{ height: '100%', width: `${pct}%`, background: TIER_COLORS[tier] || '#8b93a7', borderRadius: 3, transition: 'width 0.3s' }} />
              </div>
            </div>
          );
        })}
      </div>

      {/* 按厂商分布 */}
      {providers.length > 0 && (
        <div style={{ background: '#1a1d27', borderRadius: 8, padding: 14 }}>
          <div style={{ fontSize: 12, fontWeight: 600, color: '#cbd5e1', marginBottom: 10 }}>
            按厂商分布
          </div>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
            {providers.map((provider) => {
              const meta = resolveProvider(provider);
              return (
                <div key={provider}
                  style={{
                    background: '#24293a',
                    borderRadius: 6,
                    padding: '6px 10px',
                    display: 'flex',
                    alignItems: 'center',
                    gap: 6,
                  }}
                >
                  <span style={{ fontSize: 14 }}>{meta.icon}</span>
                  <span style={{ fontSize: 11, color: '#cbd5e1' }}>{meta.label}</span>
                  <span style={{ fontSize: 11, color: '#5b8cff', fontWeight: 600 }}>
                    {stats.by_provider[provider]} 次
                  </span>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}

function DayRangeSelector({ days, onChange }: { days: number; onChange: (d: number) => void }) {
  const options = [1, 7, 30, 90];
  return (
    <div style={{ display: 'flex', gap: 4, alignItems: 'center' }}>
      <span style={{ fontSize: 11, color: '#8b93a7' }}>统计周期:</span>
      {options.map((d) => (
        <button key={d}
          onClick={() => onChange(d)}
          style={{
            padding: '3px 8px',
            background: days === d ? 'rgba(91,140,255,0.18)' : 'transparent',
            color: days === d ? '#5b8cff' : '#8b93a7',
            border: `1px solid ${days === d ? '#5b8cff' : '#2a3140'}`,
            borderRadius: 4,
            fontSize: 11,
            cursor: 'pointer',
          }}
        >
          {d === 1 ? '今天' : `${d} 天`}
        </button>
      ))}
    </div>
  );
}

export function ModelList({ models, onAdd, onEdit, onDelete, onSetDefault }: Props) {
  const [activeTab, setActiveTab] = useState<ModelTabKey>('models');

  const renderModelGrid = () => (
    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
      {/* Add card */}
      {onAdd && (
        <div
          onClick={onAdd}
          style={{
            width: 100,
            minHeight: 120,
            border: '1px dashed #2a3140',
            borderRadius: 8,
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            cursor: 'pointer',
            background: 'rgba(42,49,64,0.2)',
          }}
        >
          <div style={{ fontSize: 24, color: '#8b93a7' }}>+</div>
          <div style={{ fontSize: 11, color: '#8b93a7', marginTop: 4 }}>新建模型</div>
        </div>
      )}

      {/* Model cards */}
      {models.map((m) => {
        const { icon, label } = resolveProvider(m.provider);
        return (
          <div
            key={m.id}
            onClick={() => onEdit?.(m.id)}
            style={{
              width: 100,
              minHeight: 120,
              border: `1px solid ${m.isDefault ? '#5b8cff' : '#2a3140'}`,
              borderRadius: 8,
              padding: 8,
              cursor: 'pointer',
              background: m.isDefault ? 'rgba(91,140,255,0.08)' : 'rgba(42,49,64,0.2)',
              position: 'relative',
            }}
          >
            <div style={{ fontSize: 20 }}>{icon}</div>
            <div style={{ fontSize: 12, fontWeight: 500, color: '#e8eaef', marginTop: 4 }}>
              {m.name}
            </div>
            <div style={{ fontSize: 10, color: '#8b93a7' }}>{label}</div>
            <div style={{ fontSize: 9, color: '#5a6478', marginTop: 2 }}>{m.id}</div>

            {m.isDefault && (
              <span style={{ position: 'absolute', top: 4, right: 4, background: '#5b8cff', color: '#fff', borderRadius: 3, fontSize: 9, padding: '1px 5px' }}>
                默认
              </span>
            )}

            {/* Actions */}
            <div style={{ position: 'absolute', bottom: 4, right: 4, display: 'flex', gap: 2, opacity: 0.6 }}
              onMouseEnter={(e) => (e.currentTarget.style.opacity = '1')}
              onMouseLeave={(e) => (e.currentTarget.style.opacity = '0.6')}
            >
              {!m.isDefault && onSetDefault && (
                <button onClick={(e) => { e.stopPropagation(); onSetDefault(m.id); }}
                  style={{ background: 'rgba(91,140,255,0.2)', border: 'none', borderRadius: 3, color: '#5b8cff', cursor: 'pointer', fontSize: 9, padding: '1px 5px' }}>
                  默认
                </button>
              )}
              {onDelete && (
                <button onClick={(e) => { e.stopPropagation(); onDelete(m.id); }}
                  style={{ background: 'rgba(229,57,53,0.2)', border: 'none', borderRadius: 3, color: '#e53935', cursor: 'pointer', fontSize: 9, padding: '1px 5px' }}>
                  删除
                </button>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );

  return (
    <div>
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
        {MODEL_TABS.map((tab) => (
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
      {activeTab === 'models' ? renderModelGrid() : <RenderCostStats />}
    </div>
  );
}
