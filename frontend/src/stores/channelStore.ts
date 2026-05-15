/**
 * 通道 Store — 管理通道列表、通道编辑弹窗状态
 */
import { create } from 'zustand';
import type { ChannelInfo } from '../types';

interface ChannelStoreState {
  channels: ChannelInfo[];
  showChannelModal: boolean;
  editingChannelId: string | null;

  setChannels: (channels: ChannelInfo[]) => void;
  setShowChannelModal: (show: boolean, editingId?: string | null) => void;
  setEditingChannelId: (id: string | null) => void;
}

export const useChannelStore = create<ChannelStoreState>((set) => ({
  channels: [],
  showChannelModal: false,
  editingChannelId: null,

  setChannels: (channels) => set({ channels }),
  setShowChannelModal: (show: boolean, editingId: string | null = null) =>
    set({ showChannelModal: show, editingChannelId: editingId }),
  setEditingChannelId: (id) => set({ editingChannelId: id }),
}));
