"""STT WebSocket 路由 — 语音转文字实时流式推理（前端控制录音生命周期）。

WebSocket 协议:
- 前端发送: 原始 PCM 音频数据 (16kHz, 16-bit, mono, little-endian)
- 后端返回: JSON 格式的识别结果
  - {"type": "partial", "text": "..."}      — 部分识别结果
  - {"type": "final", "text": "..."}        — 最终识别结果
  - {"type": "error", "message": "..."}     — 错误信息

前端控制录音周期（按住空格键=录音，松开=停止），断开 WebSocket 即停止。
"""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from backend.services.stt import VOSK_AVAILABLE, create_recognizer

router = APIRouter(prefix="/stt", tags=["stt"])
_log = logging.getLogger(__name__)


@router.websocket("/ws")
async def stt_websocket(ws: WebSocket):
    await ws.accept()

    if not VOSK_AVAILABLE:
        _log.warning("STT WebSocket 请求被拒绝: vosk 未安装")
        await ws.send_json({"type": "error", "message": "语音识别不可用: vosk 未安装，请安装 stt 可选依赖"})
        await ws.close(code=1011, reason="vosk not available")
        return

    _log.info("STT WebSocket 连接已建立 (前端控制模式)")
    rec = None

    try:
        rec = create_recognizer()

        while True:
            data = await ws.receive_bytes()
            if not data:
                continue

            if rec.AcceptWaveform(data):
                # 完整句子识别完成
                result = json.loads(rec.Result())
                text = result.get("text", "").strip()
                if text:
                    _log.debug("STT final: '%s'", text)
                    await ws.send_json({"type": "final", "text": text})
            else:
                # 部分识别结果
                partial = json.loads(rec.PartialResult())
                text = partial.get("partial", "").strip()
                if text:
                    await ws.send_json({"type": "partial", "text": text})

    except WebSocketDisconnect:
        _log.info("STT WebSocket 客户端断开")
    except Exception as e:
        _log.error("STT WebSocket 错误: %s", e)
        try:
            await ws.send_json({"type": "error", "message": str(e)})
        except Exception:
            pass
    finally:
        try:
            await ws.close()
        except Exception:
            pass
