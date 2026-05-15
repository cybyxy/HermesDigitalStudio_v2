/**
 * EnergyBar — 双色能量条组件
 *
 * 显示当前选中 Agent 的饱食度（Satiety）和神经电源（Neural Power）状态。
 * - 饱食度：绿色 → 黄色 → 红色渐变
 * - 神经电源：蓝色 → 橙色 → 红色渐变
 * - 模式标签：normal / power_save / surge / forced_discharge
 */

import { useEffect, useState, useRef } from 'react';
import { apiGetAgentEnergy } from '../api/energy';
import type { EnergyState } from '../api/types';
import './EnergyBar.css';

export interface EnergyBarProps {
  agentId: string | null;
}

/** 根据值获取饱食度颜色（绿→黄→红） */
function satietyColor(value: number): string {
  if (value > 60) return '#4caf50';
  if (value > 30) return '#ff9800';
  return '#f44336';
}

/** 根据值获取神经电源颜色（蓝→橙→红） */
function bioCurrentColor(value: number): string {
  if (value <= 3) return '#2196f3';
  if (value <= 6) return '#ff9800';
  return '#f44336';
}

/** 模式标签 */
function modeLabel(mode: string): string {
  switch (mode) {
    case 'power_save': return '节能';
    case 'surge': return '电涌';
    case 'forced_discharge': return '放电';
    default: return '正常';
  }
}

function modeClass(mode: string): string {
  return `energy-mode-${mode}`;
}

export function EnergyBar({ agentId }: EnergyBarProps) {
  const [energy, setEnergy] = useState<EnergyState | null>(null);
  const [error, setError] = useState(false);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    const fetchEnergy = async () => {
      if (!agentId) {
        setEnergy(null);
        return;
      }
      try {
        const data = await apiGetAgentEnergy(agentId);
        setEnergy(data);
        setError(false);
      } catch {
        setError(true);
      }
    };

    fetchEnergy();

    // 每 30 秒轮询
    intervalRef.current = setInterval(fetchEnergy, 30000);

    return () => {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
    };
  }, [agentId]);

  if (!agentId) {
    return <div className="energy-bar energy-bar--empty">选择 Agent 以查看能量状态</div>;
  }

  if (error && !energy) {
    return <div className="energy-bar energy-bar--empty">能量数据不可用</div>;
  }

  if (!energy) {
    return <div className="energy-bar energy-bar--loading">加载中...</div>;
  }

  const satietyPct = (energy.satiety / 100) * 100;
  const bioCurrentPct = (energy.bio_current / 10) * 100;

  return (
    <div className="energy-bar">
      {/* 饱食度 */}
      <div className="energy-row">
        <span className="energy-label">饱食度</span>
        <div className="energy-track">
          <div
            className="energy-fill"
            style={{
              width: `${satietyPct}%`,
              backgroundColor: satietyColor(energy.satiety),
            }}
          />
        </div>
        <span className="energy-value">{energy.satiety}</span>
      </div>

      {/* 神经电流 */}
      <div className="energy-row">
        <span className="energy-label">神经电流</span>
        <div className="energy-track">
          <div
            className="energy-fill"
            style={{
              width: `${bioCurrentPct}%`,
              backgroundColor: bioCurrentColor(energy.bio_current),
            }}
          />
        </div>
        <span className="energy-value">{energy.bio_current}</span>
      </div>

      {/* 模式 */}
      <div className={`energy-mode ${modeClass(energy.mode)}`}>
        {modeLabel(energy.mode)}
      </div>
    </div>
  );
}
