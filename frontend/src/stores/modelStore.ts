/**
 * 模型 Store — 管理模型列表、供应商列表、模型编辑弹窗状态
 */
import { create } from 'zustand';
import type { ModelInfo, ProviderInfo } from '../types';

interface ModelStoreState {
  models: ModelInfo[];
  providers: ProviderInfo[];
  showModelModal: boolean;
  editingModelId: string | null;

  setModels: (models: ModelInfo[]) => void;
  setProviders: (providers: ProviderInfo[]) => void;
  setShowModelModal: (show: boolean, editingId?: string | null) => void;
  setEditingModelId: (id: string | null) => void;
}

export const useModelStore = create<ModelStoreState>((set) => ({
  models: [],
  providers: [],
  showModelModal: false,
  editingModelId: null,

  setModels: (models) => set({ models }),
  setProviders: (providers) => set({ providers }),
  setShowModelModal: (show: boolean, editingId: string | null = null) =>
    set({ showModelModal: show, editingModelId: editingId }),
  setEditingModelId: (id) => set({ editingModelId: id }),
}));
