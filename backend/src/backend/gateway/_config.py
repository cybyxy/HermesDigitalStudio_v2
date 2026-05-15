"""Gateway 模块级常量与路径解析。

所有 gateway 子模块引用的路径常量和配置在此处集中定义。
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

_log = logging.getLogger("backend.gateway")

# tui_gateway.entry provides the JSON-RPC-over-stdio gateway main loop.
# __file__ = backend/src/backend/gateway/_config.py
#   parent = gateway/ → parent = backend/ → parent = src/ → parent = backend dir
_BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent
# Monorepo: HermesDigitalStudio_v2/backend, HermesDigitalStudio_v2/vendor/hermes-agent
_REPO_ROOT = _BACKEND_ROOT.parent
_HERMES_VENDOR_ROOT = _REPO_ROOT / "vendor" / "hermes-agent"
# Legacy name kept for cwd (subprocess expects a directory on PYTHONPATH with hermes)
_HERMES_PROJECT_ROOT = _BACKEND_ROOT
_HERMES_ENTRY = str(_HERMES_VENDOR_ROOT / "tui_gateway" / "entry.py")

# JSON-RPC 调用默认超时（秒）
_SUBPROCESS_TIMEOUT_S: float = 30.0

# config.yaml 中 model.api_key 常见 ``${OPENROUTER_API_KEY}`` 形式；须用即将传给子进程的 env 展开，
# 不能依赖 load_config() 缓存（父进程若曾用空环境展开过，缓存里 api_key 会一直为空 → profile 子进程 401）。
_ENV_REF_PATTERN = re.compile(r"\$\{([A-Za-z0-9_]+)\}")
