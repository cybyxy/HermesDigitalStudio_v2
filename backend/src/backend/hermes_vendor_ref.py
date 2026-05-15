"""
Hermes 依赖引用说明（本仓库自建，不修改 vendor 内源码）。

- 上游 / 本地拷贝目录：仓库根下 ``vendor/hermes-agent``（勿提交 git，见根 README）。
- 设计说明与子 Agent 记忆概念：``docs/hermes-memory-and-vendor.md``。
- 运行时由启动脚本将上述路径加入 ``PYTHONPATH`` 或安装为可编辑依赖，具体见 ``backend/pyproject.toml`` 与 ``main.py``。
"""

from __future__ import annotations

from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
HERMES_AGENT_VENDOR = _REPO_ROOT / "vendor" / "hermes-agent"


def hermes_agent_root() -> Path:
    """返回本机 Hermes Agent 包根目录（vendor 拷贝）。"""
    return HERMES_AGENT_VENDOR
