"""TTS 模型预加载 — 在 Agent 网关启动前预热本地 TTS 引擎。

避免前端页面加载后首次触发 TTS 时出现懒加载延迟。
对在线 provider（Edge/OpenAI/ElevenLabs 等）仅做导入验证；对本地
provider（Piper/KittenTTS）触发模型下载和首次加载。

用法：
    在 ``main.py`` 的 ``_preload_all_models()`` 中调用::

        from backend.services.tts_preload import prewarm_tts_models
        prewarm_tts_models()
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
import yaml
from pathlib import Path

_log = logging.getLogger(__name__)

# TTS provider：需要预热的本地引擎
_LOCAL_TTS_PROVIDERS = frozenset({"piper", "kittentts"})


def prewarm_tts_models() -> dict[str, bool]:
    """预加载所有本地 TTS 模型。

    读取 ``~/.hermes/config.yaml`` 中的 ``tts`` 配置节，推断当前
    使用的 provider，对本地引擎执行预热。

    Returns:
        {"piper": True/False, "kittentts": True/False}
    """
    tts_config = _read_tts_config()
    if not tts_config:
        _log.info("tts_preload: no TTS config found, skip")
        return {}

    provider = _resolve_provider(tts_config)
    results: dict[str, bool] = {}

    # 1. Piper 本地 VITS 引擎
    if provider == "piper" or _is_piper_installed():
        try:
            results["piper"] = _prewarm_piper(tts_config)
        except Exception as e:
            _log.warning("tts_preload: piper prewarm failed: %s", e)
            results["piper"] = False
    else:
        results["piper"] = False

    # 2. KittenTTS 本地 ONNX 引擎
    if provider == "kittentts" or _is_kittentts_installed():
        try:
            results["kittentts"] = _prewarm_kittentts(tts_config)
        except Exception as e:
            _log.warning("tts_preload: kittentts prewarm failed: %s", e)
            results["kittentts"] = False
    else:
        results["kittentts"] = False

    _log.info("tts_preload: done %s", results)
    return results


# ── 配置读取 ──────────────────────────────────────────────────────────────


def _read_tts_config() -> dict | None:
    """从 ``~/.hermes/config.yaml`` 读取 TTS 配置。"""
    config_path = Path.home() / ".hermes" / "config.yaml"
    if not config_path.is_file():
        return None

    try:
        raw = yaml.safe_load(config_path.read_text())
        if not isinstance(raw, dict):
            return None
        tts = raw.get("tts")
        return tts if isinstance(tts, dict) else {}
    except Exception as e:
        _log.debug("tts_preload: cannot read config: %s", e)
        return None


def _resolve_provider(tts_config: dict) -> str:
    """从 TTS 配置中解析当前 provider 名称。"""
    return (tts_config.get("provider") or "edge").lower().strip()


# ── 可用性检查 ───────────────────────────────────────────────────────────


def _is_piper_installed() -> bool:
    """检查 piper-tts 包是否已安装。"""
    try:
        import importlib.util
        return importlib.util.find_spec("piper") is not None
    except Exception:
        return False


def _is_kittentts_installed() -> bool:
    """检查 kittentts 包是否已安装。"""
    try:
        import importlib.util
        return importlib.util.find_spec("kittentts") is not None
    except Exception:
        return False


# ── Piper 预热 ────────────────────────────────────────────────────────────


def _get_piper_voices_dir() -> Path:
    """获取 Piper 语音模型缓存目录。"""
    root = Path.home() / ".hermes" / "cache" / "piper-voices"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _prewarm_piper(tts_config: dict) -> bool:
    """预热 Piper 本地 TTS：确保语音模型已下载可用。"""
    piper_cfg = tts_config.get("piper", {})
    if not isinstance(piper_cfg, dict):
        piper_cfg = {}

    voice = (piper_cfg.get("voice") or "").strip()
    if not voice:
        voice = "en_US-lessac-medium"

    download_dir = Path(piper_cfg.get("voices_dir") or _get_piper_voices_dir()).expanduser()

    # 1. 检查 .onnx 文件是否已存在
    onnx_path = download_dir / f"{voice}.onnx"
    json_path = download_dir / f"{voice}.onnx.json"

    if onnx_path.exists() and json_path.exists():
        _log.info("tts_preload: piper voice '%s' already cached", voice)
        # 触发首次模型加载（PiperVoice.load）
        try:
            from piper import PiperVoice
            PiperVoice.load(str(onnx_path), use_cuda=False)
            _log.info("tts_preload: piper voice '%s' loaded successfully", voice)
        except Exception as e:
            _log.warning("tts_preload: piper voice load attempt: %s (non-fatal)", e)
        return True

    # 2. 下载语音模型（首次）
    _log.info("tts_preload: downloading piper voice '%s' to %s ...", voice, download_dir)
    try:
        result = subprocess.run(
            [sys.executable, "-m", "piper.download_voices", voice,
             "--download-dir", str(download_dir)],
            capture_output=True, text=True, timeout=300,
        )
        if result.returncode != 0:
            _log.warning("tts_preload: piper download failed: %s", result.stderr[:200])
            return False

        _log.info("tts_preload: piper voice '%s' downloaded", voice)
        return True
    except subprocess.TimeoutExpired:
        _log.warning("tts_preload: piper download timed out")
        return False
    except Exception as e:
        _log.warning("tts_preload: piper download error: %s", e)
        return False


# ── KittenTTS 预热 ───────────────────────────────────────────────────────


def _prewarm_kittentts(tts_config: dict) -> bool:
    """预热 KittenTTS 本地 ONNX 模型：触发首次模型加载。

    KittenTTS 模型约 25-80MB，首次加载需若干秒，预热后可避免
    运行时延迟。
    """
    from kittentts import KittenTTS

    kt_cfg = tts_config.get("kittentts", {})
    if not isinstance(kt_cfg, dict):
        kt_cfg = {}

    model_name = kt_cfg.get("model", "kittentts_v1.0")
    _log.info("tts_preload: loading KittenTTS model '%s' ...", model_name)

    try:
        model = KittenTTS(model_name)
        _log.info("tts_preload: KittenTTS model '%s' loaded (%s)", model_name, type(model).__name__)
        return True
    except Exception as e:
        _log.warning("tts_preload: KittenTTS model load failed: %s", e)
        return False
