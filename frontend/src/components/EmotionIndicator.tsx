/**
 * EmotionIndicator — Agent PAD 情绪状态指示器
 *
 * 在 StatusBar 底部显示三个小圆点，分别代表：
 * - 🟢 valence (愉悦度): 绿色，正=明亮绿，负=暗绿
 * - 🟡 arousal (唤醒度): 黄色/橙色
 * - 🔵 dominance (支配度): 蓝色
 *
 * 圆点大小反映绝对值大小。
 * 点击展开/折叠显示最近 30 条 PAD 历史迷你折线图。
 */

import React, { useEffect, useState, useCallback, useRef } from 'react';
import { apiGetAgentEmotion, apiGetAgentEmotionHistory } from '../api/emotion';
import type { EmotionState, EmotionHistoryEntry } from '../api/types';
import './EmotionIndicator.css';

interface EmotionIndicatorProps {
  agentId: string | null;
}

const POLL_INTERVAL = 30_000; // 30s

/** 趋势箭头 */
function trendArrow(current: number, previous: number): string {
  if (previous === current) return '→';
  return current > previous ? '↑' : '↓';
}

/** 迷你折线 Canvas */
function MiniSparkline({
  data,
  width,
  height,
  color,
  range,
}: {
  data: number[];
  width: number;
  height: number;
  color: string;
  range: [number, number];
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || data.length < 2) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    ctx.clearRect(0, 0, width, height);

    const [min, max] = range;
    const ySpan = max - min || 1;
    const xStep = width / (data.length - 1);

    ctx.beginPath();
    ctx.strokeStyle = color;
    ctx.lineWidth = 1.5;

    data.forEach((val, i) => {
      const x = i * xStep;
      const y = height - ((val - min) / ySpan) * height;
      if (i === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });

    ctx.stroke();
  }, [data, width, height, color, range]);

  return <canvas ref={canvasRef} width={width} height={height} style={{ display: 'block' }} />;
}

export const EmotionIndicator: React.FC<EmotionIndicatorProps> = ({ agentId }) => {
  const [emotion, setEmotion] = useState<EmotionState | null>(null);
  const [history, setHistory] = useState<EmotionHistoryEntry[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(false);
  const [expanded, setExpanded] = useState(false);

  // 加载当前情绪
  useEffect(() => {
    if (!agentId) {
      setEmotion(null);
      setError(false);
      setLoading(false);
      setHistory([]);
      setExpanded(false);
      return;
    }

    let cancelled = false;
    const fetchEmotion = async () => {
      setLoading(true);
      try {
        const data = await apiGetAgentEmotion(agentId);
        if (!cancelled) {
          setEmotion(data);
          setError(false);
        }
      } catch {
        if (!cancelled) setError(true);
      } finally {
        if (!cancelled) setLoading(false);
      }
    };

    fetchEmotion();
    const timer = setInterval(fetchEmotion, POLL_INTERVAL);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [agentId]);

  // 加载历史（展开时）
  useEffect(() => {
    if (!agentId || !expanded) return;
    let cancelled = false;
    apiGetAgentEmotionHistory(agentId, 30)
      .then((data) => {
        if (!cancelled) setHistory(data);
      })
      .catch(() => {});
    return () => { cancelled = true; };
  }, [agentId, expanded]);

  const toggleExpand = useCallback(() => {
    setExpanded((prev) => !prev);
  }, []);

  // 无 agent
  if (!agentId) {
    return (
      <div className="emotion-indicator">
        <span className="emotion-placeholder">选择 Agent</span>
      </div>
    );
  }

  // 错误
  if (error && !emotion) {
    return (
      <div className="emotion-indicator">
        <span className="emotion-placeholder">—</span>
      </div>
    );
  }

  // 加载中
  if (loading && !emotion) {
    return (
      <div className="emotion-indicator">
        <span className="emotion-placeholder">加载中...</span>
      </div>
    );
  }

  if (!emotion) return null;

  const dotSize = (value: number) => 8 + Math.abs(value) * 8; // 8-16px

  const valenceColor = emotion.valence >= 0
    ? `rgb(${Math.round(76 + 179 * emotion.valence)}, ${Math.round(175 + 80 * (1 - emotion.valence))}, ${Math.round(80 - 80 * emotion.valence)})`
    : `rgb(${Math.round(76 + 76 * (1 + emotion.valence))}, ${Math.round(175 - 175 * Math.abs(emotion.valence))}, ${Math.round(80 - 80 * Math.abs(emotion.valence))})`;

  const arousalColor = emotion.arousal >= 0
    ? `rgb(${Math.round(255)}, ${Math.round(193 - 143 * emotion.arousal)}, ${Math.round(7)})`
    : `rgb(${Math.round(255 - 100 * Math.abs(emotion.arousal))}, ${Math.round(193 - 100 * Math.abs(emotion.arousal))}, ${Math.round(7)})`;

  const dominanceColor = emotion.dominance >= 0
    ? `rgb(${Math.round(33)}, ${Math.round(150 + 105 * emotion.dominance)}, ${Math.round(243)})`
    : `rgb(${Math.round(33 + 33 * (1 - Math.abs(emotion.dominance)))}, ${Math.round(150 - 100 * Math.abs(emotion.dominance))}, ${Math.round(243 - 143 * Math.abs(emotion.dominance))})`;

  // 趋势：与历史最后一条对比
  const lastEntry = history.length > 0 ? history[history.length - 1] : null;
  const prevV = lastEntry?.valence ?? emotion.valence;
  const prevA = lastEntry?.arousal ?? emotion.arousal;
  const prevD = lastEntry?.dominance ?? emotion.dominance;

  const tooltip = `愉悦度:${emotion.valence.toFixed(1)} 唤醒度:${emotion.arousal.toFixed(1)} 支配度:${emotion.dominance.toFixed(1)}`;

  // 提取各维度数组用于折线
  const vData = history.map((e) => e.valence);
  const aData = history.map((e) => e.arousal);
  const dData = history.map((e) => e.dominance);

  return (
    <div className="emotion-indicator" style={{ position: 'relative' }}>
      {/* 三色圆点 —— 可点击展开 */}
      <div
        onClick={toggleExpand}
        style={{ cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 4, padding: '2px 0' }}
        title={tooltip}
      >
        <span className="emotion-dot-label">V</span>
        <span
          className="emotion-dot"
          style={{
            width: dotSize(emotion.valence),
            height: dotSize(emotion.valence),
            background: valenceColor,
          }}
        />
        <span className="emotion-dot-label">A</span>
        <span
          className="emotion-dot"
          style={{
            width: dotSize(emotion.arousal),
            height: dotSize(emotion.arousal),
            background: arousalColor,
          }}
        />
        <span className="emotion-dot-label">D</span>
        <span
          className="emotion-dot"
          style={{
            width: dotSize(emotion.dominance),
            height: dotSize(emotion.dominance),
            background: dominanceColor,
          }}
        />
      </div>

      {/* 展开面板 */}
      {expanded && (
        <div
          style={{
            position: 'absolute',
            top: '100%',
            left: 0,
            marginTop: 4,
            padding: '8px 10px',
            background: 'rgba(20, 24, 36, 0.95)',
            border: '1px solid rgba(100, 120, 160, 0.3)',
            borderRadius: 6,
            zIndex: 100,
            minWidth: 220,
          }}
        >
          <div style={{ fontSize: 10, color: '#8b93a7', marginBottom: 4 }}>PAD 情绪趋势 (最近 30 条)</div>

          {/* Valence */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 4 }}>
            <span style={{ fontSize: 10, color: valenceColor, width: 14 }}>V</span>
            <span style={{ fontSize: 10, color: '#ccc', width: 36 }}>
              {emotion.valence.toFixed(2)} {trendArrow(emotion.valence, prevV)}
            </span>
            <MiniSparkline data={vData} width={120} height={16} color={valenceColor} range={[-1, 1]} />
          </div>

          {/* Arousal */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 4 }}>
            <span style={{ fontSize: 10, color: arousalColor, width: 14 }}>A</span>
            <span style={{ fontSize: 10, color: '#ccc', width: 36 }}>
              {emotion.arousal.toFixed(2)} {trendArrow(emotion.arousal, prevA)}
            </span>
            <MiniSparkline data={aData} width={120} height={16} color={arousalColor} range={[-1, 1]} />
          </div>

          {/* Dominance */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 4 }}>
            <span style={{ fontSize: 10, color: dominanceColor, width: 14 }}>D</span>
            <span style={{ fontSize: 10, color: '#ccc', width: 36 }}>
              {emotion.dominance.toFixed(2)} {trendArrow(emotion.dominance, prevD)}
            </span>
            <MiniSparkline data={dData} width={120} height={16} color={dominanceColor} range={[-1, 1]} />
          </div>
        </div>
      )}
    </div>
  );
};
