#!/usr/bin/env bash
# Studio 后端开发启动脚本（端口 9120，启用 --reload 热重载）
# 用法: ./backend/scripts/dev.sh
#   HERMES_STUDIO_NO_EMBEDDED_GATEWAY=1 ./backend/scripts/dev.sh  # 跳过嵌入式网关
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BACKEND_DIR="$(dirname "$SCRIPT_DIR")"

# uvicorn 从 src/ 目录运行，模块路径为 backend.main
cd "$BACKEND_DIR/src"

echo "[$(date '+%H:%M:%S')] 启动 HermesDigitalStudio 后端 (dev, 端口 9120, --reload)..."

uv run uvicorn backend.main:app \
    --host 0.0.0.0 \
    --port 9120 \
    --reload
