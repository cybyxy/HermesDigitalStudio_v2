/**
 * AgentEditForm — React replacement for class-based AgentEditForm.
 * Create/edit Agent persona with animated sprite avatar picker.
 */
import { useState, useEffect, useRef, useCallback } from 'react';
import { ModalPanel } from './ModalPanel';
import {
  PERSON_FRAME_W,
  PERSON_FRAME_H,
  getPersonSheetUrl,
  getSpriteBasesByGender,
} from '../ui/personSprites';

export interface AgentFormData {
  profile: string;
  displayName: string;
  avatar: string;
  gender: 'male' | 'female';
  personality: string;
  catchphrases: string;
  memes: string;
  identity: string;
  style: string;
  defaults: string;
  avoid: string;
  coreTruths: string;
}

interface Props {
  agentId?: string;
  initialData?: Partial<AgentFormData>;
  onSubmit: (data: AgentFormData) => Promise<void>;
  onCancel: () => void;
}

export function AgentEditForm({ agentId, initialData, onSubmit, onCancel }: Props) {
  const isEdit = !!agentId;

  const [displayName, setDisplayName] = useState(initialData?.displayName ?? '');
  const [profile, setProfile] = useState(initialData?.profile ?? '');
  const [gender, setGender] = useState<'male' | 'female'>(initialData?.gender ?? 'male');
  const [avatar, setAvatar] = useState(initialData?.avatar ?? '');

  // Persona tab fields
  const [identity, setIdentity] = useState(initialData?.identity ?? '');
  const [style, setStyle] = useState(initialData?.style ?? '');
  const [defaults, setDefaults] = useState(initialData?.defaults ?? '');
  const [avoid, setAvoid] = useState(initialData?.avoid ?? '');
  const [coreTruths, setCoreTruths] = useState(initialData?.coreTruths ?? '');

  // Role tab fields
  const [personality, setPersonality] = useState(initialData?.personality ?? '');
  const [catchphrases, setCatchphrases] = useState(initialData?.catchphrases ?? '');
  const [memes, setMemes] = useState(initialData?.memes ?? '');

  const [activeTab, setActiveTab] = useState<'persona' | 'role'>('persona');
  const [errorText, setErrorText] = useState('');

  // Sync all field states when initialData prop changes (e.g. API returns agent detail)
  useEffect(() => {
    if (!initialData) return;
    setDisplayName(initialData.displayName ?? '');
    setProfile(initialData.profile ?? '');
    setGender(initialData.gender ?? 'male');
    setAvatar(initialData.avatar ?? '');
    setIdentity(initialData.identity ?? '');
    setStyle(initialData.style ?? '');
    setDefaults(initialData.defaults ?? '');
    setAvoid(initialData.avoid ?? '');
    setCoreTruths(initialData.coreTruths ?? '');
    setPersonality(initialData.personality ?? '');
    setCatchphrases(initialData.catchphrases ?? '');
    setMemes(initialData.memes ?? '');
    setErrorText('');
  }, [initialData]);

  // --- Avatar picker animation ---
  const animTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const [animFrame, setAnimFrame] = useState(0);
  const imgCacheRef = useRef(new Map<string, HTMLImageElement>());
  const [bases, setBases] = useState<string[]>(() => getSpriteBasesByGender(gender));

  const startAnim = useCallback(() => {
    stopAnim();
    setAnimFrame(0);
    animTimerRef.current = setInterval(() => {
      setAnimFrame((prev) => (prev + 1) % 3);
    }, 300);
  }, []);

  const stopAnim = useCallback(() => {
    if (animTimerRef.current) {
      clearInterval(animTimerRef.current);
      animTimerRef.current = null;
    }
  }, []);

  useEffect(() => {
    startAnim();
    return stopAnim;
  }, [startAnim, stopAnim]);

  const handleGenderChange = useCallback((g: 'male' | 'female') => {
    setGender(g);
    setAvatar('');
    setBases(getSpriteBasesByGender(g));
    imgCacheRef.current.clear();
    // Reset animation
    stopAnim();
    startAnim();
  }, [startAnim, stopAnim]);

  const validate = (): boolean => {
    if (!isEdit && !profile.trim()) {
      setErrorText('Profile 名称不能为空');
      return false;
    }
    if (!displayName.trim()) {
      setErrorText('显示名称不能为空');
      return false;
    }
    if (!avatar) {
      setErrorText('请选择一个人物形象');
      return false;
    }
    setErrorText('');
    return true;
  };

  const handleSubmit = async () => {
    const formData: AgentFormData = {
      profile: profile.trim(),
      displayName: displayName.trim(),
      avatar,
      gender,
      personality: personality.trim(),
      catchphrases: catchphrases.trim(),
      memes: memes.trim(),
      identity: identity.trim(),
      style: style.trim(),
      defaults: defaults.trim(),
      avoid: avoid.trim(),
      coreTruths: coreTruths.trim(),
    };
    if (!validate()) return;
    stopAnim();
    await onSubmit(formData);
  };

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
  const textareaStyle: React.CSSProperties = {
    ...inputStyle,
    fontSize: 12,
    resize: 'none' as const,
  };

  return (
    <ModalPanel
      title={isEdit ? '编辑 Agent' : '新建 Agent'}
      icon="👤"
      maxWidth="32rem"
      onClose={() => { stopAnim(); onCancel(); }}
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

        {/* Name fields */}
        <div style={{ display: 'grid', gridTemplateColumns: isEdit ? '1fr' : '1fr 1fr', gap: 12, marginBottom: 16 }}>
          {!isEdit && (
            <div>
              <label style={labelStyle}>
                🏷️ Profile 名字 <span style={{ color: '#f87171' }}>*</span>
              </label>
              <input
                type="text"
                placeholder="例如: chengdu-advisor"
                value={profile}
                onChange={(e) => setProfile(e.target.value)}
                style={inputStyle}
              />
            </div>
          )}
          <div>
            <label style={labelStyle}>
              ✨ 显示名称 <span style={{ color: '#f87171' }}>*</span>
            </label>
            <input
              type="text"
              placeholder="例如: 成都活地图"
              value={displayName}
              onChange={(e) => setDisplayName(e.target.value)}
              style={inputStyle}
            />
          </div>
        </div>

        {/* Gender + Avatar picker */}
        <div style={{ marginBottom: 16 }}>
          <label style={labelStyle}>🧑 性别</label>
          <div style={{ display: 'flex', gap: 12, marginBottom: 8 }}>
            <label style={{ display: 'flex', alignItems: 'center', gap: 6, cursor: 'pointer', fontSize: 13, color: '#e8eaef' }}>
              <input
                type="radio"
                name="agent-gender"
                value="male"
                checked={gender === 'male'}
                onChange={() => handleGenderChange('male')}
                style={{ accentColor: '#5b8cff', width: 14, height: 14 }}
              />
              男
            </label>
            <label style={{ display: 'flex', alignItems: 'center', gap: 6, cursor: 'pointer', fontSize: 13, color: '#e8eaef' }}>
              <input
                type="radio"
                name="agent-gender"
                value="female"
                checked={gender === 'female'}
                onChange={() => handleGenderChange('female')}
                style={{ accentColor: '#5b8cff', width: 14, height: 14 }}
              />
              女
            </label>
          </div>

          <label style={labelStyle}>🧑 人物形象</label>
          <div style={{
            display: 'flex', flexWrap: 'wrap', gap: 6, padding: 8,
            background: '#0f1218', border: '1px solid #2a3140',
            borderRadius: 6, maxHeight: 200, overflowY: 'auto',
          }}>
            {bases.map((base) => (
              <AvatarThumbnail
                key={base}
                base={base}
                selected={avatar === base}
                animFrame={animFrame}
                imgCache={imgCacheRef}
                onSelect={(b) => setAvatar(b)}
              />
            ))}
          </div>
        </div>

        {/* Tab switcher */}
        <div style={{ display: 'flex', borderBottom: '1px solid #2a3140', marginBottom: 16 }}>
          <button
            onClick={() => setActiveTab('persona')}
            style={{
              padding: '8px 16px', background: 'transparent', border: 'none',
              borderBottom: activeTab === 'persona' ? '2px solid #5b8cff' : '2px solid transparent',
              color: activeTab === 'persona' ? '#5b8cff' : '#8b93a7',
              cursor: 'pointer', fontSize: 13, fontWeight: 500,
            }}
          >
            🧠 核心设定
          </button>
          <button
            onClick={() => setActiveTab('role')}
            style={{
              padding: '8px 16px', background: 'transparent', border: 'none',
              borderBottom: activeTab === 'role' ? '2px solid #5b8cff' : '2px solid transparent',
              color: activeTab === 'role' ? '#5b8cff' : '#8b93a7',
              cursor: 'pointer', fontSize: 13, marginLeft: 4,
            }}
          >
            🎭 角色设定
          </button>
        </div>

        {/* Persona panel */}
        {activeTab === 'persona' && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            <div>
              <label style={{ ...labelStyle, color: '#5b8cff' }}>🏠 Identity 身份</label>
              <textarea
                rows={2}
                placeholder="你是谁，你叫什么，核心定位是什么"
                value={identity}
                onChange={(e) => setIdentity(e.target.value)}
                style={textareaStyle}
              />
            </div>
            <div>
              <label style={{ ...labelStyle, color: '#5b8cff' }}>🎨 Style 风格</label>
              <textarea
                rows={2}
                placeholder="语言特点、语调、视觉美学"
                value={style}
                onChange={(e) => setStyle(e.target.value)}
                style={textareaStyle}
              />
            </div>
            <div>
              <label style={{ ...labelStyle, color: '#5b8cff' }}>📍 Defaults 默认行为</label>
              <textarea
                rows={2}
                placeholder="场景感知、响应协议"
                value={defaults}
                onChange={(e) => setDefaults(e.target.value)}
                style={textareaStyle}
              />
            </div>
            <div>
              <label style={{ ...labelStyle, color: '#5b8cff' }}>🚫 Avoid 避免行为</label>
              <textarea
                rows={2}
                placeholder="需要规避的内容"
                value={avoid}
                onChange={(e) => setAvoid(e.target.value)}
                style={textareaStyle}
              />
            </div>
            <div>
              <label style={{ ...labelStyle, color: '#5b8cff' }}>🏛️ Core Truths 核心真理</label>
              <textarea
                rows={2}
                placeholder="你的终极行为准则和世界观"
                value={coreTruths}
                onChange={(e) => setCoreTruths(e.target.value)}
                style={textareaStyle}
              />
            </div>
          </div>
        )}

        {/* Role panel */}
        {activeTab === 'role' && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            <div>
              <label style={{ ...labelStyle, color: '#5b8cff' }}>
                🧠 性格特点（全部注入 System Prompt）
              </label>
              <textarea
                rows={3}
                placeholder="例如：活泼开朗、喜欢用emoji、说话带川普味..."
                value={personality}
                onChange={(e) => setPersonality(e.target.value)}
                style={textareaStyle}
              />
            </div>
            <div>
              <label style={{ ...labelStyle, color: '#5b8cff' }}>
                💬 口头禅（每行一条，推理时随机选一条）
              </label>
              <textarea
                rows={3}
                placeholder={"每行一条，例如：\n嘛事儿\n要得嘛\n巴适得很"}
                value={catchphrases}
                onChange={(e) => setCatchphrases(e.target.value)}
                style={textareaStyle}
              />
            </div>
            <div>
              <label style={{ ...labelStyle, color: '#5b8cff' }}>
                🔥 梗语（每行一条，推理时60%概率随机选一条）
              </label>
              <textarea
                rows={3}
                placeholder={"每行一条，例如：\n我太难了\n绝绝子\nyyds"}
                value={memes}
                onChange={(e) => setMemes(e.target.value)}
                style={textareaStyle}
              />
            </div>
          </div>
        )}

        {/* Footer */}
        <div style={{
          display: 'flex', justifyContent: 'flex-end', gap: 12,
          padding: '12px 0 0', borderTop: '1px solid #2a3140', marginTop: 16,
        }}>
          <button
            onClick={() => { stopAnim(); onCancel(); }}
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

/* ------------------------------------------------------------------ */
/*  AvatarThumbnail — pixel-art canvas with animated spritesheet       */
/* ------------------------------------------------------------------ */
function AvatarThumbnail({
  base,
  selected,
  animFrame,
  imgCache,
  onSelect,
}: {
  base: string;
  selected: boolean;
  animFrame: number;
  imgCache: React.MutableRefObject<Map<string, HTMLImageElement>>;
  onSelect: (base: string) => void;
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const loadedRef = useRef(false);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const existing = imgCache.current.get(base);
    if (existing) {
      loadedRef.current = true;
      drawFrame(canvas, existing, animFrame);
    } else {
      const img = new Image();
      img.onload = () => {
        imgCache.current.set(base, img);
        loadedRef.current = true;
        if (canvasRef.current === canvas) {
          drawFrame(canvas, img, animFrame);
        }
      };
      img.src = getPersonSheetUrl(base);
    }
  }, [base, imgCache]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const img = imgCache.current.get(base);
    if (img) {
      drawFrame(canvas, img, animFrame);
    }
  }, [animFrame, base, imgCache]);

  return (
    <canvas
      ref={canvasRef}
      width={PERSON_FRAME_W}
      height={PERSON_FRAME_H}
      data-base={base}
      onClick={() => onSelect(base)}
      style={{
        imageRendering: 'pixelated' as React.CSSProperties['imageRendering'],
        cursor: 'pointer',
        border: `2px solid ${selected ? '#5b8cff' : '#2a3140'}`,
        borderRadius: 4,
        background: '#0c0e12',
        display: 'block',
      }}
    />
  );
}

function drawFrame(
  canvas: HTMLCanvasElement,
  img: HTMLImageElement,
  frame: number,
): void {
  const ctx = canvas.getContext('2d');
  if (!ctx) return;
  ctx.imageSmoothingEnabled = false;
  ctx.clearRect(0, 0, PERSON_FRAME_W, PERSON_FRAME_H);
  ctx.drawImage(
    img,
    frame * PERSON_FRAME_W, 0, PERSON_FRAME_W, PERSON_FRAME_H,
    0, 0, PERSON_FRAME_W, PERSON_FRAME_H,
  );
}
