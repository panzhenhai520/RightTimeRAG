# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository Overview

This is the Panython platform workspace — a self-hosted RAG (Retrieval-Augmented Generation) deployment built on top of [RAGFlow](https://ragflow.io/) with local GPU-accelerated model serving. The repo root at `/home/xsuper/app` contains four top-level components:

| Directory | Purpose |
|---|---|
| `newapp/ragflow/` | **Active** RAGFlow v0.25.6 source code (runs via systemd) |
| `newapp/ragclaw/` | Custom web crawler that feeds articles into RAGFlow |
| `newapp/runtime/` | Startup scripts, runtime logs, DS4 health state, and service compose overrides |
| `newapp/src/ds4-tp/` | Custom DeepSeek V4 Flash inference engine written in C (not generic GGUF) |
| `newapp/models/` | Local model weights (DeepSeek-v4-gguf, Qwen2.5-VL-7B, CosyVoice3, etc.) |
| `newapp/CosyVoice/` | CosyVoice3 TTS deployment |
| `base/` | Xinference Docker service definitions (embedding/reranking/VLM) |
| `ragflow/` | **Legacy** Docker-based deployment of RAGFlow v0.19.0 (kept for data safety, not primary) |

## Active Service Architecture

The production stack runs as a mix of Docker containers and systemd services. The canonical startup order and port assignments:

### Docker containers (base services)
| Container | Purpose |
|---|---|
| `docker-mysql-1` | MySQL 8.0 database |
| `docker-redis-1` | Redis / Valkey cache |
| `docker-minio-1` | MinIO object storage |
| `docker-es01-1` | Elasticsearch 8.11.3 document index |
| `xinference` | GPU0, port **9997** — bge-m3 embedding + bge-reranker-large |
| `xinference-vlm-gpu2` | GPU2, port **9998** — Qwen2.5-VL-7B-AWQ vision model |
| `cosyvoice3-gpu3` | GPU3, port **50001** — CosyVoice3 TTS |

### Systemd services
| Unit | Port | Purpose |
|---|---|---|
| `ds4-server-ragflow.service` | **8106** | DeepSeek V4 Flash OpenAI-compatible API |
| `ds4-watchdog-ragflow.service` | — | Monitors DS4 KV cache health and triggers restarts |
| `ragflow-source.service` | **9388** | RAGFlow Python backend |
| `ragflow-web-source.service` | **9222** | RAGFlow Vite dev frontend |

DS4 health state is written to `newapp/runtime/ds4/ds4-health.json` by the watchdog.

### Starting the full stack
```bash
# Ordered startup (waits for health checks at each step)
bash /home/xsuper/app/newapp/runtime/scripts/start_panython_runtime_stack.sh

# Validate all services are healthy
bash /home/xsuper/app/newapp/runtime/scripts/check_runtime_stack.sh
```

Systemd-only (backend/frontend):
```bash
sudo systemctl start ragflow-source.service
sudo systemctl start ragflow-web-source.service
```

Rebuild Docker model containers if lost (use fixed image tags, not `latest`):
```bash
bash /home/xsuper/app/newapp/runtime/scripts/recreate_xinference_runtime.sh
bash /home/xsuper/app/newapp/runtime/scripts/recreate_xinference_vlm_gpu2.sh
bash /home/xsuper/app/newapp/CosyVoice/deploy/recreate_cosyvoice3_gpu3_ortgpu.sh
```

## RAGFlow Source (`newapp/ragflow/`)

See `newapp/ragflow/CLAUDE.md` for full development guide. Summary:

- Python backend: `api/` (Flask, entry `api/ragflow_server.py`)
- Frontend: `web/` (React/TypeScript/Vite)
- RAG pipeline: `rag/`, document processing: `deepdoc/`, agent system: `agent/`
- Python managed with `uv` (`pyproject.toml`, requires Python 3.13)

```bash
# Backend dev (from newapp/ragflow/)
source .venv/bin/activate
export PYTHONPATH=$(pwd)
bash docker/launch_backend_service.sh

# Tests
uv run pytest

# Lint
ruff check && ruff format

# Frontend dev
cd web && npm run dev -- --host 0.0.0.0
```

Logs go to `newapp/ragflow/logs/ragflow_server.log` (via systemd) and `newapp/runtime/ragflow-vite-9222.log` (frontend).

## ragclaw Web Crawler (`newapp/ragclaw/`)

Flask-based web crawler that discovers article links, extracts content via Playwright, deduplicates, and uploads to RAGFlow knowledge bases.

- Port: **8003**
- Database: `crawler_articles.db` (SQLite)
- Auth sessions: `auth_storage/` (do not delete — preserves login cookies for authenticated crawling)

```bash
cd /home/xsuper/app/newapp/ragclaw
pip install -r requirements.txt
python -m playwright install chromium
python init_sqlite_database.py init
python start_with_schedule.py      # Production entry: web server + scheduler
```

Key files: `firecrawl_app.py` (Flask app), `scheduler.py` (cron tasks), `article_link_extractor.py` (main crawl pipeline), `ragflow_client.py` (RAGFlow upload client).

## DS4 Inference Engine (`newapp/src/ds4-tp/`)

A DeepSeek V4 Flash specific inference engine in C — not a generic GGUF runner. Runs on this server via `llama.cpp`-style tensor parallelism across 4x RTX 5880 Ada GPUs (ports vary by context size config).

- Source: `ds4.c`, `ds4_cli.c`, `ds4_server.c`
- Build: `make` (no C++)
- Tests: `make test`
- The watchdog (`ds4-watchdog-ragflow.service`) monitors KV cache pressure and restarts DS4 when remaining tokens fall below threshold

## Legacy Deployment (`ragflow/`)

RAGFlow v0.19.0-slim running via Docker Compose with customized Python files bind-mounted in. **Do not run `docker compose down -v`** — the data volumes (`mysql_data/`, `minio_data/`, `esdata01/`, `redis_data/`) are preserved intentionally.

Custom overrides live in `ragflow/app/server/` and are mounted over upstream RAGFlow files. The pre-built custom frontend is in `ragflow/app/web/dist/`. A `custom-server` Node.js container runs on port **3010**.

Configuration: `ragflow/.env` and `ragflow/service_conf.yaml.template`.

## GPU Assignment Summary

| GPU | Container/Service | Model |
|---|---|---|
| GPU 0 | `xinference` | bge-m3, bge-reranker-large |
| GPU 2 | `xinference-vlm-gpu2` | Qwen2.5-VL-7B-AWQ |
| GPU 3 | `cosyvoice3-gpu3` | CosyVoice3 TTS |
| GPU 0–3 | `ds4-server-ragflow` | DeepSeek V4 Flash (tensor parallel) |
