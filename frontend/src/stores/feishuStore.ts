/**
 * 飞书 Store — 管理飞书 transcript 镜像数据
 */
import { create } from 'zustand';
import type { ChatRow, ProcessRow } from '../types';

interface FeishuStoreState {
  feishuMirrorChatRows: ChatRow[];
  feishuMirrorProcessRows: ProcessRow[];

  setFeishuMirror: (chat: ChatRow[], process: ProcessRow[]) => void;
}

export const useFeishuStore = create<FeishuStoreState>((set) => ({
  feishuMirrorChatRows: [],
  feishuMirrorProcessRows: [],

  setFeishuMirror: (chat, process) =>
    set({ feishuMirrorChatRows: chat, feishuMirrorProcessRows: process }),
}));
