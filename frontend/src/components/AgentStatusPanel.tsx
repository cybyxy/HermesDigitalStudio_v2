/**
 * AgentStatusPanel — Agent 状态浮动信息面板
 *
 * 显示：
 * - 饱食度 / 神经电流
 * - 当前综合情绪状态（PAD → 单标签）
 */

import { useEffect, useState, useRef } from 'react';
import { apiGetAgentEnergy } from '../api/energy';
import { apiGetAgentEmotion } from '../api/emotion';
import type { EnergyState, EmotionState } from '../api/types';
import './AgentStatusPanel.css';

interface Props {
  agentId: string | null;
}

/** 饱食度颜色 */
function satietyColor(value: number): string {
  if (value > 60) return '#4caf50';
  if (value > 30) return '#ff9800';
  return '#f44336';
}

/** 神经电流颜色 */
function neuralCurrentColor(value: number): string {
  if (value <= 3) return '#2196f3';
  if (value <= 6) return '#ff9800';
  return '#f44336';
}

/**
 * PAD → 单一情绪标签 + 颜色
 * 返回 { label, color }
 */
function padToMood(v: number, a: number, d: number): { label: string; color: string } {
  // 混合颜色：valence 决定色相，arousal 影响饱和度
  const r = v >= 0
    ? Math.round(76 + 60 * (1 - v))
    : Math.round(76 + 120 * Math.abs(v));
  const g = v >= 0
    ? Math.round(175 - 60 * (1 - v))
    : Math.round(175 - 120 * Math.abs(v));
  const b = a >= 0
    ? Math.round(80 + 80 * a)
    : Math.round(80 + 40 * Math.abs(a));
  const color = `rgb(${Math.max(0, Math.min(255, r))}, ${Math.max(0, Math.min(255, g))}, ${Math.max(0, Math.min(255, b))})`;

  // 情绪标签
  if (v > 0.3 && a > 0.3) return { label: '兴奋', color };
  if (v > 0.3 && a < -0.3) return { label: '放松', color };
  if (v < -0.3 && a > 0.3) return { label: '紧张', color };
  if (v < -0.3 && a < -0.3) return { label: '低落', color };
  if (v > 0.2) return { label: '愉悦', color };
  if (v < -0.2) return { label: '不悦', color };
  return { label: '平和', color };
}

export function AgentStatusPanel({ agentId }: Props) {
  const [energy, setEnergy] = useState<EnergyState | null>(null);
  const [energyError, setEnergyError] = useState(false);
  const [emotion, setEmotion] = useState<EmotionState | null>(null);
  const [emotionError, setEmotionError] = useState(false);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    const fetchData = async () => {
      if (!agentId) {
        setEnergy(null);
        setEnergyError(false);
        setEmotion(null);
        setEmotionError(false);
        return;
      }
      await Promise.all([
        (async () => {
          try {
            const data = await apiGetAgentEnergy(agentId);
            setEnergy(data);
            setEnergyError(false);
          } catch {
            setEnergyError(true);
          }
        })(),
        (async () => {
          try {
            const data = await apiGetAgentEmotion(agentId);
            setEmotion(data);
            setEmotionError(false);
          } catch {
            setEmotionError(true);
          }
        })(),
      ]);
    };

    fetchData();
    intervalRef.current = setInterval(fetchData, 30000);

    return () => {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
    };
  }, [agentId]);

  if (!agentId) return null;

  const hasEnergy = energy && !energyError;
  const hasEmotion = emotion && !emotionError;
  if (!hasEnergy && !hasEmotion) return null;

  const satietyPct = energy ? (energy.satiety / 100) * 100 : 0;
  const bioPct = energy ? (energy.bio_current / 10) * 100 : 0;

  const mood = hasEmotion
    ? padToMood(emotion!.valence, emotion!.arousal, emotion!.dominance)
    : null;

  return (
    <div className="agent-status-panel">
      {hasEnergy && (
        <>
          <div className="asp-item">
            <span className="asp-label">饱食</span>
            <div className="asp-track">
              <div
                className="asp-fill"
                style={{
                  width: `${satietyPct}%`,
                  backgroundColor: satietyColor(energy!.satiety),
                }}
              />
            </div>
          </div>

          <div className="asp-item">
            <span className="asp-label">神经电流</span>
            <div className="asp-track">
              <div
                className="asp-fill"
                style={{
                  width: `${bioPct}%`,
                  backgroundColor: neuralCurrentColor(energy!.bio_current),
                }}
              />
            </div>
          </div>
        </>
      )}

      {/* 综合情绪指示器 */}
      {mood && (
        <div className="asp-mood">
          <span className="asp-mood-dot" style={{ background: mood.color }} />
          <span className="asp-mood-label">{mood.label}</span>
        </div>
      )}

      {!hasEnergy && !hasEmotion && (
        <span className="asp-loading">⋯</span>
      )}
    </div>
  );
}
