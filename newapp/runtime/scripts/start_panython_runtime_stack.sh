#!/usr/bin/env bash
set -euo pipefail

APP_ROOT="${APP_ROOT:-/home/xsuper/app/newapp}"

run_systemctl() {
  if [ "$(id -u)" -eq 0 ]; then
    systemctl "$@"
  else
    sudo systemctl "$@"
  fi
}

container_exists() {
  docker ps -a --format '{{.Names}}' | grep -qx "$1"
}

start_container() {
  local name="$1"
  if container_exists "${name}"; then
    docker start "${name}" >/dev/null
    echo "Started container: ${name}"
  else
    echo "Missing required container: ${name}" >&2
    return 1
  fi
}

wait_url() {
  local url="$1"
  local label="$2"
  local timeout="${3:-180}"
  local deadline
  deadline=$((SECONDS + timeout))

  echo "Waiting for ${label}: ${url}"
  while [ "${SECONDS}" -lt "${deadline}" ]; do
    if curl -fsS --max-time 5 "${url}" >/dev/null 2>&1; then
      echo "Ready: ${label}"
      return 0
    fi
    sleep 5
  done

  echo "Timed out waiting for ${label}" >&2
  return 1
}

echo "Step 1/6: Docker base services"
start_container docker-mysql-1
start_container docker-redis-1
start_container docker-minio-1
start_container docker-es01-1

echo "Step 2/6: Local auxiliary model services"
if container_exists xinference; then
  docker start xinference >/dev/null
else
  bash "${APP_ROOT}/runtime/scripts/recreate_xinference_runtime.sh"
fi

if container_exists xinference-vlm-gpu2; then
  docker start xinference-vlm-gpu2 >/dev/null
else
  bash "${APP_ROOT}/runtime/scripts/recreate_xinference_vlm_gpu2.sh"
fi

if container_exists cosyvoice3-gpu3; then
  docker start cosyvoice3-gpu3 >/dev/null
else
  bash "${APP_ROOT}/CosyVoice/deploy/recreate_cosyvoice3_gpu3_ortgpu.sh"
fi

wait_url http://127.0.0.1:9997/v1/models "Xinference bge/reranker" 420
wait_url http://127.0.0.1:9998/v1/models "Xinference VLM" 420
wait_url http://127.0.0.1:50001/health "CosyVoice3" 420

echo "Step 3/6: DeepSeek V4 Flash"
run_systemctl start ds4-server-ragflow.service
wait_url http://127.0.0.1:8106/v1/models "DS4 server" 1800

echo "Step 4/6: DS4 watchdog"
run_systemctl start ds4-watchdog-ragflow.service

echo "Step 5/6: RAGFlow source backend"
run_systemctl start ragflow-source.service
sleep 5

echo "Step 6/6: RAGFlow source frontend"
run_systemctl start ragflow-web-source.service
wait_url http://127.0.0.1:9222 "RAGFlow frontend" 180

bash "${APP_ROOT}/runtime/scripts/check_runtime_stack.sh"
