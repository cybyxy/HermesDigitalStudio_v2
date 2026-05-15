/**
 * useVoiceRecognition — 语音识别 Hook（按住录音，松开发送）。
 *
 * 通过 WebSocket 连接后端 Vosk STT 服务，前端控制录音生命周期。
 *
 * 用法:
 *   const { isRecording, transcript, lastResult } = useVoiceRecognition({ recording: pressed });
 *
 * 架构:
 *   麦克风 → AudioContext → ScriptProcessorNode (下采样到16kHz) → Int16 PCM → WebSocket → 后端Vosk → JSON结果
 */

import { useState, useRef, useEffect } from 'react';

/** WebSocket 返回的消息 */
interface SttMessage {
  type: 'partial' | 'final' | 'error';
  text?: string;
  message?: string;
}

export interface VoiceRecognitionState {
  /** 当前是否正在录音 */
  isRecording: boolean;
  /** 当前实时转写文本 */
  partialText: string;
  /** 累积的 final 文本 */
  accumulatedText: string;
  /** 合并后的完整转写结果（partial + accumulated） */
  transcript: string;
  /** 录音停止后交付的最终结果 */
  lastResult: string;
  /** 错误信息 */
  error: string | null;
  /** WebSocket 是否就绪 */
  ready: boolean;
}

export interface UseVoiceRecognitionOptions {
  /** 是否正在录音（true=开始/继续，false=停止并交付结果） */
  recording: boolean;
}

export function useVoiceRecognition({ recording }: UseVoiceRecognitionOptions) {
  const [isRecording, setIsRecording] = useState(false);
  const [partialText, setPartialText] = useState('');
  const [accumulatedText, setAccumulatedText] = useState('');
  const [transcript, setTranscript] = useState('');
  const [lastResult, setLastResult] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [ready, setReady] = useState(false);

  // 持久引用
  const wsRef = useRef<WebSocket | null>(null);
  const audioCtxRef = useRef<AudioContext | null>(null);
  const processorRef = useRef<ScriptProcessorNode | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const partialRef = useRef('');
  const accumulatedRef = useRef('');

  // ── 音频工具函数 ──────────────────────────────────────────

  function floatTo16BitPCM(float32: Float32Array): Int16Array {
    const buf = new Int16Array(float32.length);
    for (let i = 0; i < float32.length; i++) {
      const s = Math.max(-1, Math.min(1, float32[i]));
      buf[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
    }
    return buf;
  }

  function downsample(buffer: Float32Array, sourceRate: number, targetRate = 16000): Float32Array {
    if (sourceRate === targetRate) return buffer;
    const ratio = sourceRate / targetRate;
    const newLength = Math.round(buffer.length / ratio);
    const result = new Float32Array(newLength);
    for (let i = 0; i < newLength; i++) {
      const srcIdx = Math.round(i * ratio);
      result[i] = buffer[srcIdx] ?? 0;
    }
    return result;
  }

  function sendAudioData(pcm: Int16Array) {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(pcm.buffer);
    }
  }

  // ── WebSocket 消息处理 ────────────────────────────────────

  function handleWsMessage(event: MessageEvent) {
    try {
      const msg: SttMessage = JSON.parse(event.data);
      switch (msg.type) {
        case 'partial': {
          partialRef.current = msg.text || '';
          const full = accumulatedRef.current + partialRef.current;
          setPartialText(partialRef.current);
          setTranscript(full);
          break;
        }

        case 'final': {
          const text = msg.text || '';
          if (text) {
            accumulatedRef.current += text;
            partialRef.current = '';
            setAccumulatedText(accumulatedRef.current);
            setPartialText('');
            setTranscript(accumulatedRef.current);
          }
          break;
        }

        case 'error':
          setError(msg.message || 'STT 错误');
          break;
      }
    } catch {
      // 忽略解析错误
    }
  }

  // ── WebSocket 连接管理 ────────────────────────────────────

  function connectWs(): WebSocket {
    if (wsRef.current?.readyState === WebSocket.OPEN) return wsRef.current;

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const host = window.location.host;
    const ws = new WebSocket(`${protocol}//${host}/api/stt/ws`);

    ws.binaryType = 'arraybuffer';
    ws.onmessage = handleWsMessage;
    ws.onopen = () => setReady(true);
    ws.onerror = () => setError('WebSocket 连接失败');
    ws.onclose = () => setReady(false);

    wsRef.current = ws;
    return ws;
  }

  function closeWs() {
    if (wsRef.current) {
      wsRef.current.onmessage = null;
      wsRef.current.close();
      wsRef.current = null;
    }
  }

  // ── 麦克风管理 ────────────────────────────────────────────

  async function startMic() {
    const stream = await navigator.mediaDevices.getUserMedia({
      audio: {
        sampleRate: { ideal: 16000 },
        channelCount: { ideal: 1 },
        echoCancellation: true,
        noiseSuppression: true,
      },
    });
    streamRef.current = stream;

    const audioCtx = new AudioContext();
    audioCtxRef.current = audioCtx;
    const sourceSampleRate = audioCtx.sampleRate;

    const source = audioCtx.createMediaStreamSource(stream);
    const processor = audioCtx.createScriptProcessor(4096, 1, 1);
    processorRef.current = processor;

    const ws = connectWs();

    processor.onaudioprocess = (e) => {
      if (ws.readyState !== WebSocket.OPEN) return;
      const inputData = e.inputBuffer.getChannelData(0);
      const downsampled = downsample(inputData, sourceSampleRate, 16000);
      const pcm = floatTo16BitPCM(downsampled);
      sendAudioData(pcm);
    };

    source.connect(processor);
    processor.connect(audioCtx.destination);
  }

  function stopMic() {
    if (processorRef.current) {
      processorRef.current.disconnect();
      processorRef.current = null;
    }
    if (audioCtxRef.current) {
      audioCtxRef.current.close().catch(() => {});
      audioCtxRef.current = null;
    }
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((t) => t.stop());
      streamRef.current = null;
    }
    closeWs();
  }

  /** 停止录音并交付结果：累积文本 + 最后的部分转写 */
  function flushAndCleanup() {
    const text = accumulatedRef.current + partialRef.current;
    const cleaned = text.replace(/\s/g, '');
    accumulatedRef.current = '';
    partialRef.current = '';

    setAccumulatedText('');
    setPartialText('');
    setTranscript('');
    setReady(false);
    setIsRecording(false);

    if (cleaned) {
      setLastResult(cleaned);
    }
  }

  // ── recording 控制录音生命周期 ──────────────────────────────

  useEffect(() => {
    if (recording) {
      // 开始录音
      accumulatedRef.current = '';
      partialRef.current = '';
      setAccumulatedText('');
      setPartialText('');
      setTranscript('');
      setLastResult('');
      setError(null);
      setLastResult('');
      setIsRecording(true);
      startMic().catch((err: unknown) => {
        const message = err instanceof DOMException
          ? (err.name === 'NotAllowedError' ? '麦克风权限被拒绝' : err.message)
          : '无法启动麦克风';
        setError(message);
        setIsRecording(false);
      });
    } else {
      // 停止录音，交付结果
      flushAndCleanup();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [recording]);

  // 组件卸载时清理
  useEffect(() => {
    return () => {
      if (wsRef.current || streamRef.current) {
        stopMic();
      }
    };
  }, []);

  return {
    isRecording,
    partialText,
    accumulatedText,
    transcript,
    lastResult,
    error,
    ready,
    // 向后兼容
    listeningState: (isRecording ? 'active' : 'idle') as 'idle' | 'listening' | 'active',
    finalText: accumulatedText,
  };
}
