#
#  Copyright 2026 The InfiniFlow Authors. All Rights Reserved.
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.
#

import contextlib
import json
import logging
import time
from typing import Any

from rag.utils.redis_conn import REDIS_CONN


class AgentRunStatus:
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCEL_REQUESTED = "cancel_requested"
    CANCELED = "canceled"


class AgentRunService:
    TTL_SECONDS = 24 * 60 * 60
    MAX_EVENTS = 2000
    ACTIVE_STATUSES = {
        AgentRunStatus.QUEUED,
        AgentRunStatus.RUNNING,
        AgentRunStatus.CANCEL_REQUESTED,
    }
    SUMMARY_STRING_LIMIT = 500
    SUMMARY_LIST_LIMIT = 5
    SUMMARY_DICT_LIMIT = 20
    SENSITIVE_KEYS = {
        "api_key",
        "apikey",
        "authorization",
        "cookie",
        "password",
        "secret",
        "token",
    }

    @classmethod
    def _state_key(cls, tenant_id: str, run_id: str) -> str:
        return f"agent_run:{tenant_id}:{run_id}:state"

    @classmethod
    def _events_key(cls, tenant_id: str, run_id: str) -> str:
        return f"agent_run:{tenant_id}:{run_id}:events"

    @classmethod
    def _active_runs_key(cls, tenant_id: str, agent_id: str) -> str:
        return f"agent_run:{tenant_id}:{agent_id}:active"

    @staticmethod
    def _load_json(key: str, default: Any):
        raw = REDIS_CONN.get(key)
        if not raw:
            return default
        try:
            return json.loads(raw)
        except Exception:
            logging.warning("AgentRunService failed to parse redis payload. key=%s", key)
            return default

    @classmethod
    def start(
        cls,
        tenant_id: str,
        run_id: str,
        agent_id: str,
        session_id: str,
        message_id: str,
        task_id: str,
        query: str,
        status: str = AgentRunStatus.RUNNING,
        mode: str = "sse",
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        now = time.time()
        state = {
            "run_id": run_id,
            "agent_id": agent_id,
            "session_id": session_id,
            "message_id": message_id,
            "task_id": task_id,
            "status": status,
            "mode": mode,
            "query": query,
            "metadata": metadata or {},
            "created_at": now,
            "updated_at": now,
            "finished_at": None,
            "event_count": 0,
            "error": "",
            "progress": {
                "percent": 0,
                "total_nodes": 0,
                "succeeded_nodes": 0,
                "failed_nodes": 0,
                "running_nodes": 0,
                "current_nodes": [],
                "last_event_seq": None,
                "last_event_type": None,
            },
            "downloads": [],
        }
        try:
            REDIS_CONN.set_obj(cls._state_key(tenant_id, run_id), state, cls.TTL_SECONDS)
            REDIS_CONN.set_obj(cls._events_key(tenant_id, run_id), [], cls.TTL_SECONDS)
            if status in cls.ACTIVE_STATUSES:
                REDIS_CONN.sadd(cls._active_runs_key(tenant_id, agent_id), run_id)
        except Exception:
            logging.exception("AgentRunService.start failed. run_id=%s", run_id)
        return state

    @classmethod
    def mark_running(cls, tenant_id: str, run_id: str) -> None:
        try:
            state = cls.get_state(tenant_id, run_id) or {}
            state["status"] = AgentRunStatus.RUNNING
            state["updated_at"] = time.time()
            REDIS_CONN.set_obj(cls._state_key(tenant_id, run_id), state, cls.TTL_SECONDS)
            if state.get("agent_id"):
                REDIS_CONN.sadd(cls._active_runs_key(tenant_id, state["agent_id"]), run_id)
        except Exception:
            logging.exception("AgentRunService.mark_running failed. run_id=%s", run_id)

    @classmethod
    def get_state(cls, tenant_id: str, run_id: str) -> dict[str, Any] | None:
        state = cls._load_json(cls._state_key(tenant_id, run_id), None)
        return state if isinstance(state, dict) else None

    @classmethod
    def list_active(cls, tenant_id: str, agent_id: str, session_id: str | None = None) -> list[dict[str, Any]]:
        try:
            run_ids = REDIS_CONN.smembers(cls._active_runs_key(tenant_id, agent_id)) or []
        except Exception:
            logging.exception("AgentRunService.list_active failed. agent_id=%s", agent_id)
            return []

        states = []
        for run_id in run_ids:
            state = cls.get_state(tenant_id, str(run_id))
            if not state:
                with contextlib.suppress(Exception):
                    REDIS_CONN.srem(cls._active_runs_key(tenant_id, agent_id), run_id)
                continue
            if state.get("status") not in cls.ACTIVE_STATUSES:
                with contextlib.suppress(Exception):
                    REDIS_CONN.srem(cls._active_runs_key(tenant_id, agent_id), run_id)
                continue
            if session_id and state.get("session_id") != session_id:
                continue
            states.append(state)

        states.sort(key=lambda item: item.get("updated_at") or item.get("created_at") or 0, reverse=True)
        return states

    @classmethod
    def get_events(cls, tenant_id: str, run_id: str, after_seq: int = -1) -> list[dict[str, Any]]:
        events = cls._load_json(cls._events_key(tenant_id, run_id), [])
        if not isinstance(events, list):
            return []
        return [event for event in events if int(event.get("seq", -1)) > after_seq]

    @classmethod
    def _is_sensitive_key(cls, key: str) -> bool:
        normalized = str(key or "").lower().replace("-", "_")
        return any(item in normalized for item in cls.SENSITIVE_KEYS)

    @classmethod
    def _summarize_value(cls, value: Any, depth: int = 0) -> Any:
        if depth > 2:
            return {"type": type(value).__name__, "summary": "max depth reached"}
        if value is None or isinstance(value, (bool, int, float)):
            return value
        if isinstance(value, str):
            if len(value) <= cls.SUMMARY_STRING_LIMIT:
                return value
            return {
                "type": "string",
                "length": len(value),
                "preview": value[: cls.SUMMARY_STRING_LIMIT],
            }
        if isinstance(value, list):
            return {
                "type": "list",
                "length": len(value),
                "items": [cls._summarize_value(item, depth + 1) for item in value[: cls.SUMMARY_LIST_LIMIT]],
            }
        if isinstance(value, dict):
            result = {}
            for idx, (key, item) in enumerate(value.items()):
                if idx >= cls.SUMMARY_DICT_LIMIT:
                    result["_truncated_keys"] = len(value) - cls.SUMMARY_DICT_LIMIT
                    break
                result[key] = "***" if cls._is_sensitive_key(key) else cls._summarize_value(item, depth + 1)
            return result
        return str(value)[: cls.SUMMARY_STRING_LIMIT]

    @classmethod
    def _extract_downloads(cls, value: Any) -> list[dict[str, Any]]:
        downloads = []
        if isinstance(value, dict):
            if value.get("doc_id") and (value.get("filename") or value.get("file_name")):
                item = {
                    "artifact_id": value.get("artifact_id") or value.get("doc_id"),
                    "doc_id": value.get("doc_id"),
                    "filename": value.get("filename") or value.get("file_name"),
                }
                for key in ("mime_type", "size", "download_url", "metadata"):
                    if value.get(key) is not None:
                        item[key] = value.get(key)
                metadata = value.get("metadata") or {}
                run_id = value.get("run_id") or metadata.get("run_id")
                node_id = value.get("node_id") or metadata.get("node_id")
                if run_id:
                    item["run_id"] = run_id
                if node_id:
                    item["node_id"] = node_id
                downloads.append(item)
            for item in value.values():
                downloads.extend(cls._extract_downloads(item))
        elif isinstance(value, list):
            for item in value:
                downloads.extend(cls._extract_downloads(item))
        return downloads

    @classmethod
    def summarize_events(cls, state: dict[str, Any] | None, events: list[dict[str, Any]]) -> dict[str, Any]:
        nodes: dict[str, dict[str, Any]] = {}
        messages = []
        downloads = []
        workflow = {}
        errors = []
        timeline = []
        last_event_seq = None
        last_event_type = None

        for stored_event in events:
            event = stored_event.get("event", {}) if isinstance(stored_event, dict) else {}
            event_type = event.get("event")
            data = event.get("data") or {}
            seq = stored_event.get("seq") if isinstance(stored_event, dict) else None
            last_event_seq = seq
            last_event_type = event_type
            if event_type:
                timeline.append(
                    {
                        "seq": seq,
                        "event_type": event_type,
                        "component_id": data.get("component_id"),
                        "component_name": data.get("component_name"),
                        "component_type": data.get("component_type"),
                        "status": (
                            "failed"
                            if event_type in {"node_failed", "workflow_failed"}
                            else "canceled"
                            if event_type == "workflow_canceled"
                            else "succeeded"
                            if event_type in {"node_finished", "workflow_finished", "message_end"}
                            else "running"
                            if event_type in {"node_started", "node_progress", "workflow_started"}
                            else None
                        ),
                        "stored_at": stored_event.get("stored_at") if isinstance(stored_event, dict) else None,
                        "created_at": data.get("created_at"),
                        "message": data.get("message"),
                        "error": data.get("error"),
                    }
                )

            if event_type == "node_started":
                component_id = data.get("component_id")
                if not component_id:
                    continue
                nodes.setdefault(component_id, {})
                nodes[component_id].update(
                    {
                        "component_id": component_id,
                        "component_name": data.get("component_name"),
                        "component_type": data.get("component_type"),
                        "status": "running",
                        "started_at": data.get("created_at"),
                        "thoughts": data.get("thoughts"),
                        "start_seq": seq,
                    }
                )
            elif event_type == "node_finished":
                component_id = data.get("component_id")
                if not component_id:
                    continue
                node = nodes.setdefault(component_id, {"component_id": component_id})
                error = data.get("error")
                node.update(
                    {
                        "component_name": data.get("component_name"),
                        "component_type": data.get("component_type"),
                        "status": "failed" if error else "succeeded",
                        "error": error,
                        "elapsed_time": data.get("elapsed_time"),
                        "created_at": data.get("created_at"),
                        "finished_at": data.get("created_at"),
                        "inputs": cls._summarize_value(data.get("inputs")),
                        "outputs": cls._summarize_value(data.get("outputs")),
                        "finish_seq": seq,
                    }
                )
                if error:
                    errors.append(
                        {
                            "component_id": component_id,
                            "component_name": data.get("component_name"),
                            "error": error,
                        }
                    )
                downloads.extend(cls._extract_downloads(data.get("outputs")))
            elif event_type == "node_failed":
                component_id = data.get("component_id")
                if not component_id:
                    continue
                node = nodes.setdefault(component_id, {"component_id": component_id})
                node.update(
                    {
                        "component_name": data.get("component_name"),
                        "component_type": data.get("component_type"),
                        "status": "failed",
                        "error": data.get("error"),
                        "elapsed_time": data.get("elapsed_time"),
                        "created_at": data.get("created_at"),
                        "finished_at": data.get("created_at"),
                        "inputs": cls._summarize_value(data.get("inputs")),
                        "outputs": cls._summarize_value(data.get("outputs")),
                        "finish_seq": seq,
                    }
                )
                if data.get("error"):
                    errors.append(
                        {
                            "component_id": component_id,
                            "component_name": data.get("component_name"),
                            "error": data.get("error"),
                        }
                    )
                downloads.extend(cls._extract_downloads(data.get("outputs")))
            elif event_type == "node_progress":
                component_id = data.get("component_id")
                if not component_id:
                    continue
                node = nodes.setdefault(component_id, {"component_id": component_id})
                node.update(
                    {
                        "component_name": data.get("component_name") or node.get("component_name"),
                        "component_type": data.get("component_type") or node.get("component_type"),
                        "status": "running",
                        "progress": data.get("progress"),
                        "message": data.get("message"),
                        "progress_seq": seq,
                    }
                )
            elif event_type == "node_output":
                component_id = data.get("component_id")
                if not component_id:
                    continue
                node = nodes.setdefault(component_id, {"component_id": component_id})
                node["latest_output"] = cls._summarize_value(data.get("output"))
                node["output_seq"] = seq
                downloads.extend(cls._extract_downloads(data.get("output")))
            elif event_type == "message":
                content = str(data.get("content") or "")
                if content:
                    messages.append({"seq": seq, "length": len(content), "preview": content[:200]})
            elif event_type == "workflow_started":
                workflow.update(
                    {
                        "status": "running",
                        "created_at": data.get("created_at"),
                        "inputs": cls._summarize_value(data.get("inputs")),
                    }
                )
            elif event_type == "message_end":
                downloads.extend(cls._extract_downloads(data.get("downloads")))
                downloads.extend(cls._extract_downloads(data.get("attachment")))
            elif event_type == "workflow_finished":
                workflow = {
                    **workflow,
                    "status": "succeeded",
                    "elapsed_time": data.get("elapsed_time"),
                    "created_at": data.get("created_at"),
                    "outputs": cls._summarize_value(data.get("outputs")),
                }
                downloads.extend(cls._extract_downloads(data.get("outputs")))
            elif event_type == "workflow_failed":
                workflow.update(
                    {
                        "status": "failed",
                        "created_at": data.get("created_at"),
                        "error": data.get("error"),
                    }
                )
                errors.append({"component_id": None, "component_name": "workflow", "error": data.get("error")})
            elif event_type == "workflow_canceled":
                workflow.update(
                    {
                        "status": "canceled",
                        "created_at": data.get("created_at"),
                        "error": data.get("error"),
                    }
                )

        dedup_downloads = []
        seen_downloads = set()
        for item in downloads:
            doc_id = item.get("doc_id")
            if not doc_id or doc_id in seen_downloads:
                continue
            seen_downloads.add(doc_id)
            dedup_downloads.append(item)

        dedup_errors = []
        seen_errors = set()
        for item in errors:
            key = (item.get("component_id"), item.get("component_name"), item.get("error"))
            if key in seen_errors:
                continue
            seen_errors.add(key)
            dedup_errors.append(item)

        node_values = list(nodes.values())
        running_nodes = [node for node in node_values if node.get("status") == "running"]
        succeeded_nodes = [node for node in node_values if node.get("status") == "succeeded"]
        failed_nodes = [node for node in node_values if node.get("status") == "failed"]

        workflow_status = workflow.get("status")
        total_nodes = len(node_values)
        terminal_workflow = workflow_status in {"succeeded", "failed", "canceled"}
        completed_nodes = len(succeeded_nodes) + len(failed_nodes)
        if terminal_workflow and total_nodes == 0:
            progress_percent = 1.0
        elif terminal_workflow and not failed_nodes:
            progress_percent = 1.0
        elif total_nodes > 0:
            progress_percent = max(0.0, min(1.0, completed_nodes / total_nodes))
        else:
            progress_percent = 0.0

        state = state or {}
        duration = None
        try:
            started_at = state.get("created_at")
            finished_at = state.get("finished_at") or state.get("updated_at")
            if started_at and finished_at:
                duration = max(0.0, float(finished_at) - float(started_at))
        except Exception:
            duration = None

        return {
            "state": state,
            "event_count": len(events),
            "nodes": node_values,
            "timeline": timeline,
            "duration": duration,
            "progress": {
                "percent": progress_percent,
                "total_nodes": total_nodes,
                "succeeded_nodes": len(succeeded_nodes),
                "failed_nodes": len(failed_nodes),
                "running_nodes": len(running_nodes),
                "current_nodes": [
                    {
                        "component_id": node.get("component_id"),
                        "component_name": node.get("component_name"),
                        "component_type": node.get("component_type"),
                        "thoughts": node.get("thoughts"),
                    }
                    for node in running_nodes
                ],
                "last_event_seq": last_event_seq,
                "last_event_type": last_event_type,
            },
            "messages": messages,
            "downloads": dedup_downloads,
            "workflow": workflow,
            "errors": dedup_errors,
        }

    @classmethod
    def get_trace(cls, tenant_id: str, run_id: str) -> dict[str, Any] | None:
        state = cls.get_state(tenant_id, run_id)
        if not state:
            return None
        events = cls.get_events(tenant_id, run_id, -1)
        return cls.summarize_events(state, events)

    @classmethod
    def get_artifacts(cls, tenant_id: str, run_id: str) -> list[dict[str, Any]] | None:
        trace = cls.get_trace(tenant_id, run_id)
        if not trace:
            return None
        return trace.get("downloads", [])

    @classmethod
    def append_event(cls, tenant_id: str, run_id: str, event: dict[str, Any]) -> None:
        try:
            events = cls._load_json(cls._events_key(tenant_id, run_id), [])
            if not isinstance(events, list):
                events = []
            seq = int(events[-1].get("seq", -1)) + 1 if events else 0
            event_record = {
                "seq": seq,
                "stored_at": time.time(),
                "event": event,
            }
            events.append(event_record)
            if len(events) > cls.MAX_EVENTS:
                events = events[-cls.MAX_EVENTS :]
            REDIS_CONN.set_obj(cls._events_key(tenant_id, run_id), events, cls.TTL_SECONDS)

            state = cls.get_state(tenant_id, run_id) or {}
            trace = cls.summarize_events(state, events)
            state["updated_at"] = time.time()
            state["event_count"] = len(events)
            state["progress"] = trace.get("progress", {})
            state["downloads"] = trace.get("downloads", [])
            REDIS_CONN.set_obj(cls._state_key(tenant_id, run_id), state, cls.TTL_SECONDS)
        except Exception:
            logging.exception("AgentRunService.append_event failed. run_id=%s", run_id)

    @classmethod
    def finish(cls, tenant_id: str, run_id: str, status: str = AgentRunStatus.SUCCEEDED, error: str = "") -> None:
        try:
            state = cls.get_state(tenant_id, run_id) or {}
            now = time.time()
            if status == AgentRunStatus.SUCCEEDED and state.get("status") == AgentRunStatus.CANCEL_REQUESTED:
                status = AgentRunStatus.CANCELED
            state["status"] = status
            state["updated_at"] = now
            state["finished_at"] = now
            state["error"] = error or ""
            if status in {AgentRunStatus.SUCCEEDED, AgentRunStatus.CANCELED}:
                progress = state.get("progress") if isinstance(state.get("progress"), dict) else {}
                progress["percent"] = 1.0
                progress["running_nodes"] = 0
                progress["current_nodes"] = []
                state["progress"] = progress
            REDIS_CONN.set_obj(cls._state_key(tenant_id, run_id), state, cls.TTL_SECONDS)
            if state.get("agent_id"):
                REDIS_CONN.srem(cls._active_runs_key(tenant_id, state["agent_id"]), run_id)
        except Exception:
            logging.exception("AgentRunService.finish failed. run_id=%s", run_id)

    @classmethod
    def fail(cls, tenant_id: str, run_id: str, error: str) -> None:
        cls.finish(tenant_id, run_id, AgentRunStatus.FAILED, error)

    @classmethod
    def request_cancel(cls, tenant_id: str, run_id: str) -> bool:
        state = cls.get_state(tenant_id, run_id)
        if not state:
            return False
        try:
            task_id = state.get("task_id")
            if task_id:
                REDIS_CONN.set(f"{task_id}-cancel", "x", cls.TTL_SECONDS)
            state["status"] = AgentRunStatus.CANCEL_REQUESTED
            state["updated_at"] = time.time()
            REDIS_CONN.set_obj(cls._state_key(tenant_id, run_id), state, cls.TTL_SECONDS)
            return True
        except Exception:
            logging.exception("AgentRunService.request_cancel failed. run_id=%s", run_id)
            return False
