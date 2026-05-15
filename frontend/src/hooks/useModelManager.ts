/**
 * useModelManager — Model + provider management hook.
 * CRUD operations for AI model configurations.
 */
import { useState, useCallback, useEffect } from 'react';
import { useModelStore } from '../stores/modelStore';
import * as api from '../api';
import type { ModelInfo, ProviderInfo } from '../types';

export function useModelManager() {
  const [loading, setLoading] = useState(false);
  const models = useModelStore((s) => s.models);
  const providers = useModelStore((s) => s.providers);

  /** Load models and providers from the API */
  const refreshModels = useCallback(async (): Promise<{ models: ModelInfo[]; providers: ProviderInfo[] }> => {
    setLoading(true);
    try {
      const [modelData, providerData] = await Promise.all([
        api.apiGetModels(),
        api.apiGetProviders(),
      ]);
      useModelStore.getState().setModels(modelData);
      useModelStore.getState().setProviders(providerData);
      return { models: modelData, providers: providerData };
    } catch {
      return { models: [], providers: [] };
    } finally {
      setLoading(false);
    }
  }, []);

  /** Create a new model */
  const createModel = useCallback(async (data: Record<string, unknown>): Promise<boolean> => {
    setLoading(true);
    try {
      await api.apiPostModel(data as { name: string; provider: string; modelId: string; apiBase?: string; apiKey?: string; contextWindow?: number; isDefault?: boolean; enabled?: boolean; description?: string });
      await refreshModels();
      return true;
    } catch {
      return false;
    } finally {
      setLoading(false);
    }
  }, [refreshModels]);

  /** Update an existing model */
  const updateModel = useCallback(async (modelId: string, data: Record<string, unknown>): Promise<boolean> => {
    setLoading(true);
    try {
      await api.apiPutModel(modelId, data);
      await refreshModels();
      return true;
    } catch {
      return false;
    } finally {
      setLoading(false);
    }
  }, [refreshModels]);

  /** Delete a model */
  const deleteModel = useCallback(async (modelId: string): Promise<boolean> => {
    setLoading(true);
    try {
      await api.apiDeleteModel(modelId);
      await refreshModels();
      return true;
    } catch {
      return false;
    } finally {
      setLoading(false);
    }
  }, [refreshModels]);

  /** Fetch available models from a specific provider */
  const fetchProviderModels = useCallback(async (
    provider: string,
    apiKey?: string,
    baseUrl?: string,
  ): Promise<string[]> => {
    try {
      const result = await api.apiProbeProviderModels(provider, apiKey, baseUrl);
      return result.models;
    } catch {
      return [];
    }
  }, []);

  /** Get provider env key hint */
  const getProviderEnvKey = useCallback(async (provider: string): Promise<string | null> => {
    try {
      const result = await api.apiGetProviderEnvkey(provider);
      return result.envVarValue || null;
    } catch {
      return null;
    }
  }, []);

  return {
    models,
    providers,
    loading,
    refreshModels,
    createModel,
    updateModel,
    deleteModel,
    fetchProviderModels,
    getProviderEnvKey,
  };
}
