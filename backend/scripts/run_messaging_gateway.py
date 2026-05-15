#!/usr/bin/env python3
"""前台运行 Hermes 消息网关（与 Studio 嵌入式子进程同一入口）。

分两个终端看日志：

终端 A — Studio API（不拉起嵌入式网关）::

    cd backend && export HERMES_STUDIO_NO_EMBEDDED_GATEWAY=1 && uv run python main.py

终端 B — 消息网关（直连本终端 stdout/stderr）::

    cd backend && uv run python scripts/run_messaging_gateway.py

或仓库根目录: scripts/dev-studio-backend.sh 与 scripts/dev-messaging-gateway.sh
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

_SCRIPT = Path(__file__).resolve()
_BACKEND_DIR = _SCRIPT.parents[1]
_REPO_ROOT = _BACKEND_DIR.parent
_VENDOR_ROOT = _REPO_ROOT / "vendor" / "hermes-agent"


def main() -> int:
    if not _VENDOR_ROOT.is_dir():
        print("error: vendor/hermes-agent not found:", _VENDOR_ROOT, file=sys.stderr)
        return 1

    os.environ["PYTHONUNBUFFERED"] = "1"
    sep = os.pathsep
    os.environ["PYTHONPATH"] = str(_VENDOR_ROOT) + sep + os.environ.get("PYTHONPATH", "").strip(sep)

    sys.path.insert(0, str(_VENDOR_ROOT))
    os.chdir(str(_VENDOR_ROOT))

    from gateway.run import start_gateway

    ok = asyncio.run(start_gateway(verbosity=1))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
