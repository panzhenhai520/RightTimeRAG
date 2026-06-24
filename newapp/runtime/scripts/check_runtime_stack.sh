#!/usr/bin/env bash
set -euo pipefail

check_json_contains() {
  local url="$1"
  local needle="$2"
  local label="$3"

  echo "Checking ${label}: ${url}"
  local body
  body="$(curl -fsS "${url}")"
  if ! grep -q "${needle}" <<<"${body}"; then
    echo "Expected '${needle}' in ${label}, got:" >&2
    echo "${body}" >&2
    exit 1
  fi
}

check_json_contains "http://127.0.0.1:9997/v1/models" "bge-m3" "xinference embedding"
check_json_contains "http://127.0.0.1:9997/v1/models" "bge-reranker-large" "xinference reranker"
check_json_contains "http://127.0.0.1:9998/v1/models" "qwen2.5-vl-7b-awq-gpu2" "xinference VLM"
check_json_contains "http://127.0.0.1:50001/health" '"model_loaded":true' "CosyVoice3"

curl -fsS http://127.0.0.1:9222 >/dev/null
curl -fsS http://127.0.0.1:9388/v1/system/status >/dev/null 2>&1 || true
curl -fsS http://127.0.0.1:8106/v1/models >/dev/null

echo "Runtime stack checks passed."
