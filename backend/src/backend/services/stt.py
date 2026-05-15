"""Vosk 语音转文字服务。

管理 Vosk 模型的加载、生命周期和流式推理。
vosk 为可选依赖，未安装时模块仍可导入但功能不可用。
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

_log = logging.getLogger(__name__)

try:
    import vosk
    VOSK_AVAILABLE = True
except (ImportError, OSError) as _exc:
    vosk = None  # type: ignore[assignment]
    VOSK_AVAILABLE = False
    _log.warning("vosk 不可用 (语音识别功能已禁用): %s", _exc)

# 模型路径（相对于 backend 目录）
_MODEL_REL_PATH = "models/vosk-model-cn-0.22"

_model: Optional["vosk.Model"] = None  # type: ignore[name-defined]


def _resolve_model_path() -> Path:
    """解析模型目录的绝对路径。"""
    # 此文件位于 backend/src/backend/services/stt.py
    # 向上找到 backend/ 根目录，再拼接 models/
    service_dir = Path(__file__).resolve().parent  # .../backend/src/backend/services
    backend_root = service_dir.parents[2]  # .../backend/
    model_path = (backend_root / _MODEL_REL_PATH).resolve()
    if not model_path.is_dir():
        raise FileNotFoundError(
            f"Vosk 模型目录不存在: {model_path}\n"
            f"请确保模型已解压到 backend/models/vosk-model-cn-0.22/"
        )
    return model_path


def init_model() -> "vosk.Model":  # type: ignore[name-defined]
    """初始化 Vosk 模型（启动时调用一次）。"""
    if not VOSK_AVAILABLE:
        raise RuntimeError("vosk 未安装，无法初始化 STT 模型。请安装: pip install hermes-digital-studio[stt]")

    global _model
    if _model is not None:
        return _model

    model_path = _resolve_model_path()
    _log.info("加载 Vosk 模型: %s", model_path)
    _model = vosk.Model(str(model_path))
    _log.info("Vosk 模型加载完成")
    return _model


def get_model() -> "vosk.Model":  # type: ignore[name-defined]
    """获取已加载的 Vosk 模型。"""
    global _model
    if _model is None:
        _model = init_model()
    return _model


def create_recognizer(sample_rate: float = 16000.0) -> "vosk.KaldiRecognizer":  # type: ignore[name-defined]
    """创建一个新的识别器实例。

    每个 WebSocket 连接应使用独立的 Recognizer。
    """
    if not VOSK_AVAILABLE:
        raise RuntimeError("vosk 未安装，STT 功能不可用")
    model = get_model()
    return vosk.KaldiRecognizer(model, sample_rate)


def shutdown_model() -> None:
    """释放 Vosk 模型资源。"""
    global _model
    if _model is not None:
        _log.info("释放 Vosk 模型")
        _model = None
