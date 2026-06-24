#!/usr/bin/env bash
set -euo pipefail

IMAGE="${XINFERENCE_IMAGE:-xinference-bge-rerank-runtime:20260618}"
NAME="${XINFERENCE_CONTAINER_NAME:-xinference}"
BASE_ROOT="${BASE_ROOT:-/home/xsuper/app/base/xinference}"
PORT="${XINFERENCE_PORT:-9997}"
NETWORK_MODE="${XINFERENCE_NETWORK_MODE:-host}"

if ! docker image inspect "${IMAGE}" >/dev/null 2>&1; then
  echo "Missing Docker image: ${IMAGE}" >&2
  exit 1
fi

if docker ps -a --format '{{.Names}}' | grep -qx "${NAME}"; then
  docker stop "${NAME}" >/dev/null 2>&1 || true
  docker rm "${NAME}" >/dev/null
fi

network_args=()
port_args=()
if [ "${NETWORK_MODE}" = "host" ]; then
  network_args=(--network host)
else
  network_args=(--network bridge)
  port_args=(-p "${PORT}:9997")
fi

docker run -d \
  --name "${NAME}" \
  --restart unless-stopped \
  "${network_args[@]}" \
  --gpus '"device=0"' \
  -e NVIDIA_VISIBLE_DEVICES=0 \
  -e XINFERENCE_PORT="${PORT}" \
  "${port_args[@]}" \
  -v "${BASE_ROOT}/.xinference:/root/.xinference" \
  -v "${BASE_ROOT}/.cache/huggingface:/root/.cache/huggingface" \
  -v "${BASE_ROOT}/.cache/modelscope:/root/.cache/modelscope" \
  -v "${BASE_ROOT}/start.sh:/start.sh:ro" \
  "${IMAGE}" \
  /bin/bash /start.sh

echo "Started ${NAME} from ${IMAGE} on port ${PORT}."
echo "Expected models: bge-m3, bge-reranker-large."
