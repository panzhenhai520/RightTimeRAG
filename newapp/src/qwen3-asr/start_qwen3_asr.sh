#!/usr/bin/env bash
set -euo pipefail

PYTHON="${PYTHON:-/home/xsuper/miniconda3/envs/qwen3-asr/bin/python}"
SERVER_DIR="$(cd "$(dirname "$0")" && pwd)"
MODEL_PATH="${MODEL_PATH:-/home/xsuper/app/newapp/models/Qwen3-ASR-1.7B}"
PORT="${PORT:-9900}"
HOST="${HOST:-0.0.0.0}"
LOG_FILE="${LOG_FILE:-/home/xsuper/app/newapp/runtime/asr/qwen3-asr.log}"

export CUDA_VISIBLE_DEVICES="${CUDA_VISIBLE_DEVICES:-1}"
export MODEL_PATH PORT HOST

mkdir -p "$(dirname "$LOG_FILE")"

echo "$(date '+%F %T') qwen3-asr: starting on GPU ${CUDA_VISIBLE_DEVICES}, port ${PORT}" >> "$LOG_FILE"

exec "$PYTHON" "$SERVER_DIR/server.py" >> "$LOG_FILE" 2>&1
