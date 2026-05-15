/**
 * ModelEditForm — React replacement for class-based ModelEditForm.
 * Create/edit AI model configuration (provider, model ID, base URL, API key).
 */
import { useState, useEffect, useCallback, useRef } from 'react';
import { ModalPanel } from './ModalPanel';
import type { ProviderInfo } from '../types';
import * as api from '../api';

export interface ModelFormData {
  id: string;
  provider: string;
  model: string;
  name: string;
  baseUrl: string;
  apiKey: string;
  isDefault: boolean;
}

interface Props {
  modelId?: string;
  initialData?: Partial<ModelFormData>;
  providers: ProviderInfo[];
  onSubmit: (data: ModelFormData) => Promise<void>;
  onCancel: () => void;
}

const PROVIDER_EMOJI: Record<string, string> = {
  openai:              '🤖',
  anthropic:           '🧠',
  gemini:              '🔴',
  ollama:              '🦙',
  groq:                '⚡',
  deepseek:            '🌊',
  azure:               '☁️',
  mistral:             '🌬️',
  cohere:              '🌐',
  openrouter:          '🌀',
  nous:                '🌀',
  openai_codex:        '🤖',
  qwen_oauth:          '🌀',
  google_gemini_cli:   '🔴',
  lmstudio:            '💻',
  copilot:             '💻',
  copilot_acp:         '💻',
  zai:                 '🌊',
  kimi_coding:         '🌊',
  kimi_coding_cn:      '🌊',
  stepfun:             '🌊',
  arcee:               '🧠',
  gmi:                 '🌊',
  minimax:             '🌊',
  minimax_oauth:       '🌊',
  minimax_cn:          '🌊',
  alibaba:             '☁️',
  alibaba_coding_plan: '☁️',
  xai:                 '🌊',
  nvidia:              '⚡',
  ai_gateway:          '🌀',
  opencode_zen:        '🌀',
  opencode_go:         '🌀',
  kilocode:            '🌀',
  huggingface:         '🤗',
  xiaomi:              '🌊',
  tencent_tokenhub:    '🌊',
  ollama_cloud:        '🦙',
  bedrock:             '☁️',
  azure_foundry:       '☁️',
};

const FALLBACK_EMOJI = '🔮';

function providerEmoji(id: string): string {
  return PROVIDER_EMOJI[id] ?? FALLBACK_EMOJI;
}

export function ModelEditForm({ modelId, initialData, providers, onSubmit, onCancel }: Props) {
  const rawProv = (initialData?.provider ?? '').trim();
  const matchedInitial = providers.find(
    (p) => p.id === rawProv || p.id.toLowerCase() === rawProv.toLowerCase(),
  );
  const defaultUrl = matchedInitial?.inferenceBaseUrl ?? '';

  const [selectedProvider, setSelectedProvider] = useState(matchedInitial ? matchedInitial.id : (rawProv || 'openai'));
  const [model, setModel] = useState(initialData?.model ?? '');
  const [baseUrl, setBaseUrl] = useState(initialData?.baseUrl ?? defaultUrl);
  const [apiKey, setApiKey] = useState(initialData?.apiKey ?? '');
  const [isDefault, setIsDefault] = useState(initialData?.isDefault ?? false);
  const [customName, setCustomName] = useState(selectedProvider === '__custom__' ? rawProv : '');
  const [errorText, setErrorText] = useState('');

  const [modelOptions, setModelOptions] = useState<string[]>([]);
  const [modelLoading, setModelLoading] = useState(false);

  const fetchTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const isEdit = !!modelId;
  const isMainModel = modelId === 'main' || !modelId;
  const isCustomProvider = selectedProvider === '__custom__';

  const fetchModels = useCallback(async (prov: string, key: string, base: string) => {
    setModelLoading(true);
    setModelOptions([]);
    try {
      const result = await api.apiProbeProviderModels(
        prov,
        key || undefined,
        base || undefined,
      );
      setModelOptions(result.models);
      if (result.suggestedBaseUrl && !baseUrl) {
        setBaseUrl(result.suggestedBaseUrl);
      }
    } catch {
      setModelOptions([]);
    } finally {
      setModelLoading(false);
    }
  }, [baseUrl]);

  // Auto-fetch models when switching to a known provider
  useEffect(() => {
    if (isCustomProvider) {
      setModelOptions([]);
      return;
    }
    fetchModels(selectedProvider, apiKey, baseUrl);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedProvider]);

  const handleProviderChange = useCallback(async (prov: string) => {
    setSelectedProvider(prov);
    setModel('');
    setModelOptions([]);

    if (prov === '__custom__') {
      setBaseUrl('');
      setApiKey('');
      setCustomName('');
      return;
    }

    const newProv = providers.find((p) => p.id === prov);
    if (newProv?.inferenceBaseUrl) {
      setBaseUrl(newProv.inferenceBaseUrl);
    }

    // Auto-fill API key from env
    try {
      const envInfo = await api.apiGetProviderEnvkey(prov);
      if (envInfo.envVarValue) {
        setApiKey(envInfo.envVarValue);
      }
    } catch {
      // Not found; leave as-is
    }
  }, [providers]);

  // Debounced model probing when API key is typed
  useEffect(() => {
    if (fetchTimerRef.current) clearTimeout(fetchTimerRef.current);
    if (!isCustomProvider && apiKey.trim()) {
      fetchTimerRef.current = setTimeout(() => {
        fetchModels(selectedProvider, apiKey, baseUrl);
      }, 500);
    }
    return () => {
      if (fetchTimerRef.current) clearTimeout(fetchTimerRef.current);
    };
  }, [apiKey, selectedProvider, baseUrl, isCustomProvider, fetchModels]);

  const validate = (): boolean => {
    if (!selectedProvider || selectedProvider === '__custom__' && !customName.trim()) {
      setErrorText('请选择或输入提供商');
      return false;
    }
    if (!model.trim()) {
      setErrorText('模型 ID 不能为空');
      return false;
    }
    if (isCustomProvider) {
      if (!baseUrl.trim()) {
        setErrorText('自定义厂商必须填写 API Base URL');
        return false;
      }
      if (!apiKey.trim()) {
        setErrorText('自定义厂商必须填写 API Key');
        return false;
      }
    }
    setErrorText('');
    return true;
  };

  const handleSubmit = async () => {
    if (!validate()) return;
    const effectiveProvider = isCustomProvider
      ? customName.trim().toLowerCase().replace(/\s+/g, '-')
      : selectedProvider;
    const formData: ModelFormData = {
      id: modelId ?? '',
      provider: effectiveProvider || 'openai',
      model: model.trim(),
      name: '',
      baseUrl: baseUrl.trim(),
      apiKey: apiKey.trim(),
      isDefault: isMainModel ? isDefault : false,
    };
    await onSubmit(formData);
  };

  const knownIds = new Set(providers.map((p) => p.id));
  const currentKnown = knownIds.has(selectedProvider);

  const labelStyle: React.CSSProperties = {
    fontSize: 11,
    color: '#8b93a7',
    display: 'block',
    marginBottom: 4,
  };
  const inputStyle: React.CSSProperties = {
    width: '100%',
    padding: '8px',
    background: '#0f1218',
    border: '1px solid #2a3140',
    borderRadius: 6,
    color: '#e8eaef',
    fontSize: 13,
    boxSizing: 'border-box',
  };

  return (
    <ModalPanel
      title={isEdit ? '编辑模型' : '新建模型'}
      icon="🔌"
      maxWidth="32rem"
      onClose={onCancel}
    >
      <div style={{ padding: '4px 0' }}>
        {/* Error banner */}
        {errorText && (
          <div style={{
            display: 'flex', alignItems: 'center', gap: 8, padding: '8px 12px',
            background: 'rgba(127,29,29,0.4)', border: '1px solid rgba(127,29,29,0.5)',
            borderRadius: 6, fontSize: 11, color: '#fca5a5', marginBottom: 16,
          }}>
            <span>⚠️</span><span>{errorText}</span>
          </div>
        )}

        {/* Provider row */}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginBottom: 12 }}>
          <div>
            <label style={labelStyle}>
              🏭 提供商 <span style={{ color: '#f87171' }}>*</span>
            </label>
            <select
              value={selectedProvider}
              onChange={(e) => handleProviderChange(e.target.value)}
              style={{ ...inputStyle, cursor: 'pointer' }}
            >
              <option value="__custom__">🔧 自定义（Custom）</option>
              {selectedProvider && !currentKnown && selectedProvider !== '__custom__' && (
                <option value={selectedProvider}>
                  {providerEmoji(selectedProvider)} {selectedProvider}
                </option>
              )}
              {providers.map((p) => (
                <option key={p.id} value={p.id}>
                  {providerEmoji(p.id)} {p.name}
                </option>
              ))}
            </select>
          </div>
          {isCustomProvider && (
            <div>
              <label style={labelStyle}>
                🔧 自定义名称 <span style={{ color: '#f87171' }}>*</span>
              </label>
              <input
                type="text"
                placeholder="如 majiabin"
                value={customName}
                onChange={(e) => setCustomName(e.target.value)}
                style={inputStyle}
              />
            </div>
          )}
        </div>

        {/* Base URL */}
        <div style={{ marginBottom: 12 }}>
          <label style={labelStyle}>
            🔗 API Base URL{' '}
            <span style={{
              fontSize: 10,
              color: isCustomProvider ? '#f87171' : '#475569',
            }}>
              {isCustomProvider ? '（必填）' : '（可选）'}
            </span>
          </label>
          <input
            type="text"
            placeholder={isCustomProvider ? 'https://api.example.com/v1' : '留空用默认值'}
            value={baseUrl}
            onChange={(e) => setBaseUrl(e.target.value)}
            style={inputStyle}
          />
        </div>

        {/* API Key */}
        <div style={{ marginBottom: 12 }}>
          <label style={labelStyle}>
            🔐 API Key{' '}
            <span style={{ fontSize: 10, color: '#475569' }}>
              {isCustomProvider ? '（必填）' : '（环境变量，不落盘）'}
            </span>
          </label>
          <input
            type="password"
            placeholder={isCustomProvider ? 'sk-...（必填）' : 'sk-...（留空沿用环境变量）'}
            value={apiKey}
            onChange={(e) => setApiKey(e.target.value)}
            style={inputStyle}
          />
        </div>

        {/* Model ID */}
        <div style={{ marginBottom: 12 }}>
          <label style={labelStyle}>
            🤖 模型 ID <span style={{ color: '#f87171' }}>*</span>
          </label>
          <select
            value={modelOptions.includes(model) ? model : ''}
            onChange={(e) => { if (e.target.value) setModel(e.target.value); }}
            style={{ ...inputStyle, background: '#1a2230', cursor: 'pointer', marginBottom: 6 }}
          >
            {modelLoading
              ? <option value="">⏳ 探测中…</option>
              : modelOptions.length === 0
                ? <option value="">— 输入或选择模型 —</option>
                : <option value="">— 选择模型 —</option>
            }
            {modelOptions.map((m) => (
              <option key={m} value={m}>{m}</option>
            ))}
          </select>
          <input
            type="text"
            placeholder="gpt-4o / claude-3-5-sonnet-20241022（手动输入）"
            value={model}
            onChange={(e) => setModel(e.target.value)}
            style={inputStyle}
          />
        </div>

        {/* Default checkbox (main model only) */}
        {isMainModel && (
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12 }}>
            <label style={{ display: 'flex', alignItems: 'center', gap: 6, cursor: 'pointer' }}>
              <input
                type="checkbox"
                checked={isDefault}
                onChange={(e) => setIsDefault(e.target.checked)}
                style={{ accentColor: '#5b8cff', width: 15, height: 15 }}
              />
              <span style={{ fontSize: 13, color: '#e8eaef' }}>设为默认主模型</span>
            </label>
          </div>
        )}

        {/* Footer */}
        <div style={{
          display: 'flex', justifyContent: 'flex-end', gap: 12,
          padding: '12px 0 0', borderTop: '1px solid #2a3140', marginTop: 16,
        }}>
          <button
            onClick={onCancel}
            style={{
              padding: '8px 16px', background: 'transparent', border: '1px solid #2a3140',
              borderRadius: 6, color: '#8b93a7', cursor: 'pointer', fontSize: 13,
            }}
          >
            取消
          </button>
          <button
            onClick={handleSubmit}
            style={{
              display: 'flex', alignItems: 'center', gap: 8, padding: '8px 20px',
              background: '#5b8cff', border: 'none', borderRadius: 6, color: 'white',
              cursor: 'pointer', fontSize: 13, fontWeight: 500,
            }}
          >
            {isEdit ? '💾 保存修改' : '✅ 确认创建'}
          </button>
        </div>
      </div>
    </ModalPanel>
  );
}
