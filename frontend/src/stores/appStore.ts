/**
 * 应用全局状态 Store — 负责顶层协调状态
 * 包括：初始化状态、WebSocket 连接状态、附件管理
 */
import { create } from 'zustand';
import type { Attachment } from '../types';

interface AppState {
  initialized: boolean;
  wsConnected: boolean;
  autoConnect: boolean;
  attachments: Attachment[];
  /** 最新一条心跳推理消息 */
  heartbeatMessage: {
    agentId: string;
    content: string;
    timestamp: number;
  } | null;
  /** 心跳推理过程中的 thinking 文本流（实时累积） */
  heartbeatThinking: string;
  /** 最近一条小心思 */
  smallThought: {
    agentId: string;
    content: string;
    timestamp: number;
  } | null;

  setInitialized: (init: boolean) => void;
  setWsConnected: (connected: boolean) => void;
  setAutoConnect: (v: boolean) => void;
  setAttachments: (attachments: Attachment[]) => void;
  addAttachment: (attachment: Attachment) => void;
  removeAttachment: (index: number) => void;
  setHeartbeatMessage: (msg: AppState['heartbeatMessage']) => void;
  setHeartbeatThinking: (text: string) => void;
  clearHeartbeatThinking: () => void;
  setSmallThought: (thought: AppState['smallThought']) => void;
  clearSmallThought: () => void;
}

export const useAppStore = create<AppState>((set) => ({
  initialized: false,
  wsConnected: false,
  autoConnect: false,
  attachments: [],
  heartbeatMessage: null,
  heartbeatThinking: '',
  smallThought: null,

  setInitialized: (init) => set({ initialized: init }),
  setWsConnected: (connected) => set({ wsConnected: connected }),
  setAutoConnect: (v) => set({ autoConnect: v }),
  setAttachments: (attachments) => set({ attachments }),
  addAttachment: (attachment) =>
    set((state) => ({ attachments: [...state.attachments, attachment] })),
  removeAttachment: (index) =>
    set((state) => ({ attachments: state.attachments.filter((_, i) => i !== index) })),
  setHeartbeatMessage: (msg) => set({ heartbeatMessage: msg }),
  setHeartbeatThinking: (text) => set({ heartbeatThinking: text }),
  clearHeartbeatThinking: () => set({ heartbeatThinking: '' }),
  setSmallThought: (thought) => set({ smallThought: thought }),
  clearSmallThought: () => set({ smallThought: null }),
}));
