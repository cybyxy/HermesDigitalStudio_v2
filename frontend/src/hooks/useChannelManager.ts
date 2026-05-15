/**
 * useChannelManager — Channel CRUD hook.
 * Manages communication channel configurations.
 */
import { useState, useCallback, useEffect } from 'react';
import { useChannelStore } from '../stores/channelStore';
import * as api from '../api';
import type { ChannelInfo } from '../types';

export function useChannelManager() {
  const [loading, setLoading] = useState(false);
  const channels = useChannelStore((s) => s.channels);

  /** Load all channels */
  const refreshChannels = useCallback(async (): Promise<ChannelInfo[]> => {
    setLoading(true);
    try {
      const data = await api.apiGetChannels();
      useChannelStore.getState().setChannels(data);
      return data;
    } catch {
      return [];
    } finally {
      setLoading(false);
    }
  }, []);

  /** Create a new channel */
  const createChannel = useCallback(async (data: Record<string, unknown>): Promise<boolean> => {
    setLoading(true);
    try {
      await api.apiPostChannel(data as unknown as api.ChannelUpsertPayload);
      await refreshChannels();
      return true;
    } catch {
      return false;
    } finally {
      setLoading(false);
    }
  }, [refreshChannels]);

  /** Update an existing channel */
  const updateChannel = useCallback(async (channelId: string, data: Record<string, unknown>): Promise<boolean> => {
    setLoading(true);
    try {
      await api.apiPutChannel(channelId, data as unknown as api.ChannelUpsertPayload);
      await refreshChannels();
      return true;
    } catch {
      return false;
    } finally {
      setLoading(false);
    }
  }, [refreshChannels]);

  /** Delete a channel */
  const deleteChannel = useCallback(async (channelId: string): Promise<boolean> => {
    setLoading(true);
    try {
      await api.apiDeleteChannel(channelId);
      await refreshChannels();
      return true;
    } catch {
      return false;
    } finally {
      setLoading(false);
    }
  }, [refreshChannels]);

  return {
    channels,
    loading,
    refreshChannels,
    createChannel,
    updateChannel,
    deleteChannel,
  };
}
