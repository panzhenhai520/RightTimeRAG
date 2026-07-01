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

from __future__ import annotations

import json
import re
from typing import Any


class AgentPublicResponseService:
    """Build the stable external Agent response shape.

    Internal Agent traces can contain node inputs, node outputs, prompt
    fragments, and hidden reasoning. This adapter exposes only fields that are
    intended for external systems.
    """

    TERMINAL_STATUSES = {"succeeded", "failed", "canceled", "timeout"}
    HIDDEN_THINK_PATTERN = re.compile(r"<think\b[^>]*>.*?</think>", re.IGNORECASE | re.DOTALL)
    SENSITIVE_KEYWORDS = ("api_key", "apikey", "authorization", "cookie", "password", "secret", "token")
    STRUCTURED_KEYS = {
        "answer",
        "intention",
        "target",
        "reply_to",
        "confidence",
        "knowledge_used",
        "suggested_next_action",
    }
    SENSITIVE_ASSIGNMENT_PATTERN = re.compile(
        r"(?i)\b(api[_-]?key|authorization|cookie|password|secret|token)\b\s*[:=]\s*([^\s,;]+)"
    )

    @classmethod
    def strip_hidden_thoughts(cls, value: Any) -> str:
        text = "" if value is None else str(value)
        text = cls.HIDDEN_THINK_PATTERN.sub("", text)
        text = re.sub(r"</?think\b[^>]*>", "", text, flags=re.IGNORECASE)
        return text.strip()

    @classmethod
    def redact_sensitive_text(cls, value: Any) -> str:
        text = cls.strip_hidden_thoughts(value)
        return cls.SENSITIVE_ASSIGNMENT_PATTERN.sub(r"\1=***", text)

    @classmethod
    def normalize_error(
        cls,
        code: str | None = None,
        message: Any = "",
        *,
        retryable: bool = False,
        detail: Any = None,
    ) -> dict[str, Any] | None:
        if not code and not message and detail is None:
            return None
        error = {
            "code": code or "AGENT_ERROR",
            "message": cls.redact_sensitive_text(message) or "Agent execution failed.",
            "retryable": bool(retryable),
        }
        if detail is not None:
            error["detail"] = cls._safe_scalar(detail, max_chars=800)
        return error

    @classmethod
    def normalize_downloads(cls, value: Any) -> list[dict[str, Any]]:
        items = cls._as_list(value)
        normalized: list[dict[str, Any]] = []
        seen: set[str] = set()
        for item in items:
            if not isinstance(item, dict):
                continue
            doc_id = cls._safe_scalar(item.get("doc_id") or item.get("id") or item.get("artifact_id"))
            artifact_id = cls._safe_scalar(item.get("artifact_id") or doc_id)
            filename = cls._safe_scalar(item.get("filename") or item.get("file_name") or item.get("name"))
            key = doc_id or artifact_id or filename
            if not key or key in seen:
                continue
            seen.add(key)
            out = {
                "artifact_id": artifact_id,
                "doc_id": doc_id,
                "filename": filename,
                "mime_type": cls._safe_scalar(item.get("mime_type") or item.get("content_type")),
                "size": item.get("size") if isinstance(item.get("size"), (int, float)) else None,
                "download_url": cls._safe_scalar(item.get("download_url") or item.get("url")),
            }
            normalized.append({k: v for k, v in out.items() if v not in (None, "")})
        return normalized

    @classmethod
    def normalize_references(cls, value: Any) -> list[dict[str, Any]]:
        references: list[dict[str, Any]] = []
        for chunk in cls._iter_reference_chunks(value):
            if not isinstance(chunk, dict):
                continue
            content = chunk.get("content_with_weight", chunk.get("content"))
            out = {
                "id": cls._safe_scalar(chunk.get("chunk_id") or chunk.get("id")),
                "chunk_id": cls._safe_scalar(chunk.get("chunk_id") or chunk.get("id")),
                "document_id": cls._safe_scalar(chunk.get("doc_id") or chunk.get("document_id")),
                "document_name": cls._safe_scalar(chunk.get("docnm_kwd") or chunk.get("document_name")),
                "dataset_id": cls._safe_scalar(chunk.get("kb_id") or chunk.get("dataset_id")),
                "page": cls._safe_scalar(chunk.get("page") or chunk.get("page_num") or chunk.get("page_number")),
                "positions": cls._safe_positions(chunk.get("positions") or chunk.get("position_int")),
                "image_id": cls._safe_scalar(chunk.get("image_id") or chunk.get("img_id")),
                "standard_type": cls._safe_scalar(chunk.get("standard_type")),
                "jurisdiction": cls._safe_scalar(chunk.get("jurisdiction")),
                "industry": cls._safe_scalar(chunk.get("industry")),
                "effective_from": cls._safe_scalar(chunk.get("effective_from")),
                "effective_to": cls._safe_scalar(chunk.get("effective_to")),
                "version": cls._safe_scalar(chunk.get("version")),
                "article_no": cls._safe_scalar(chunk.get("article_no")),
                "topic": cls._safe_scalar(chunk.get("topic")),
                "metadata_incomplete": chunk.get("metadata_incomplete") if isinstance(chunk.get("metadata_incomplete"), bool) else None,
                "content": cls._safe_scalar(cls.strip_hidden_thoughts(content), max_chars=1200),
            }
            references.append({k: v for k, v in out.items() if v not in (None, "", [])})
        return references

    @classmethod
    def sanitize_trace_summary(cls, trace: Any) -> dict[str, Any]:
        if not isinstance(trace, dict):
            return {}
        state = trace.get("state") if isinstance(trace.get("state"), dict) else {}
        metadata = state.get("metadata") if isinstance(state.get("metadata"), dict) else {}
        workflow = trace.get("workflow") if isinstance(trace.get("workflow"), dict) else {}
        progress = trace.get("progress") if isinstance(trace.get("progress"), dict) else {}
        safe_nodes = []
        for node in trace.get("nodes") or []:
            if not isinstance(node, dict):
                continue
            safe_nodes.append(
                {
                    k: v
                    for k, v in {
                        "component_id": cls._safe_scalar(node.get("component_id")),
                        "component_name": cls._safe_scalar(node.get("component_name")),
                        "component_type": cls._safe_scalar(node.get("component_type")),
                        "status": cls._safe_scalar(node.get("status")),
                        "elapsed_time": node.get("elapsed_time") if isinstance(node.get("elapsed_time"), (int, float)) else None,
                        "error": cls._safe_scalar(node.get("error"), max_chars=800),
                    }.items()
                    if v not in (None, "")
                }
            )

        safe_errors = []
        for item in trace.get("errors") or []:
            if not isinstance(item, dict):
                continue
            safe_errors.append(
                {
                    k: v
                    for k, v in {
                        "component_id": cls._safe_scalar(item.get("component_id")),
                        "component_name": cls._safe_scalar(item.get("component_name")),
                        "error": cls._safe_scalar(item.get("error"), max_chars=800),
                    }.items()
                    if v not in (None, "")
                }
            )

        return {
            "status": cls._safe_scalar(state.get("status") or workflow.get("status")),
            "workflow_id": cls._safe_scalar(metadata.get("workflow_id") or workflow.get("workflow_id")),
            "workflow_version": cls._safe_scalar(metadata.get("workflow_version") or workflow.get("workflow_version")),
            "context_hash": cls._safe_scalar(workflow.get("context_hash")),
            "constraint_hash": cls._safe_scalar(workflow.get("constraint_hash")),
            "context_missing": cls._safe_scalar(workflow.get("context_missing")),
            "context_issues": cls._safe_scalar(workflow.get("context_issues")),
            "event_count": trace.get("event_count") if isinstance(trace.get("event_count"), int) else None,
            "duration": trace.get("duration") if isinstance(trace.get("duration"), (int, float)) else None,
            "progress": cls._sanitize_progress(progress),
            "workflow": {
                k: v
                for k, v in {
                    "workflow_id": cls._safe_scalar(metadata.get("workflow_id") or workflow.get("workflow_id")),
                    "workflow_version": cls._safe_scalar(metadata.get("workflow_version") or workflow.get("workflow_version")),
                    "context_hash": cls._safe_scalar(workflow.get("context_hash")),
                    "constraint_hash": cls._safe_scalar(workflow.get("constraint_hash")),
                    "status": cls._safe_scalar(workflow.get("status")),
                    "elapsed_time": workflow.get("elapsed_time") if isinstance(workflow.get("elapsed_time"), (int, float)) else None,
                    "error": cls._safe_scalar(workflow.get("error"), max_chars=800),
                }.items()
                if v not in (None, "")
            },
            "nodes": safe_nodes,
            "downloads": cls.normalize_downloads(trace.get("downloads")),
            "errors": safe_errors,
        }

    @classmethod
    def normalize_structured_output(cls, value: Any) -> dict[str, Any]:
        candidates: list[dict[str, Any]] = []

        def visit(item: Any):
            if isinstance(item, str):
                try:
                    visit(json.loads(item))
                except Exception:
                    return
                return
            if isinstance(item, dict):
                if any(key in item for key in cls.STRUCTURED_KEYS):
                    candidates.append(item)
                for child in item.values():
                    if isinstance(child, (dict, list, str)):
                        visit(child)
            elif isinstance(item, list):
                for child in item:
                    visit(child)

        visit(value)
        if not candidates:
            return {}
        selected = candidates[-1]
        confidence = selected.get("confidence")
        try:
            confidence = max(0.0, min(1.0, float(confidence)))
        except Exception:
            confidence = None
        return {
            "answer": cls.strip_hidden_thoughts(selected.get("answer")) if selected.get("answer") is not None else "",
            "intention": cls._safe_scalar(selected.get("intention")),
            "target": cls._safe_scalar(selected.get("target")),
            "reply_to": cls._safe_scalar(selected.get("reply_to")),
            "confidence": confidence,
            "knowledge_used": cls._safe_json_list(selected.get("knowledge_used"), max_items=20),
            "suggested_next_action": cls._safe_scalar(selected.get("suggested_next_action"), max_chars=400),
        }

    @classmethod
    def build_response(
        cls,
        *,
        agent_id: str = "",
        workflow_id: str = "",
        run_id: str = "",
        session_id: str = "",
        message_id: str = "",
        status: str | None = None,
        answer: Any = "",
        references: Any = None,
        downloads: Any = None,
        trace: Any = None,
        structured: Any = None,
        latency_ms: int | float | None = None,
        error: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        trace_summary = cls.sanitize_trace_summary(trace)
        structured_fields = cls.normalize_structured_output(structured)
        final_status = status or trace_summary.get("status") or ("failed" if error else "succeeded")
        safe_downloads = cls.normalize_downloads(downloads)
        for item in trace_summary.get("downloads") or []:
            safe_downloads.extend(cls.normalize_downloads([item]))
        safe_downloads = cls.normalize_downloads(safe_downloads)
        if latency_ms is None and isinstance(trace_summary.get("duration"), (int, float)):
            latency_ms = round(float(trace_summary["duration"]) * 1000, 3)
        safe_answer = structured_fields.get("answer") or cls.strip_hidden_thoughts(answer)
        return {
            "agent_id": agent_id or "",
            "workflow_id": workflow_id or agent_id or "",
            "run_id": run_id or "",
            "session_id": session_id or "",
            "message_id": message_id or "",
            "status": final_status,
            "answer": safe_answer,
            "intention": structured_fields.get("intention") or "",
            "target": structured_fields.get("target") or "",
            "reply_to": structured_fields.get("reply_to") or "",
            "confidence": structured_fields.get("confidence"),
            "knowledge_used": structured_fields.get("knowledge_used") or [],
            "suggested_next_action": structured_fields.get("suggested_next_action") or "",
            "references": cls.normalize_references(references),
            "downloads": safe_downloads,
            "trace_summary": trace_summary,
            "error_code": (error or {}).get("code", "") if isinstance(error, dict) else "",
            "error": error,
            "latency_ms": latency_ms if isinstance(latency_ms, (int, float)) else None,
        }

    @classmethod
    def from_final_answer(
        cls,
        *,
        agent_id: str = "",
        workflow_id: str = "",
        run_id: str = "",
        session_id: str = "",
        message_id: str = "",
        final_answer: Any = None,
        trace: Any = None,
        status: str | None = None,
        error: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        data = final_answer.get("data") if isinstance(final_answer, dict) else {}
        data = data if isinstance(data, dict) else {"content": data}
        event = final_answer.get("event") if isinstance(final_answer, dict) else ""
        if error is None and event == "workflow_failed":
            error = cls.normalize_error("WORKFLOW_FAILED", data.get("error") or "Workflow failed.")
        answer = data.get("content", "")
        if not answer and isinstance(final_answer, dict) and final_answer.get("error"):
            error = error or cls.normalize_error("AGENT_ERROR", final_answer.get("error"))
        return cls.build_response(
            agent_id=agent_id,
            workflow_id=workflow_id,
            run_id=run_id or (final_answer.get("run_id") if isinstance(final_answer, dict) else ""),
            session_id=session_id or (final_answer.get("session_id") if isinstance(final_answer, dict) else ""),
            message_id=message_id or (final_answer.get("message_id") if isinstance(final_answer, dict) else ""),
            status=status or ("failed" if error else None),
            answer=answer,
            references=data.get("reference") or data.get("references"),
            downloads=data.get("downloads") or data.get("attachment") or data.get("download"),
            trace=trace,
            structured=data.get("structured") or data.get("structured_output") or data.get("json"),
            error=error,
        )

    @classmethod
    def _sanitize_progress(cls, progress: dict[str, Any]) -> dict[str, Any]:
        safe_current = []
        for item in progress.get("current_nodes") or []:
            if not isinstance(item, dict):
                continue
            safe_current.append(
                {
                    k: v
                    for k, v in {
                        "component_id": cls._safe_scalar(item.get("component_id")),
                        "component_name": cls._safe_scalar(item.get("component_name")),
                        "component_type": cls._safe_scalar(item.get("component_type")),
                    }.items()
                    if v not in (None, "")
                }
            )
        return {
            k: v
            for k, v in {
                "percent": progress.get("percent") if isinstance(progress.get("percent"), (int, float)) else None,
                "total_nodes": progress.get("total_nodes") if isinstance(progress.get("total_nodes"), int) else None,
                "succeeded_nodes": progress.get("succeeded_nodes") if isinstance(progress.get("succeeded_nodes"), int) else None,
                "failed_nodes": progress.get("failed_nodes") if isinstance(progress.get("failed_nodes"), int) else None,
                "running_nodes": progress.get("running_nodes") if isinstance(progress.get("running_nodes"), int) else None,
                "current_nodes": safe_current,
                "last_event_seq": progress.get("last_event_seq") if isinstance(progress.get("last_event_seq"), int) else None,
                "last_event_type": cls._safe_scalar(progress.get("last_event_type")),
            }.items()
            if v not in (None, "", [])
        }

    @classmethod
    def _iter_reference_chunks(cls, value: Any):
        if value is None:
            return
        if isinstance(value, dict):
            if isinstance(value.get("chunks"), list):
                for item in value["chunks"]:
                    yield item
            if isinstance(value.get("reference"), list):
                for item in value["reference"]:
                    yield item
            for key, item in value.items():
                if key in {"chunks", "reference", "doc_aggs"}:
                    continue
                if isinstance(item, dict):
                    yield from cls._iter_reference_chunks(item)
                elif isinstance(item, list):
                    for sub_item in item:
                        yield from cls._iter_reference_chunks(sub_item)
        elif isinstance(value, list):
            for item in value:
                yield from cls._iter_reference_chunks(item)

    @classmethod
    def _safe_scalar(cls, value: Any, max_chars: int = 300) -> Any:
        if value is None:
            return None
        if isinstance(value, (int, float, bool)):
            return value
        if isinstance(value, (list, tuple, set)):
            return [cls._safe_scalar(item, max_chars=max_chars) for item in list(value)[:20]]
        if isinstance(value, dict):
            return {
                str(k): ("***" if cls._is_sensitive_key(str(k)) else cls._safe_scalar(v, max_chars=max_chars))
                for k, v in list(value.items())[:20]
            }
        text = cls.redact_sensitive_text(value)
        if len(text) > max_chars:
            return text[:max_chars] + "..."
        return text

    @classmethod
    def _safe_positions(cls, value: Any) -> list[Any]:
        if not isinstance(value, list):
            return []
        return [cls._safe_scalar(item, max_chars=120) for item in value[:20]]

    @classmethod
    def _as_list(cls, value: Any) -> list[Any]:
        if value is None:
            return []
        if isinstance(value, list):
            return value
        if isinstance(value, dict):
            return [value]
        return []

    @classmethod
    def _safe_json_list(cls, value: Any, max_items: int = 20) -> list[Any]:
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except Exception:
                return []
        if isinstance(value, dict):
            value = [value]
        if not isinstance(value, list):
            return []
        return [cls._safe_json_item(item) for item in value[:max_items]]

    @classmethod
    def _safe_json_item(cls, item: Any) -> Any:
        if isinstance(item, dict):
            return {
                str(key): cls._safe_json_item(value)
                for key, value in list(item.items())[:20]
                if not cls._is_sensitive_key(str(key))
            }
        if isinstance(item, list):
            return [cls._safe_json_item(value) for value in item[:20]]
        if isinstance(item, str):
            return cls._safe_scalar(item)
        if isinstance(item, (int, float, bool)) or item is None:
            return item
        return cls._safe_scalar(item)

    @classmethod
    def _is_sensitive_key(cls, key: str) -> bool:
        normalized = key.lower().replace("-", "_")
        return any(part in normalized for part in cls.SENSITIVE_KEYWORDS)
