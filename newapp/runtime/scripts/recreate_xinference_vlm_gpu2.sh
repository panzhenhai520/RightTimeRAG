#!/usr/bin/env bash
set -euo pipefail

IMAGE="${VLM_IMAGE:-xinference-vlm-gpu2-qwen25vl-awq:20260618}"
NAME="${VLM_CONTAINER_NAME:-xinference-vlm-gpu2}"
BASE_ROOT="${BASE_ROOT:-/home/xsuper/app/base/xinference-vlm-gpu2}"
APP_ROOT="${APP_ROOT:-/home/xsuper/app/newapp}"
PORT="${VLM_PORT:-9998}"

if ! docker image inspect "${IMAGE}" >/dev/null 2>&1; then
  echo "Missing Docker image: ${IMAGE}" >&2
  exit 1
fi

if docker ps -a --format '{{.Names}}' | grep -qx "${NAME}"; then
  docker stop "${NAME}" >/dev/null 2>&1 || true
  docker rm "${NAME}" >/dev/null
fi

docker run -d \
  --name "${NAME}" \
  --restart unless-stopped \
  --gpus '"device=2"' \
  -e NVIDIA_VISIBLE_DEVICES=2 \
  -e XINFERENCE_PORT=9997 \
  -e VLM_MODEL_UID=qwen2.5-vl-7b-awq-gpu2 \
  -e VLM_MODEL_PATH=/models/Qwen2.5-VL-7B-Instruct-AWQ \
  -p "${PORT}:9997" \
  -v "${BASE_ROOT}/.xinference:/root/.xinference" \
  -v "${BASE_ROOT}/.cache/huggingface:/root/.cache/huggingface" \
  -v "${BASE_ROOT}/.cache/modelscope:/root/.cache/modelscope" \
  -v "${BASE_ROOT}/start_vlm_gpu2.sh:/start_vlm_gpu2.sh:ro" \
  -v "${APP_ROOT}/models:/models" \
  "${IMAGE}" \
  bash /start_vlm_gpu2.sh

echo "Started ${NAME} from ${IMAGE} on host port ${PORT}."
echo "Expected model: qwen2.5-vl-7b-awq-gpu2."
