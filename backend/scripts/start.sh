#!/usr/bin/env bash
# Studio 后端生产启动脚本（端口 9120，无 --reload，日志写入 scripts/logs/）
# 用法: ./backend/scripts/start.sh
#   HERMES_STUDIO_NO_EMBEDDED_GATEWAY=1 ./backend/scripts/start.sh  # 跳过嵌入式网关
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BACKEND_DIR="$(dirname "$SCRIPT_DIR")"
LOG_DIR="$SCRIPT_DIR/logs"
mkdir -p "$LOG_DIR"

# uvicorn 从 src/ 目录运行，模块路径为 backend.main
cd "$BACKEND_DIR/src"

echo "[$(date '+%H:%M:%S')] 启动 HermesDigitalStudio 后端 (端口 9120, logs=$LOG_DIR/backend.log)..."

uv run uvicorn backend.main:app \
    --host 0.0.0.0 \
    --port 9120 \
    2>&1 | tee -a "$LOG_DIR/backend.log"
