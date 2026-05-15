"""HermesDigitalStudio 启动入口 — 对应 Spring Boot main()。

src-layout: 实际包位于 src/backend/，通过 PYTHONPATH 技巧使
src.backend 可作为顶层包导入。
"""

from __future__ import annotations

import sys
from pathlib import Path

# 将 src/ 的父目录加入 sys.path，使 "src.backend" 成为可导入的顶级包
# 例如: /path/to/HermesDigitalStudio/backend 运行时，
# 将 backend/src/ 加入后，"import src.backend" 即可解析到 src/backend/backend/
_this_file = Path(__file__).resolve()
_backend_dir = _this_file.parent  # .../HermesDigitalStudio/backend
_src_dir = _backend_dir / "src"
if str(_src_dir) not in sys.path:
    sys.path.insert(0, str(_src_dir))

# 未使用 .venv / 未 pip 安装 hermes-agent 时，从子模块源码解析 ``hermes_cli``（与 channel 层一致）
_repo_root = _backend_dir.parent
_hermes_vendor = _repo_root / "vendor" / "hermes-agent"
if _hermes_vendor.is_dir():
    _vp = str(_hermes_vendor)
    if _vp not in sys.path:
        sys.path.insert(0, _vp)

# 现在可以正常导入 src.backend 了
from src.backend.main import app  # noqa: E402

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=9120, log_level="info")
