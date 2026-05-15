"""多厂商模型适配器 — Gemini / Ollama / 通用 OpenAI-compatible 统一接口。

提供统一的适配器注册表，由 ModelRouter 根据路由决策选择对应的适配器。
"""

from __future__ import annotations

import asyncio
import json
import logging
import urllib.request
import urllib.error
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, ClassVar

_log = logging.getLogger(__name__)


@dataclass
class ModelResponse:
    """统一模型响应。"""
    text: str
    model: str
    provider: str
    usage: dict = field(default_factory=dict)


class BaseAdapter(ABC):
    """所有厂商适配器的基类。"""

    provider: str = "unknown"

    @abstractmethod
    async def complete(self, prompt: str, model: str, **kwargs) -> ModelResponse:
        """执行一次补全请求。"""
        ...

    @abstractmethod
    async def is_available(self) -> bool:
        """检查适配器是否可用。"""
        ...


# ── Gemini 适配器 ──────────────────────────────────────────────────────


class GeminiAdapter(BaseAdapter):
    """Google Gemini API 适配器。

    使用 REST API (generativelanguage.googleapis.com)，
    需要设置环境变量 ``GEMINI_API_KEY``。
    """

    provider = "gemini"
    API_BASE: ClassVar[str] = "https://generativelanguage.googleapis.com/v1beta/models/"

    def __init__(self, api_key: str = ""):
        if not api_key:
            try:
                from backend.core.config import get_config
                api_key = get_config().gemini_api_key
            except Exception:
                pass
        self.api_key = api_key

    def _call_sync(self, prompt: str, model: str, **kwargs) -> ModelResponse:
        """同步调用（在线程池中执行）。"""
        if not self.api_key:
            raise RuntimeError("GEMINI_API_KEY 未设置")

        url = f"{self.API_BASE}{model}:generateContent?key={self.api_key}"
        body = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": kwargs.get("temperature", 0.7),
                "maxOutputTokens": kwargs.get("max_tokens", 4096),
            },
        }

        data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(
            url, data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=120) as resp:
            result = json.loads(resp.read().decode("utf-8"))

        text = ""
        usage = {}
        if "candidates" in result and result["candidates"]:
            parts = result["candidates"][0].get("content", {}).get("parts", [])
            text = "".join(p.get("text", "") for p in parts)
        if "usageMetadata" in result:
            u = result["usageMetadata"]
            usage = {
                "prompt_tokens": u.get("promptTokenCount", 0),
                "completion_tokens": u.get("candidatesTokenCount", 0),
                "total_tokens": u.get("totalTokenCount", 0),
            }

        return ModelResponse(text=text, model=model, provider=self.provider, usage=usage)

    async def complete(self, prompt: str, model: str = "gemini-2.0-flash", **kwargs) -> ModelResponse:
        try:
            return await asyncio.to_thread(self._call_sync, prompt, model, **kwargs)
        except urllib.error.HTTPError as e:
            _log.error("Gemini API error: %s %s", e.code, e.reason)
            raise RuntimeError(f"Gemini API 返回 {e.code}: {e.reason}")
        except Exception as e:
            _log.error("Gemini call failed: %s", e)
            raise

    def _check_sync(self) -> bool:
        if not self.api_key:
            return False
        url = f"{self.API_BASE}gemini-2.0-flash:generateContent?key={self.api_key}"
        body = json.dumps({"contents": [{"parts": [{"text": "ping"}]}]}).encode()
        req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"}, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=10):
                return True
        except Exception:
            return False

    async def is_available(self) -> bool:
        try:
            return await asyncio.to_thread(self._check_sync)
        except Exception:
            return False


# ── Ollama 适配器 ──────────────────────────────────────────────────────


class OllamaAdapter(BaseAdapter):
    """Ollama 本地模型适配器。

    默认连接 ``http://localhost:11434``，可通过 ``OLLAMA_HOST`` 环境变量覆盖。
    """

    provider = "ollama"

    def __init__(self, base_url: str = ""):
        if not base_url:
            try:
                from backend.core.config import get_config
                base_url = get_config().ollama_host
            except Exception:
                pass
        self.base_url = base_url or "http://localhost:11434"

    def _call_sync(self, prompt: str, model: str, **kwargs) -> ModelResponse:
        """同步调用（在线程池中执行）。"""
        url = f"{self.base_url}/api/generate"
        body = {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": kwargs.get("temperature", 0.7),
                "num_predict": kwargs.get("max_tokens", 4096),
            },
        }

        data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(
            url, data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=120) as resp:
            result = json.loads(resp.read().decode("utf-8"))

        text = result.get("response", "")
        usage = {
            "prompt_tokens": result.get("prompt_eval_count", 0),
            "completion_tokens": result.get("eval_count", 0),
            "total_tokens": result.get("prompt_eval_count", 0) + result.get("eval_count", 0),
        }

        return ModelResponse(text=text, model=model, provider=self.provider, usage=usage)

    async def complete(self, prompt: str, model: str = "llama3.2", **kwargs) -> ModelResponse:
        try:
            return await asyncio.to_thread(self._call_sync, prompt, model, **kwargs)
        except urllib.error.URLError as e:
            _log.warning("Ollama unavailable at %s: %s", self.base_url, e)
            raise RuntimeError(f"Ollama 服务不可用 ({self.base_url}): {e.reason}")
        except Exception as e:
            _log.error("Ollama call failed: %s", e)
            raise

    def _check_sync(self) -> bool:
        try:
            url = f"{self.base_url}/api/tags"
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=5):
                return True
        except Exception:
            return False

    async def is_available(self) -> bool:
        try:
            return await asyncio.to_thread(self._check_sync)
        except Exception:
            return False


# ── 适配器注册表 ───────────────────────────────────────────────────────


class AdapterRegistry:
    """多厂商适配器注册表。

    用法::

        registry = AdapterRegistry()
        registry.register(GeminiAdapter())
        registry.register(OllamaAdapter())

        adapter = registry.get("gemini")
        if adapter and await adapter.is_available():
            response = await adapter.complete("你好", model="gemini-2.0-flash")
    """

    def __init__(self):
        self._adapters: dict[str, BaseAdapter] = {}

    def register(self, adapter: BaseAdapter) -> None:
        """注册一个适配器。"""
        self._adapters[adapter.provider] = adapter
        _log.info("adapter_registry: registered %s adapter", adapter.provider)

    def get(self, provider: str) -> BaseAdapter | None:
        """获取指定提供商的适配器。"""
        return self._adapters.get(provider)

    def list_providers(self) -> list[str]:
        """列出所有已注册的提供商。"""
        return list(self._adapters.keys())

    async def list_available(self) -> list[str]:
        """列出当前可用的提供商。"""
        available: list[str] = []
        for name, adapter in self._adapters.items():
            try:
                if await adapter.is_available():
                    available.append(name)
            except Exception:
                pass
        return available


# ── 全局单例 ───────────────────────────────────────────────────────────

_registry: AdapterRegistry | None = None


def get_adapter_registry() -> AdapterRegistry:
    """获取适配器注册表全局单例。"""
    global _registry
    if _registry is None:
        _registry = AdapterRegistry()
        # 自动注册可用适配器
        try:
            _registry.register(GeminiAdapter())
        except Exception:
            _log.debug("adapter_registry: Gemini not configured, skipped")
        try:
            _registry.register(OllamaAdapter())
        except Exception:
            _log.debug("adapter_registry: Ollama not configured, skipped")
    return _registry
