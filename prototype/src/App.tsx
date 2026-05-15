import { useState, useEffect, useCallback } from 'react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import {
  X, ChevronLeft, ChevronRight, Send, Mic, MicOff,
  Settings, Trash2, Plus, RefreshCw, Zap, Brain,
  MessageSquare, Users, Wrench, BarChart3, FolderOpen,
  Database, Activity, ChevronDown, ChevronUp, Check, Star
} from 'lucide-react';

// Types
interface Agent {
  id: string; name: string; role: string; avatar: string; color: string;
  model: string; online: boolean; satiety: number; bioCurrent: number;
  emotion: { valence: number; arousal: number; dominance: number };
}
interface ChatMessage {
  id: string; role: 'user' | 'assistant' | 'tool' | 'thinking';
  content: string; agentId?: string; timestamp: string; streaming?: boolean;
  toolName?: string; toolResult?: string;
}
interface PlanStep { id: number; title: string; status: 'done' | 'active' | 'pending'; }
interface Skill { name: string; desc: string; category: string; enabled: boolean; }

// Data
const agents: Agent[] = [
  { id: 'alice', name: 'Alice', role: '程序员', avatar: '/alice.png', color: '#a78bfa', model: 'GPT-4o', online: true, satiety: 75, bioCurrent: 4, emotion: { valence: 0.7, arousal: 0.3, dominance: 0.5 } },
  { id: 'bob', name: 'Bob', role: '安全专家', avatar: '/bob.png', color: '#60a5fa', model: 'Claude 3.5', online: true, satiety: 45, bioCurrent: 7, emotion: { valence: 0.2, arousal: 0.8, dominance: 0.6 } },
  { id: 'clio', name: 'Clio', role: '设计师', avatar: '/clio.png', color: '#f472b6', model: 'GPT-4o', online: true, satiety: 90, bioCurrent: 2, emotion: { valence: 0.9, arousal: 0.1, dominance: 0.3 } },
  { id: 'dave', name: 'Dave', role: '运维', avatar: '', color: '#34d399', model: 'Llama 3.2', online: false, satiety: 60, bioCurrent: 5, emotion: { valence: 0.4, arousal: 0.5, dominance: 0.4 } },
  { id: 'eve', name: 'Eve', role: '数据分析师', avatar: '', color: '#fbbf24', model: 'Gemini Pro', online: true, satiety: 82, bioCurrent: 3, emotion: { valence: 0.6, arousal: 0.4, dominance: 0.5 } },
  { id: 'frank', name: 'Frank', role: '文案', avatar: '', color: '#fb923c', model: 'GPT-4o', online: true, satiety: 55, bioCurrent: 6, emotion: { valence: 0.5, arousal: 0.6, dominance: 0.4 } },
];

const planSteps: PlanStep[] = [
  { id: 1, title: '代码安全扫描', status: 'done' },
  { id: 2, title: '漏洞分析与评估', status: 'active' },
  { id: 3, title: '生成修复方案', status: 'pending' },
  { id: 4, title: '文档更新与归档', status: 'pending' },
];

const skills: Skill[] = [
  { name: 'Git 操作', desc: '代码版本管理与协作', category: '开发工具', enabled: true },
  { name: 'Debug 助手', desc: '智能调试与错误分析', category: '开发工具', enabled: true },
  { name: '每日提醒', desc: '定时任务与日程提醒', category: '日常辅助', enabled: true },
  { name: '天气查询', desc: '实时天气信息获取', category: '日常辅助', enabled: false },
  { name: '安全审计', desc: '代码安全漏洞扫描', category: '安全', enabled: true },
  { name: '文件管理', desc: '智能文件整理与分类', category: '日常辅助', enabled: true },
];

const initialMessages: ChatMessage[] = [
  { id: '1', role: 'user', content: '帮我分析一下这个项目的安全性', timestamp: '10:25' },
  { id: '2', role: 'thinking', content: '正在分析项目结构，检查依赖项...', agentId: 'alice', timestamp: '10:25' },
  { id: '3', role: 'tool', content: '已扫描 127 个文件', toolName: 'search_codebase', toolResult: '发现 3 个潜在安全问题', agentId: 'alice', timestamp: '10:25' },
  { id: '4', role: 'assistant', content: '经过初步扫描，我发现以下安全问题需要关注：\n\n1. **依赖漏洞**: lodash 版本过低，存在原型污染风险\n2. **XSS 风险**: 用户输入未经过滤直接渲染\n3. **配置泄露**: .env 文件被意外提交到版本库\n\n建议优先修复第 1 和第 2 项。', agentId: 'alice', timestamp: '10:26' },
  { id: '5', role: 'user', content: '那先帮我修复 lodash 的依赖问题', timestamp: '10:27' },
  { id: '6', role: 'assistant', content: '好的，我来更新 lodash 到最新版本并检查兼容性...', agentId: 'alice', timestamp: '10:27', streaming: true },
];

const modelList = [
  { name: 'GPT-4o', provider: 'OpenAI', isDefault: true, providerIcon: '🔷' },
  { name: 'Claude 3.5 Sonnet', provider: 'Anthropic', isDefault: false, providerIcon: '🧠' },
  { name: 'Llama 3.2', provider: 'Ollama', isDefault: false, providerIcon: '🏠' },
  { name: 'Gemini Pro', provider: 'Google', isDefault: false, providerIcon: '🔺' },
  { name: 'DeepSeek V3', provider: 'DeepSeek', isDefault: false, providerIcon: '🔍' },
];

const channelList = [
  { platform: 'feishu', name: '飞书工作群', icon: '🐦', status: 'connected', agentId: 'alice' },
  { platform: 'telegram', name: 'Telegram Bot', icon: '✈️', status: 'connected', agentId: 'bob' },
  { platform: 'discord', name: 'Discord 服务器', icon: '🎮', status: 'disconnected', agentId: null },
];

const plansData = [
  { id: 1, name: '安全审计', status: 'active', progress: 50, agent: 'Alice', time: '10:25' },
  { id: 2, name: '性能优化', status: 'pending', progress: 0, agent: 'Dave', time: '09:30' },
  { id: 3, name: 'UI 重构', status: 'done', progress: 100, agent: 'Clio', time: '昨天' },
];

export default function App() {
  // Panel state
  const [leftCollapsed, setLeftCollapsed] = useState(false);
  const [rightCollapsed, setRightCollapsed] = useState(false);
  const [dockOpen, setDockOpen] = useState(false);
  const [dockTab, setDockTab] = useState<string>('agents');

  // Modal state
  const [showAgentEdit, setShowAgentEdit] = useState(false);
  const [showModelEdit, setShowModelEdit] = useState(false);
  const [showMemoryDetail, setShowMemoryDetail] = useState(false);
  const [memoryAgent, setMemoryAgent] = useState<Agent>(agents[0]);

  // Chat state
  const [messages, setMessages] = useState<ChatMessage[]>(initialMessages);
  const [inputText, setInputText] = useState('');
  const [activeAgent, setActiveAgent] = useState<Agent>(agents[0]);

  // Small thought
  const [smallThought, setSmallThought] = useState<{ agent: Agent; content: string } | null>(null);

  // Agent edit form
  const [editingAgent, setEditingAgent] = useState<Agent | null>(null);
  const [editTab, setEditTab] = useState<'persona' | 'role'>('persona');

  // Settings modal
  const [showSettings, setShowSettings] = useState(false);

  // Handle dock toggle
  const toggleDock = (tab: string) => {
    if (dockOpen && dockTab === tab) { setDockOpen(false); return; }
    setDockTab(tab);
    setDockOpen(true);
  };

  // Handle model edit
  const [editingModel, setEditingModel] = useState<any>(null);
  const [modelForm, setModelForm] = useState({ name: '', provider: 'openai', apiKey: '', baseUrl: '' });

  // Small thought auto-trigger
  useEffect(() => {
    const timer = setTimeout(() => {
      const ev = agents.find(a => a.id === 'eve');
      if (ev) setSmallThought({ agent: ev, content: '我觉得主人可能还需要一份数据趋势分析报告，最近的项目数据变化很大...' });
    }, 8000);
    const hide = setTimeout(() => setSmallThought(null), 13000);
    return () => { clearTimeout(timer); clearTimeout(hide); };
  }, []);

  // Send message
  const handleSend = useCallback(() => {
    if (!inputText.trim()) return;
    const newMsg: ChatMessage = { id: Date.now().toString(), role: 'user', content: inputText, timestamp: new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' }) };
    setMessages(prev => [...prev, newMsg]);
    setInputText('');
    setTimeout(() => {
      const reply: ChatMessage = {
        id: (Date.now() + 1).toString(), role: 'assistant', content: '收到，我来处理...', agentId: activeAgent.id,
        timestamp: new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' }),
        streaming: true
      };
      setMessages(prev => [...prev, reply]);
      setTimeout(() => {
        setMessages(prev => prev.map(m => m.id === reply.id ? { ...m, content: '已经为你生成了分析报告。需要我详细展开哪个部分？', streaming: false } : m));
      }, 2000);
    }, 600);
  }, [inputText, activeAgent]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend(); }
  };

  const getEmotionColor = (valence: number) => {
    if (valence > 0.3) return '#22c55e';
    if (valence < -0.3) return '#ef4444';
    return '#fbbf24';
  };

  return (
    <div style={{ height: '100vh', display: 'flex', flexDirection: 'column', background: '#0c0e12', color: '#e8eaef', fontFamily: "system-ui, -apple-system, sans-serif", fontSize: 12 }}>
      {/* Main content area */}
      <div style={{ flex: 1, display: 'flex', overflow: 'hidden' }}>
        {/* Left Panel */}
        {!leftCollapsed && (
          <div style={{ width: 260, minWidth: 260, background: '#141820', borderRight: '1px solid #2a3140', display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
            <div style={{ padding: '12px 16px', borderBottom: '1px solid #2a3140', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <span style={{ fontWeight: 600, fontSize: 13 }}>计划时间线</span>
              <Button variant="ghost" size="iconSm" onClick={() => setLeftCollapsed(true)}><ChevronLeft size={14} /></Button>
            </div>
            <div style={{ flex: 1, overflow: 'auto', padding: 12 }}>
              {/* Plan header */}
              <div style={{ marginBottom: 16 }}>
                <div style={{ display: 'flex', gap: 6, marginBottom: 8, flexWrap: 'wrap' }}>
                  <span style={{ background: 'rgba(91,140,255,0.15)', color: '#5b8cff', padding: '2px 8px', borderRadius: 4, fontSize: 11 }}>🎯 Planner: Alice</span>
                  <span style={{ background: 'rgba(167,139,250,0.15)', color: '#a78bfa', padding: '2px 8px', borderRadius: 4, fontSize: 11 }}>👥 Bob, Clio</span>
                </div>
                <div style={{ fontWeight: 600, fontSize: 13, marginBottom: 4 }}>系统安全审计与优化方案</div>
                <div style={{ color: '#8b93a7', fontSize: 11 }}>创建于 10:25 · 2/4 步骤完成</div>
              </div>
              {/* Timeline */}
              <div style={{ position: 'relative', paddingLeft: 20 }}>
                <div style={{ position: 'absolute', left: 7, top: 8, bottom: 8, width: 2, background: '#2a3140' }} />
                {planSteps.map((step, i) => (
                  <div key={step.id} style={{ position: 'relative', marginBottom: i < planSteps.length - 1 ? 20 : 0 }}>
                    <div style={{
                      position: 'absolute', left: -15, top: 3, width: 10, height: 10, borderRadius: '50%',
                      background: step.status === 'done' ? '#22c55e' : step.status === 'active' ? '#5b8cff' : '#2a3140',
                      border: `2px solid ${step.status === 'active' ? '#5b8cff' : step.status === 'done' ? '#22c55e' : '#2a3140'}`,
                      boxShadow: step.status === 'active' ? '0 0 8px rgba(91,140,255,0.4)' : 'none',
                    }} />
                    <div style={{ fontSize: 12, color: step.status === 'pending' ? '#8b93a7' : '#e8eaef', marginBottom: 2 }}>
                      Step {step.id}: {step.title}
                    </div>
                    <div style={{ fontSize: 11, color: '#6b7280' }}>
                      {step.status === 'done' ? '✅ 已完成' : step.status === 'active' ? '🔄 进行中' : '⏳ 待处理'}
                    </div>
                  </div>
                ))}
              </div>
              {/* Deliverables */}
              <div style={{ marginTop: 16, padding: 10, background: '#1e2433', borderRadius: 6, border: '1px solid #2a3140' }}>
                <div style={{ fontSize: 11, color: '#8b93a7', marginBottom: 6 }}>📁 交付物</div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                  {['security-report.pdf', 'fixes.patch', 'audit-log.json'].map(f => (
                    <div key={f} style={{ fontSize: 11, color: '#5b8cff', cursor: 'pointer' }}>📄 {f}</div>
                  ))}
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Left toggle when collapsed */}
        {leftCollapsed && (
          <div style={{ width: 32, minWidth: 32, background: '#141820', borderRight: '1px solid #2a3140', display: 'flex', alignItems: 'flex-start', justifyContent: 'center', paddingTop: 12 }}>
            <Button variant="ghost" size="iconSm" onClick={() => setLeftCollapsed(false)}><ChevronRight size={14} /></Button>
          </div>
        )}

        {/* Center - Office Canvas */}
        <div style={{ flex: 1, position: 'relative', overflow: 'hidden' }}>
          <div style={{
            position: 'absolute', inset: 0,
            background: `url(/office-bg.png) center/cover`,
            opacity: 0.3
          }} />
          <div style={{ position: 'absolute', inset: 0, background: 'radial-gradient(ellipse at center, rgba(20,24,32,0) 0%, rgba(12,14,18,0.8) 100%)' }} />
          {/* Agent sprites on canvas */}
          <div style={{ position: 'absolute', inset: 0 }}>
            {agents.filter(a => a.online).map((agent, i) => {
              const positions = [
                { x: '30%', y: '35%' }, { x: '55%', y: '25%' }, { x: '70%', y: '50%' },
                { x: '40%', y: '60%' }, { x: '60%', y: '70%' },
              ];
              const pos = positions[i] || { x: '50%', y: '50%' };
              return (
                <div key={agent.id} style={{
                  position: 'absolute', left: pos.x, top: pos.y, transform: 'translate(-50%, -50%)',
                  display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 2,
                  cursor: 'pointer', transition: 'transform 0.2s',
                }} onClick={() => setActiveAgent(agent)}>
                  <div style={{
                    width: 32, height: 48, background: agent.color, borderRadius: 3,
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                    fontSize: 18, fontWeight: 'bold', color: '#fff',
                    boxShadow: agent.id === activeAgent.id ? '0 0 12px ' + agent.color : '0 2px 8px rgba(0,0,0,0.4)',
                    border: agent.id === activeAgent.id ? '2px solid #e8eaef' : '2px solid rgba(255,255,255,0.2)',
                    imageRendering: 'pixelated',
                  }}>
                    {agent.avatar ? <img src={agent.avatar} alt={agent.name} style={{ width: '100%', height: '100%', borderRadius: 2, objectFit: 'cover' }} /> : agent.name[0]}
                  </div>
                  <span style={{ fontSize: 10, color: '#8b93a7', background: 'rgba(0,0,0,0.6)', padding: '1px 6px', borderRadius: 3 }}>
                    {agent.name}
                  </span>
                </div>
              );
            })}
          </div>
          <div style={{ position: 'absolute', top: 12, left: 12, fontSize: 11, color: '#6b7280', background: 'rgba(0,0,0,0.5)', padding: '4px 10px', borderRadius: 4 }}>
            2D Office Canvas · {agents.filter(a => a.online).length} agents online
          </div>
        </div>

        {/* Right Panel - Chat */}
        {!rightCollapsed && (
          <div style={{ width: 'min(380px, 38vw)', minWidth: 320, background: '#141820', borderLeft: '1px solid #2a3140', display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
            <div style={{ padding: '10px 14px', borderBottom: '1px solid #2a3140', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <div style={{ width: 24, height: 36, background: activeAgent.color, borderRadius: 2, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 11 }}>
                  {activeAgent.name[0]}
                </div>
                <div>
                  <div style={{ fontWeight: 600, fontSize: 13 }}>{activeAgent.name}</div>
                  <div style={{ fontSize: 10, color: '#8b93a7' }}>{activeAgent.role} · {activeAgent.model}</div>
                </div>
              </div>
              <div style={{ display: 'flex', gap: 4 }}>
                <div className="status-dot online" />
                <Button variant="ghost" size="iconSm" onClick={() => setRightCollapsed(true)}><ChevronRight size={14} /></Button>
              </div>
            </div>
            {/* Messages */}
            <div style={{ flex: 1, overflow: 'auto', padding: '12px 14px', display: 'flex', flexDirection: 'column', gap: 10 }}>
              {messages.map(msg => (
                <div key={msg.id}>
                  {msg.role === 'user' && (
                    <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
                      <div className="bubble-user" style={{ maxWidth: '85%', padding: '8px 12px' }}>
                        <div style={{ fontSize: 12, lineHeight: 1.5, whiteSpace: 'pre-wrap' }}>{msg.content}</div>
                        <div style={{ fontSize: 10, color: 'rgba(200,210,220,0.6)', textAlign: 'right', marginTop: 4 }}>{msg.timestamp}</div>
                      </div>
                    </div>
                  )}
                  {msg.role === 'assistant' && (
                    <div style={{ display: 'flex', gap: 8 }}>
                      <div style={{ width: 28, height: 28, borderRadius: 4, background: activeAgent.color, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 11, flexShrink: 0 }}>{activeAgent.name[0]}</div>
                      <div className="bubble-assistant" style={{ flex: 1, padding: '8px 12px' }}>
                        <div style={{ fontSize: 12, lineHeight: 1.5, whiteSpace: 'pre-wrap' }}>{msg.content}{msg.streaming && <span style={{ animation: 'cursor-blink 0.8s step-end infinite', color: '#5b8cff' }}>█</span>}</div>
                        <div style={{ fontSize: 10, color: '#6b7280', marginTop: 4 }}>{msg.timestamp}</div>
                      </div>
                    </div>
                  )}
                  {msg.role === 'thinking' && (
                    <div style={{ padding: '6px 12px', marginLeft: 36, background: 'rgba(91,140,255,0.08)', borderRadius: 6, border: '1px solid rgba(91,140,255,0.15)', fontSize: 11, color: '#8b93a7' }}>
                      <span style={{ color: '#5b8cff' }}>💭 </span>
                      {msg.content}
                      <span className="animate-pulse-dot" style={{ display: 'inline-block', animation: 'pulse-dot 1.5s ease-in-out infinite' }}> ...</span>
                    </div>
                  )}
                  {msg.role === 'tool' && (
                    <div style={{ marginLeft: 36, padding: '6px 10px', background: '#1e2433', borderRadius: 6, border: '1px solid #2a3140', fontSize: 11 }}>
                      <div style={{ color: '#fbbf24', marginBottom: 4 }}>🔧 调用工具: {msg.toolName}</div>
                      <div style={{ color: '#8b93a7' }}>{msg.content}</div>
                      {msg.toolResult && <div style={{ color: '#22c55e', marginTop: 4 }}>✓ {msg.toolResult}</div>}
                    </div>
                  )}
                </div>
              ))}
              {/* Thinking indicator */}
              <div style={{ display: 'flex', gap: 8, alignItems: 'center', padding: '4px 0' }}>
                <div style={{ width: 28, height: 28, borderRadius: 4, background: activeAgent.color, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 11, flexShrink: 0 }}>{activeAgent.name[0]}</div>
                <div style={{ display: 'flex', gap: 3 }}>
                  <div className="animate-pulse-dot" style={{ width: 5, height: 5, borderRadius: '50%', background: '#5b8cff', animationDelay: '0s' }} />
                  <div className="animate-pulse-dot" style={{ width: 5, height: 5, borderRadius: '50%', background: '#5b8cff', animationDelay: '0.2s' }} />
                  <div className="animate-pulse-dot" style={{ width: 5, height: 5, borderRadius: '50%', background: '#5b8cff', animationDelay: '0.4s' }} />
                </div>
                <span style={{ fontSize: 11, color: '#6b7280' }}>思考中…</span>
              </div>
            </div>
          </div>
        )}

        {/* Right toggle when collapsed */}
        {rightCollapsed && (
          <div style={{ width: 32, minWidth: 32, background: '#141820', borderLeft: '1px solid #2a3140', display: 'flex', alignItems: 'flex-start', justifyContent: 'center', paddingTop: 12 }}>
            <Button variant="ghost" size="iconSm" onClick={() => setRightCollapsed(false)}><ChevronLeft size={14} /></Button>
          </div>
        )}
      </div>

      {/* Status Bar */}
      <div style={{ height: 48, minHeight: 48, background: '#141820', borderTop: '1px solid #2a3140', display: 'flex', alignItems: 'center', padding: '0 10px', gap: 8, position: 'relative', zIndex: 10 }}>
        {/* Menu buttons */}
        <div style={{ display: 'flex', gap: 2 }}>
          {[['🤖', 'agents', 'Agent'], ['📋', 'tasks', '任务'], ['📡', 'channels', '通道'], ['🔧', 'models', '模型'], ['🎯', 'skills', '技能'], ['💾', 'memory', '记忆']].map(([icon, tab, label]) => (
            <button key={tab}
              onClick={() => toggleDock(tab)}
              style={{
                padding: '4px 8px', borderRadius: 4, border: 'none', cursor: 'pointer',
                background: dockOpen && dockTab === tab ? 'rgba(91,140,255,0.15)' : 'transparent',
                color: dockOpen && dockTab === tab ? '#5b8cff' : '#8b93a7', fontSize: 11,
                display: 'flex', alignItems: 'center', gap: 4, transition: 'all 0.15s',
              }}
            >
              <span>{icon}</span><span style={{ display: 'none' }}>{label}</span>
            </button>
          ))}
          <Button variant="ghost" size="iconSm" onClick={() => setShowSettings(true)} title="设置"><Settings size={13} /></Button>
        </div>

        {/* Heartbeat message */}
        <div style={{ flex: 1, fontSize: 11, color: '#6b7280', overflow: 'hidden', whiteSpace: 'nowrap', textOverflow: 'ellipsis', padding: '0 8px' }}>
          💭 Bob 正在思考: 用户最近在关注前端安全，或许可以提前准备一份OWASP Top 10对照清单...
        </div>

        {/* Energy bars */}
        <div style={{ display: 'flex', gap: 12, alignItems: 'center' }}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 1, minWidth: 80 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 10, color: '#8b93a7' }}>
              <span>🍞 饱食度</span><span>{activeAgent.satiety}%</span>
            </div>
            <div style={{ height: 4, borderRadius: 2, background: '#2a3140', overflow: 'hidden' }}>
              <div style={{
                height: '100%', width: `${activeAgent.satiety}%`,
                background: `linear-gradient(90deg, #22c55e, ${activeAgent.satiety < 30 ? '#ef4444' : activeAgent.satiety < 60 ? '#fbbf24' : '#22c55e'})`,
                transition: 'width 0.5s ease',
              }} />
            </div>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 1, minWidth: 80 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 10, color: '#8b93a7' }}>
              <span>⚡ 生物电流</span>
              <span>{activeAgent.bioCurrent}/10 {activeAgent.bioCurrent > 8 && <span style={{ color: '#ef4444', fontSize: 9 }}>电涌</span>}</span>
            </div>
            <div style={{ height: 4, borderRadius: 2, background: '#2a3140', overflow: 'hidden' }}>
              <div style={{
                height: '100%', width: `${activeAgent.bioCurrent * 10}%`,
                background: `linear-gradient(90deg, #3b82f6, ${activeAgent.bioCurrent > 8 ? '#ef4444' : activeAgent.bioCurrent > 5 ? '#f59e0b' : '#3b82f6'})`,
                transition: 'width 0.5s ease',
              }} />
            </div>
          </div>
        </div>

        {/* Emotion dots */}
        <div style={{ display: 'flex', gap: 6, alignItems: 'center' }} title={`Valence: ${activeAgent.emotion.valence.toFixed(1)} / Arousal: ${activeAgent.emotion.arousal.toFixed(1)} / Dominance: ${activeAgent.emotion.dominance.toFixed(1)}`}>
          <div style={{ width: 8, height: 8, borderRadius: '50%', background: getEmotionColor(activeAgent.emotion.valence) }} />
          <div style={{ width: 8, height: 8, borderRadius: '50%', background: activeAgent.emotion.arousal > 0.5 ? '#f59e0b' : '#3b82f6' }} />
          <div style={{ width: 8, height: 8, borderRadius: '50%', background: activeAgent.emotion.dominance > 0.5 ? '#8b5cf6' : '#5b8cff' }} />
        </div>

        {/* Input */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
          <input
            value={inputText}
            onChange={e => setInputText(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="输入消息..."
            style={{
              width: 160, height: 28, padding: '0 10px', borderRadius: 6,
              background: '#1e2433', border: '1px solid #2a3140', color: '#e8eaef',
              fontSize: 12, outline: 'none',
            }}
          />
          <Button variant="ghost" size="iconSm"><Mic size={14} /></Button>
          <Button variant="accent" size="sm" onClick={handleSend}><Send size={12} style={{ marginRight: 2 }} /> 发送</Button>
        </div>

        {/* Small thought bubble */}
        {smallThought && (
          <div style={{
            position: 'absolute', bottom: 52, right: 250, maxWidth: 280,
            background: 'rgba(20,24,32,0.95)', backdropFilter: 'blur(16px)',
            border: '1px solid rgba(91,140,255,0.3)', borderRadius: 8,
            padding: '8px 12px', boxShadow: '0 4px 20px rgba(0,0,0,0.5)',
            animation: 'fade-in 0.3s ease-out, float-up 5s ease-out 3s forwards',
            zIndex: 20,
          }}>
            <div style={{ fontSize: 10, color: '#5b8cff', marginBottom: 4 }}>💭 {smallThought.agent.name} 的小心思</div>
            <div style={{ fontSize: 11, color: '#c7cdd9', lineHeight: 1.4 }}>{smallThought.content}</div>
            <div style={{ fontSize: 9, color: '#6b7280', marginTop: 4, textAlign: 'right' }}>置信度: 72%</div>
          </div>
        )}
      </div>

      {/* Dock Panel */}
      <div style={{
        position: 'fixed', bottom: 48, left: 0, right: 0, height: dockOpen ? '20vh' : 0,
        background: '#141820', borderTop: dockOpen ? '1px solid #2a3140' : 'none',
        transition: 'height 0.3s ease-out', overflow: 'hidden', zIndex: 8,
      }}>
        <div style={{ height: '20vh', display: 'flex', flexDirection: 'column' }}>
          {/* Dock tabs */}
          <div style={{ display: 'flex', borderBottom: '1px solid #2a3140', padding: '0 16px' }}>
            {['agents', 'tasks', 'channels', 'models', 'skills', 'memory'].map(tab => (
              <button key={tab} onClick={() => setDockTab(tab)} style={{
                padding: '6px 14px', border: 'none', cursor: 'pointer', fontSize: 11,
                background: 'transparent', color: dockTab === tab ? '#5b8cff' : '#8b93a7',
                borderBottom: dockTab === tab ? '2px solid #5b8cff' : '2px solid transparent',
                transition: 'all 0.15s',
              }}>
                {tab === 'agents' ? '🤖 Agent' : tab === 'tasks' ? '📋 任务' : tab === 'channels' ? '📡 通道' : tab === 'models' ? '🔧 模型' : tab === 'skills' ? '🎯 技能' : '💾 记忆'}
              </button>
            ))}
          </div>

          {/* Dock content */}
          <div style={{ flex: 1, overflow: 'auto', padding: 12 }}>

            {/* Agent Tab */}
            {dockTab === 'agents' && (
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(100px, 1fr))', gap: 8 }}>
                {agents.map(agent => (
                  <div key={agent.id} className="glass-card" style={{
                    padding: 8, cursor: 'pointer', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 4,
                    borderColor: agent.id === activeAgent.id ? '#5b8cff' : undefined,
                  }} onClick={() => { setActiveAgent(agent); setDockOpen(false); }}>
                    <div style={{ width: 32, height: 48, background: agent.color, borderRadius: 2, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 14, color: '#fff' }}>
                      {agent.name[0]}
                    </div>
                    <div style={{ fontSize: 11, fontWeight: 600, color: '#e8eaef' }}>{agent.name}</div>
                    <div style={{ fontSize: 10, color: '#8b93a7' }}>{agent.role}</div>
                    <div className={`status-dot ${agent.online ? 'online' : 'offline'}`} style={{ marginTop: 2 }} />
                    <select
                      value={agent.model}
                      style={{ fontSize: 9, background: '#1e2433', border: '1px solid #2a3140', color: '#8b93a7', borderRadius: 3, padding: '1px 4px', width: '100%', textAlign: 'center' }}
                      onClick={e => e.stopPropagation()}
                    >
                      <option>GPT-4o</option>
                      <option>Claude 3.5</option>
                      <option>Llama 3.2</option>
                    </select>
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        setEditingAgent(agent);
                        setShowAgentEdit(true);
                      }}
                      style={{ padding: '2px 6px', fontSize: 9, background: 'transparent', border: '1px solid #2a3140', color: '#8b93a7', borderRadius: 3, cursor: 'pointer' }}
                    >编辑</button>
                  </div>
                ))}
                <div className="glass-card" style={{ padding: 8, display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: 'pointer' }}>
                  <Plus size={20} color="#5b8cff" />
                </div>
              </div>
            )}

            {/* Tasks Tab */}
            {dockTab === 'tasks' && (
              <div style={{ display: 'flex', gap: 10, overflowX: 'auto' }}>
                {plansData.map(plan => (
                  <div key={plan.id} className="glass-card" style={{ minWidth: 180, padding: 10 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 6 }}>
                      <div className={`status-dot ${plan.status === 'active' ? 'busy' : plan.status === 'done' ? 'online' : ''}`} />
                      <span style={{ fontSize: 11, fontWeight: 600 }}>{plan.name}</span>
                    </div>
                    <div style={{ fontSize: 10, color: '#8b93a7', marginBottom: 6 }}>{plan.agent} · {plan.time}</div>
                    <div style={{ height: 3, borderRadius: 2, background: '#2a3140', overflow: 'hidden' }}>
                      <div style={{ height: '100%', width: `${plan.progress}%`, background: plan.status === 'done' ? '#22c55e' : '#5b8cff', transition: 'width 0.3s' }} />
                    </div>
                    <div style={{ fontSize: 9, color: '#6b7280', marginTop: 4 }}>{plan.progress}%</div>
                  </div>
                ))}
              </div>
            )}

            {/* Channels Tab */}
            {dockTab === 'channels' && (
              <div style={{ display: 'flex', gap: 10 }}>
                {channelList.map(ch => (
                  <div key={ch.platform} className="glass-card" style={{ minWidth: 160, padding: 10 }}>
                    <div style={{ fontSize: 20, marginBottom: 4 }}>{ch.icon}</div>
                    <div style={{ fontSize: 11, fontWeight: 600 }}>{ch.name}</div>
                    <div style={{ fontSize: 10, color: '#8b93a7' }}>{ch.platform}</div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 4, marginTop: 6 }}>
                      <div className={`status-dot ${ch.status === 'connected' ? 'online' : 'offline'}`} />
                      <span style={{ fontSize: 10, color: '#8b93a7' }}>{ch.status === 'connected' ? '已连接' : '未连接'}</span>
                    </div>
                    {ch.agentId && <div style={{ fontSize: 9, color: '#5b8cff', marginTop: 4 }}>绑定: {ch.agentId}</div>}
                  </div>
                ))}
              </div>
            )}

            {/* Models Tab */}
            {dockTab === 'models' && (
              <div style={{ display: 'flex', gap: 10, overflowX: 'auto' }}>
                {modelList.map(m => (
                  <div key={m.name} className="glass-card" style={{ minWidth: 150, padding: 10 }}>
                    <div style={{ fontSize: 14, marginBottom: 4 }}>{m.providerIcon}</div>
                    <div style={{ fontSize: 11, fontWeight: 600 }}>{m.name}</div>
                    <div style={{ fontSize: 10, color: '#8b93a7' }}>{m.provider}</div>
                    {m.isDefault && <div style={{ fontSize: 9, color: '#22c55e', marginTop: 4, display: 'flex', alignItems: 'center', gap: 2 }}><Star size={10} /> 默认</div>}
                    <button
                      onClick={() => {
                        setEditingModel(m);
                        setShowModelEdit(true);
                      }}
                      style={{ marginTop: 6, padding: '2px 8px', fontSize: 9, background: 'transparent', border: '1px solid #2a3140', color: '#8b93a7', borderRadius: 3, cursor: 'pointer', width: '100%' }}
                    >编辑</button>
                  </div>
                ))}
                <div className="glass-card" style={{ minWidth: 120, padding: 10, display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: 'pointer' }}>
                  <Plus size={20} color="#5b8cff" />
                </div>
              </div>
            )}

            {/* Skills Tab */}
            {dockTab === 'skills' && (
              <div style={{ display: 'flex', height: '100%', gap: 0 }}>
                <div style={{ width: 100, borderRight: '1px solid #2a3140', padding: '4px 0', overflow: 'auto' }}>
                  {agents.slice(0, 4).map(a => (
                    <div key={a.id} style={{ padding: '6px 10px', fontSize: 11, color: '#8b93a7', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 6 }}>
                      <div style={{ width: 18, height: 18, borderRadius: 3, background: a.color, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 9, color: '#fff' }}>{a.name[0]}</div>
                      {a.name}
                    </div>
                  ))}
                </div>
                <div style={{ flex: 1, padding: '0 12px', overflow: 'auto' }}>
                  {['开发工具', '日常辅助', '安全'].map(cat => (
                    <div key={cat} style={{ marginBottom: 12 }}>
                      <div style={{ fontSize: 10, color: '#6b7280', textTransform: 'uppercase', marginBottom: 6, fontWeight: 600 }}>{cat}</div>
                      {skills.filter(s => s.category === cat).map(skill => (
                        <div key={skill.name} className="glass-card" style={{ padding: '6px 10px', marginBottom: 4, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                          <div>
                            <div style={{ fontSize: 11, fontWeight: 500 }}>{skill.name}</div>
                            <div style={{ fontSize: 10, color: '#8b93a7' }}>{skill.desc}</div>
                          </div>
                          <div style={{
                            width: 32, height: 18, borderRadius: 9, cursor: 'pointer',
                            background: skill.enabled ? '#22c55e' : '#2a3140',
                            position: 'relative', transition: 'background 0.2s',
                          }}>
                            <div style={{
                              position: 'absolute', top: 2, width: 14, height: 14, borderRadius: '50%',
                              background: '#fff', transition: 'left 0.2s',
                              left: skill.enabled ? 16 : 2,
                            }} />
                          </div>
                        </div>
                      ))}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Memory Tab */}
            {dockTab === 'memory' && (
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(100px, 1fr))', gap: 8 }}>
                {agents.map(agent => (
                  <div key={agent.id} className="glass-card" style={{
                    padding: 8, cursor: 'pointer', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 4,
                  }} onClick={() => { setMemoryAgent(agent); setShowMemoryDetail(true); }}>
                    <div style={{ width: 32, height: 48, background: agent.color, borderRadius: 2, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 14, color: '#fff' }}>
                      {agent.name[0]}
                    </div>
                    <div style={{ fontSize: 11, fontWeight: 600 }}>{agent.name}</div>
                    <div style={{ fontSize: 10, color: '#8b93a7' }}>{agent.role}</div>
                    <Button variant="ghost" size="sm" style={{ fontSize: 9, padding: '2px 6px' }}>查看记忆</Button>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Agent Edit Modal */}
      {showAgentEdit && editingAgent && (
        <div style={{
          position: 'fixed', inset: 0, zIndex: 1000, display: 'flex', alignItems: 'center', justifyContent: 'center',
          background: 'rgba(0,0,0,0.6)', backdropFilter: 'blur(4px)',
        }} onClick={() => setShowAgentEdit(false)}>
          <div style={{
            width: 560, maxHeight: '80vh', background: '#141820', borderRadius: 10, border: '1px solid #2a3140',
            boxShadow: '0 8px 32px rgba(0,0,0,0.5)', overflow: 'hidden',
          }} onClick={e => e.stopPropagation()}>
            <div style={{ padding: '14px 18px', borderBottom: '1px solid #2a3140', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span style={{ fontWeight: 600, fontSize: 14 }}>编辑 Agent — {editingAgent.name}</span>
              <Button variant="ghost" size="iconSm" onClick={() => setShowAgentEdit(false)}><X size={14} /></Button>
            </div>
            <div style={{ display: 'flex', borderBottom: '1px solid #2a3140' }}>
              {(['persona', 'role'] as const).map(tab => (
                <button key={tab} onClick={() => setEditTab(tab)} style={{
                  flex: 1, padding: '8px', border: 'none', cursor: 'pointer', fontSize: 11,
                  background: 'transparent', color: editTab === tab ? '#5b8cff' : '#8b93a7',
                  borderBottom: editTab === tab ? '2px solid #5b8cff' : '2px solid transparent',
                }}>
                  {tab === 'persona' ? '👤 角色' : '🧠 人格'}
                </button>
              ))}
            </div>
            <div style={{ padding: 16, overflow: 'auto', maxHeight: '50vh' }}>
              {editTab === 'persona' && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                  <div>
                    <label style={{ display: 'block', fontSize: 11, color: '#8b93a7', marginBottom: 4 }}>显示名称</label>
                    <input value={editingAgent.name} style={{ width: '100%', padding: '6px 10px', background: '#1e2433', border: '1px solid #2a3140', borderRadius: 6, color: '#e8eaef', fontSize: 12 }} />
                  </div>
                  <div>
                    <label style={{ display: 'block', fontSize: 11, color: '#8b93a7', marginBottom: 4 }}>角色</label>
                    <input value={editingAgent.role} style={{ width: '100%', padding: '6px 10px', background: '#1e2433', border: '1px solid #2a3140', borderRadius: 6, color: '#e8eaef', fontSize: 12 }} />
                  </div>
                  <div>
                    <label style={{ display: 'block', fontSize: 11, color: '#8b93a7', marginBottom: 4 }}>头像</label>
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: 6 }}>
                      {agents.slice(0, 5).map(a => (
                        <div key={a.id} style={{
                          width: '100%', aspectRatio: '2/3', background: a.color, borderRadius: 4, cursor: 'pointer',
                          border: editingAgent.id === a.id ? '2px solid #5b8cff' : '2px solid transparent',
                          display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 18, color: '#fff',
                        }}>{a.name[0]}</div>
                      ))}
                    </div>
                  </div>
                </div>
              )}
              {editTab === 'role' && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                  <div>
                    <label style={{ display: 'block', fontSize: 11, color: '#8b93a7', marginBottom: 4 }}>个性描述</label>
                    <textarea rows={3} placeholder="描述 agent 的性格、说话风格、行为习惯..."
                      style={{ width: '100%', padding: '8px 10px', background: '#1e2433', border: '1px solid #2a3140', borderRadius: 6, color: '#e8eaef', fontSize: 12, resize: 'vertical' }}
                    />
                  </div>
                  <div>
                    <label style={{ display: 'block', fontSize: 11, color: '#8b93a7', marginBottom: 4 }}>口头禅</label>
                    <input placeholder="例如: 让我想想..." style={{ width: '100%', padding: '6px 10px', background: '#1e2433', border: '1px solid #2a3140', borderRadius: 6, color: '#e8eaef', fontSize: 12 }} />
                  </div>
                  <div>
                    <label style={{ display: 'block', fontSize: 11, color: '#8b93a7', marginBottom: 4 }}>表情包/梗</label>
                    <input placeholder="例如: 认真脸.jpg" style={{ width: '100%', padding: '6px 10px', background: '#1e2433', border: '1px solid #2a3140', borderRadius: 6, color: '#e8eaef', fontSize: 12 }} />
                  </div>
                  <div>
                    <label style={{ display: 'block', fontSize: 11, color: '#8b93a7', marginBottom: 4 }}>顶嘴力度</label>
                    <div style={{ display: 'flex', gap: 6 }}>
                      {['关闭', '温和', '幽默', '直率'].map((level, i) => (
                        <button key={level} style={{
                          padding: '4px 12px', borderRadius: 4, border: `1px solid ${i === 2 ? '#5b8cff' : '#2a3140'}`,
                          background: i === 2 ? 'rgba(91,140,255,0.15)' : '#1e2433',
                          color: i === 2 ? '#5b8cff' : '#8b93a7', fontSize: 11, cursor: 'pointer',
                        }}>{level} ({i})</button>
                      ))}
                    </div>
                  </div>
                </div>
              )}
            </div>
            <div style={{ padding: '12px 16px', borderTop: '1px solid #2a3140', display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
              <Button variant="ghost" onClick={() => setShowAgentEdit(false)}>取消</Button>
              <Button variant="accent" onClick={() => setShowAgentEdit(false)}>保存</Button>
            </div>
          </div>
        </div>
      )}

      {/* Model Edit Modal */}
      {showModelEdit && (
        <div style={{
          position: 'fixed', inset: 0, zIndex: 1000, display: 'flex', alignItems: 'center', justifyContent: 'center',
          background: 'rgba(0,0,0,0.6)', backdropFilter: 'blur(4px)',
        }} onClick={() => setShowModelEdit(false)}>
          <div style={{
            width: 480, background: '#141820', borderRadius: 10, border: '1px solid #2a3140',
            boxShadow: '0 8px 32px rgba(0,0,0,0.5)', overflow: 'hidden',
          }} onClick={e => e.stopPropagation()}>
            <div style={{ padding: '14px 18px', borderBottom: '1px solid #2a3140', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span style={{ fontWeight: 600, fontSize: 14 }}>{editingModel ? '编辑模型' : '添加模型'}</span>
              <Button variant="ghost" size="iconSm" onClick={() => setShowModelEdit(false)}><X size={14} /></Button>
            </div>
            <div style={{ padding: 16, display: 'flex', flexDirection: 'column', gap: 10 }}>
              <div>
                <label style={{ display: 'block', fontSize: 11, color: '#8b93a7', marginBottom: 4 }}>提供商</label>
                <select style={{ width: '100%', padding: '6px 10px', background: '#1e2433', border: '1px solid #2a3140', borderRadius: 6, color: '#e8eaef', fontSize: 12 }}>
                  <option>🔷 OpenAI</option>
                  <option>🧠 Anthropic</option>
                  <option>🔺 Google (Gemini)</option>
                  <option>🏠 Ollama (本地)</option>
                  <option>🔍 DeepSeek</option>
                  <option>⚡ Groq</option>
                  <option>🦙 Meta (Llama)</option>
                </select>
              </div>
              <div>
                <label style={{ display: 'block', fontSize: 11, color: '#8b93a7', marginBottom: 4 }}>模型名称</label>
                <input placeholder="例如: gpt-4o" style={{ width: '100%', padding: '6px 10px', background: '#1e2433', border: '1px solid #2a3140', borderRadius: 6, color: '#e8eaef', fontSize: 12 }} />
              </div>
              <div>
                <label style={{ display: 'block', fontSize: 11, color: '#8b93a7', marginBottom: 4 }}>API Key</label>
                <input type="password" placeholder="sk-..." style={{ width: '100%', padding: '6px 10px', background: '#1e2433', border: '1px solid #2a3140', borderRadius: 6, color: '#e8eaef', fontSize: 12 }} />
              </div>
              <div>
                <label style={{ display: 'block', fontSize: 11, color: '#8b93a7', marginBottom: 4 }}>Base URL (可选)</label>
                <input placeholder="https://api.openai.com/v1" style={{ width: '100%', padding: '6px 10px', background: '#1e2433', border: '1px solid #2a3140', borderRadius: 6, color: '#e8eaef', fontSize: 12 }} />
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <input type="checkbox" id="defaultModel" style={{ accentColor: '#5b8cff' }} />
                <label htmlFor="defaultModel" style={{ fontSize: 11, color: '#8b93a7' }}>设为默认模型</label>
              </div>
            </div>
            <div style={{ padding: '12px 16px', borderTop: '1px solid #2a3140', display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
              <Button variant="ghost" onClick={() => setShowModelEdit(false)}>取消</Button>
              <Button variant="accent" onClick={() => setShowModelEdit(false)}>保存</Button>
            </div>
          </div>
        </div>
      )}

      {/* Memory Detail Modal */}
      {showMemoryDetail && (
        <div style={{
          position: 'fixed', inset: 0, zIndex: 1000, display: 'flex', alignItems: 'center', justifyContent: 'center',
          background: 'rgba(0,0,0,0.6)', backdropFilter: 'blur(4px)',
        }} onClick={() => setShowMemoryDetail(false)}>
          <div style={{
            width: 700, maxHeight: '80vh', background: '#141820', borderRadius: 10, border: '1px solid #2a3140',
            boxShadow: '0 8px 32px rgba(0,0,0,0.5)', overflow: 'hidden',
          }} onClick={e => e.stopPropagation()}>
            <div style={{ padding: '14px 18px', borderBottom: '1px solid #2a3140', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span style={{ fontWeight: 600, fontSize: 14 }}>{memoryAgent.name} 的记忆详情</span>
              <Button variant="ghost" size="iconSm" onClick={() => setShowMemoryDetail(false)}><X size={14} /></Button>
            </div>
            <div style={{ display: 'flex', borderBottom: '1px solid #2a3140' }}>
              {['dual', 'kg', 'myelin'].map(tab => (
                <button key={tab} onClick={() => {}} style={{
                  flex: 1, padding: '8px', border: 'none', cursor: 'pointer', fontSize: 11,
                  background: 'transparent', color: tab === 'dual' ? '#5b8cff' : '#8b93a7',
                  borderBottom: tab === 'dual' ? '2px solid #5b8cff' : '2px solid transparent',
                }}>
                  {tab === 'dual' ? '📊 双重记忆' : tab === 'kg' ? '🔗 知识图谱' : '🧬 髓鞘化'}
                </button>
              ))}
            </div>
            <div style={{ padding: 16, overflow: 'auto', maxHeight: '50vh' }}>
              {/* Dual Memory Stats */}
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
                <div className="glass-card" style={{ padding: 12 }}>
                  <div style={{ fontSize: 10, color: '#8b93a7', marginBottom: 6 }}>🧬 向量记忆</div>
                  <div style={{ fontSize: 20, fontWeight: 700, color: '#5b8cff' }}>1,872</div>
                  <div style={{ fontSize: 10, color: '#6b7280', marginTop: 2 }}>总条目 · 最近: 10分钟前</div>
                </div>
                <div className="glass-card" style={{ padding: 12 }}>
                  <div style={{ fontSize: 10, color: '#8b93a7', marginBottom: 6 }}>🔗 知识图谱</div>
                  <div style={{ display: 'flex', gap: 16 }}>
                    <div><div style={{ fontSize: 18, fontWeight: 700, color: '#22c55e' }}>45</div><div style={{ fontSize: 9, color: '#6b7280' }}>节点</div></div>
                    <div><div style={{ fontSize: 18, fontWeight: 700, color: '#fbbf24' }}>128</div><div style={{ fontSize: 9, color: '#6b7280' }}>边</div></div>
                  </div>
                </div>
                <div className="glass-card" style={{ padding: 12 }}>
                  <div style={{ fontSize: 10, color: '#8b93a7', marginBottom: 6 }}>💬 会话日志</div>
                  <div style={{ fontSize: 20, fontWeight: 700, color: '#a78bfa' }}>23</div>
                  <div style={{ fontSize: 10, color: '#6b7280', marginTop: 2 }}>活跃会话 · 最近活跃: 2分钟前</div>
                </div>
                <div className="glass-card" style={{ padding: 12 }}>
                  <div style={{ fontSize: 10, color: '#8b93a7', marginBottom: 6 }}>📄 持久记忆</div>
                  <div style={{ fontSize: 12, color: '#8b93a7' }}>SOUL.md 已加载 · MEMORY.md 457 条记录</div>
                </div>
              </div>
              {/* Knowledge Graph visual */}
              <div style={{ marginTop: 16, padding: 16, background: '#1e2433', borderRadius: 8, border: '1px solid #2a3140' }}>
                <div style={{ fontSize: 11, color: '#8b93a7', marginBottom: 10 }}>知识图谱可视化</div>
                <div style={{ display: 'flex', justifyContent: 'center', gap: 16, alignItems: 'center', flexWrap: 'wrap', minHeight: 80 }}>
                  {['安全', '代码', '前端', '后端', 'API'].map((node, i) => (
                    <div key={node} style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 4 }}>
                      <div style={{
                        width: 40, height: 40, borderRadius: '50%',
                        background: ['#5b8cff', '#22c55e', '#a78bfa', '#fbbf24', '#ef4444'][i],
                        display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 11, color: '#fff',
                        position: 'relative',
                      }}>
                        {node[0]}
                        {/* connecting lines as pseudo-elements won't work, simplified */}
                      </div>
                      <span style={{ fontSize: 9, color: '#8b93a7' }}>{node}</span>
                    </div>
                  ))}
                </div>
                <div style={{ display: 'flex', justifyContent: 'center', gap: 4, marginTop: 8 }}>
                  {[1,2,3,4].map(i => (
                    <div key={i} style={{ width: 20, height: 2, background: '#2a3140', transform: `rotate(${i * 15 - 30}deg)`, margin: '0 4px' }} />
                  ))}
                </div>
              </div>
              {/* Myelination */}
              <div style={{ marginTop: 16, display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 10 }}>
                <div className="glass-card" style={{ padding: 10, textAlign: 'center' }}>
                  <div style={{ fontSize: 9, color: '#8b93a7' }}>学习阶段</div>
                  <div style={{ fontSize: 16, fontWeight: 700, color: '#8b93a7' }}>120</div>
                  <div style={{ height: 3, borderRadius: 2, background: '#2a3140', marginTop: 4 }}>
                    <div style={{ height: '100%', width: '77%', background: '#8b93a7', borderRadius: 2 }} />
                  </div>
                </div>
                <div className="glass-card" style={{ padding: 10, textAlign: 'center' }}>
                  <div style={{ fontSize: 9, color: '#8b93a7' }}>固化阶段</div>
                  <div style={{ fontSize: 16, fontWeight: 700, color: '#fbbf24' }}>28</div>
                  <div style={{ height: 3, borderRadius: 2, background: '#2a3140', marginTop: 4 }}>
                    <div style={{ height: '100%', width: '18%', background: '#fbbf24', borderRadius: 2 }} />
                  </div>
                </div>
                <div className="glass-card" style={{ padding: 10, textAlign: 'center' }}>
                  <div style={{ fontSize: 9, color: '#8b93a7' }}>本能阶段</div>
                  <div style={{ fontSize: 16, fontWeight: 700, color: '#22c55e' }}>8</div>
                  <div style={{ height: 3, borderRadius: 2, background: '#2a3140', marginTop: 4 }}>
                    <div style={{ height: '100%', width: '5%', background: '#22c55e', borderRadius: 2 }} />
                  </div>
                </div>
              </div>
              <div className="glass-card" style={{ padding: 10, marginTop: 10, display: 'flex', justifyContent: 'space-around' }}>
                <div style={{ textAlign: 'center' }}>
                  <div style={{ fontSize: 9, color: '#8b93a7' }}>节省 LLM 调用</div>
                  <div style={{ fontSize: 14, fontWeight: 700, color: '#5b8cff' }}>45 次</div>
                </div>
                <div style={{ textAlign: 'center' }}>
                  <div style={{ fontSize: 9, color: '#8b93a7' }}>节省 Token</div>
                  <div style={{ fontSize: 14, fontWeight: 700, color: '#22c55e' }}>23,400</div>
                </div>
                <div style={{ textAlign: 'center' }}>
                  <div style={{ fontSize: 9, color: '#8b93a7' }}>缓存命中率</div>
                  <div style={{ fontSize: 14, fontWeight: 700, color: '#fbbf24' }}>92.5%</div>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Settings Modal */}
      {showSettings && (
        <div style={{
          position: 'fixed', inset: 0, zIndex: 1000, display: 'flex', alignItems: 'center', justifyContent: 'center',
          background: 'rgba(0,0,0,0.6)', backdropFilter: 'blur(4px)',
        }} onClick={() => setShowSettings(false)}>
          <div style={{
            width: 500, maxHeight: '70vh', background: '#141820', borderRadius: 10, border: '1px solid #2a3140',
            boxShadow: '0 8px 32px rgba(0,0,0,0.5)', overflow: 'hidden',
          }} onClick={e => e.stopPropagation()}>
            <div style={{ padding: '14px 18px', borderBottom: '1px solid #2a3140', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span style={{ fontWeight: 600, fontSize: 14 }}>⚙️ 系统设置</span>
              <Button variant="ghost" size="iconSm" onClick={() => setShowSettings(false)}><X size={14} /></Button>
            </div>
            <div style={{ padding: 16, overflow: 'auto', maxHeight: '50vh' }}>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                <div className="glass-card" style={{ padding: 12 }}>
                  <div style={{ fontWeight: 600, fontSize: 12, marginBottom: 8 }}>心跳设置</div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
                    <span style={{ fontSize: 11, color: '#8b93a7' }}>心跳间隔</span>
                    <input type="number" defaultValue={5} style={{ width: 60, padding: '4px 8px', background: '#1e2433', border: '1px solid #2a3140', borderRadius: 4, color: '#e8eaef', fontSize: 11, textAlign: 'center' }} />
                    <span style={{ fontSize: 10, color: '#6b7280' }}>秒</span>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
                    <span style={{ fontSize: 11, color: '#8b93a7' }}>空闲超时</span>
                    <input type="number" defaultValue={50} style={{ width: 60, padding: '4px 8px', background: '#1e2433', border: '1px solid #2a3140', borderRadius: 4, color: '#e8eaef', fontSize: 11, textAlign: 'center' }} />
                    <span style={{ fontSize: 10, color: '#6b7280' }}>秒</span>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <span style={{ fontSize: 11, color: '#8b93a7' }}>预判过滤</span>
                    <div style={{ width: 32, height: 18, borderRadius: 9, background: '#22c55e', position: 'relative', cursor: 'pointer' }}>
                      <div style={{ position: 'absolute', top: 2, left: 16, width: 14, height: 14, borderRadius: '50%', background: '#fff' }} />
                    </div>
                  </div>
                </div>
                <div className="glass-card" style={{ padding: 12 }}>
                  <div style={{ fontWeight: 600, fontSize: 12, marginBottom: 8 }}>存储路径</div>
                  <div style={{ fontSize: 11, color: '#8b93a7' }}>数据目录: ~/.hermes/</div>
                  <div style={{ fontSize: 11, color: '#8b93a7', marginTop: 2 }}>Neo4j: bolt://localhost:7687</div>
                  <div style={{ fontSize: 11, color: '#8b93a7', marginTop: 2 }}>Qdrant: .memos/qdrant/</div>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
