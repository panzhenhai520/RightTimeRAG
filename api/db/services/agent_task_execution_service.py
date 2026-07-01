#
#  Copyright 2026 The InfiniFlow Authors. All Rights Reserved.
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

from api.db.services.agent_goal_intent_service import AgentGoalIntentService
from api.db.services.agent_task_context_service import RelevantFileResolver, TaskContextCollector
from api.db.services.agent_task_model_service import AgentTaskError, AgentTaskModelService, AgentTaskStatus
from api.db.services.agent_task_precondition_service import PreconditionChecker
from api.db.services.agent_task_stack_service import AgentTaskStackService
from api.db.services.agent_task_state_service import AgentTaskStateService
from api.db.services.document_compare_report_service import DocumentCompareReportService
from api.db.services.document_compare_service import DocumentCompareService
from api.db.services.document_normalize_service import DocumentNormalizeService
from api.db.services.workspace_file_service import WorkspaceFileService


SUPPORTED_EXECUTION_TASK_TYPES = {
    "find_file",
    "read_file",
    "read_document",
    "normalize_document",
    "extract_outline",
    "analyze_document_structure",
    "classify_content",
    "compare_documents",
    "compose_report",
    "generate_report",
}


class AgentTaskExecutionService:
    @classmethod
    def enter_child_task(
        cls,
        *,
        child_task_id: str,
        parent_frame_id: str = "",
        return_to_task_id: str = "",
        continuation_pointer: str = "",
        local_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        frame = AgentTaskStackService.push(
            task_id=child_task_id,
            parent_frame_id=parent_frame_id,
            return_to_task_id=return_to_task_id,
            continuation_pointer=continuation_pointer,
            local_context=local_context or {},
        )
        AgentTaskModelService.record_audit(
            goal_id=frame["goal_id"],
            task_id=child_task_id,
            action="task_enter_child",
            after={"frame_id": frame["frame_id"], "parent_frame_id": parent_frame_id},
        )
        return frame

    @classmethod
    def execute_leaf_task(
        cls,
        task_id: str,
        *,
        frame_id: str = "",
        parent_frame_id: str = "",
        continuation_pointer: str = "",
        runtime_context: dict[str, Any] | None = None,
        root: str = "",
        roots: list[str | Path] | None = None,
        max_retry: int = 1,
    ) -> dict[str, Any]:
        task = AgentTaskModelService.get_task(task_id)
        if AgentTaskModelService.list_children(task_id):
            return cls.block_task(task_id, frame_id=frame_id, reason="non_leaf_task", details={"child_count": len(AgentTaskModelService.list_children(task_id))})
        frame = AgentTaskStackService.get_frame(frame_id) if frame_id else AgentTaskStackService.push(
            task_id=task_id,
            parent_frame_id=parent_frame_id,
            continuation_pointer=continuation_pointer,
        )
        runtime = cls.merge_runtime_context(runtime_context or {}, frame.get("local_context", {}))
        preconditions = PreconditionChecker.check_model_task(task_id, runtime_context=runtime, root=root, roots=roots, mark_ready=True)
        if not preconditions["ok"]:
            cls.apply_wait_status(task_id, preconditions["next_status"])
            AgentTaskStackService.update_frame(frame["frame_id"], status="blocked", checkpoint={"preconditions": preconditions})
            return {
                "ok": False,
                "task_id": task_id,
                "frame_id": frame["frame_id"],
                "status": preconditions["next_status"],
                "preconditions": preconditions,
                "repair_tasks": preconditions["repair_tasks"],
            }
        try:
            cls.mark_running(task_id)
            result = cls.dispatch(task, runtime_context=runtime, root=root, roots=roots)
            cls.complete_task(task_id, result=result)
            returned = AgentTaskStackService.return_from_frame(frame["frame_id"], return_value=result)
            cls.sync_parent_local_context(returned.get("parent_frame"))
            return {
                "ok": True,
                "task_id": task_id,
                "frame_id": frame["frame_id"],
                "status": AgentTaskStatus.COMPLETED.value,
                "result": result,
                "parent_frame": returned.get("parent_frame"),
            }
        except Exception as exc:
            return cls.handle_failure(task_id, frame_id=frame["frame_id"], exc=exc, max_retry=max_retry)

    @classmethod
    def dispatch(
        cls,
        task: dict[str, Any],
        *,
        runtime_context: dict[str, Any] | None = None,
        root: str = "",
        roots: list[str | Path] | None = None,
    ) -> dict[str, Any]:
        runtime = runtime_context or {}
        inputs = cls.merge_runtime_context(task.get("inputs") if isinstance(task.get("inputs"), dict) else {}, runtime)
        task_type = str(task.get("task_type") or "").strip()
        if task_type not in SUPPORTED_EXECUTION_TASK_TYPES:
            raise AgentTaskError("UNSUPPORTED_TASK_TYPE", "Task type is not allowed for execution.", {"task_type": task_type})
        if task_type == "find_file":
            return cls.execute_find_file(inputs, root=root, roots=roots)
        if task_type == "read_file":
            return cls.execute_read_file(inputs, root=root, roots=roots)
        if task_type in {"read_document", "normalize_document"}:
            return cls.execute_normalize_document(inputs, root=root, roots=roots)
        if task_type in {"extract_outline", "analyze_document_structure"}:
            return cls.execute_extract_outline(inputs, root=root, roots=roots)
        if task_type == "classify_content":
            return cls.execute_classify_content(inputs)
        if task_type == "compare_documents":
            return cls.execute_compare_documents(inputs, root=root, roots=roots)
        if task_type in {"compose_report", "generate_report"}:
            return cls.execute_compose_report(inputs)
        raise AgentTaskError("UNSUPPORTED_TASK_TYPE", "Task type is not allowed for execution.", {"task_type": task_type})

    @classmethod
    def execute_find_file(cls, inputs: dict[str, Any], *, root: str = "", roots: list[str | Path] | None = None) -> dict[str, Any]:
        goal_intent = inputs.get("goal_intent")
        if not isinstance(goal_intent, dict):
            goal_intent = AgentGoalIntentService.classify(str(inputs.get("query") or inputs.get("raw_request") or inputs.get("primary_object") or ""))
        resolved = RelevantFileResolver.resolve(
            goal_intent=goal_intent,
            root=root or str(inputs.get("root") or ""),
            path=str(inputs.get("path_scope") or inputs.get("search_path") or "."),
            roots=roots,
            query=str(inputs.get("query") or ""),
            extensions=inputs.get("extensions") or [],
            max_candidates=int(inputs.get("max_candidates") or 8),
        )
        selected = resolved["candidate_files"][0]["file"] if resolved.get("candidate_files") else {}
        return {"candidate_files": resolved["candidate_files"], "selected_file": selected, "query_terms": resolved["query_terms"]}

    @classmethod
    def execute_read_file(cls, inputs: dict[str, Any], *, root: str = "", roots: list[str | Path] | None = None) -> dict[str, Any]:
        path = cls.path_from_inputs(inputs)
        if not path:
            raise AgentTaskError("MISSING_FILE_PATH", "read_file requires a path or selected_file input.")
        return WorkspaceFileService.read_file(path=str(path), root=root or str(inputs.get("root") or ""), roots=roots)

    @classmethod
    def execute_normalize_document(cls, inputs: dict[str, Any], *, root: str = "", roots: list[str | Path] | None = None) -> dict[str, Any]:
        path = cls.path_from_inputs(inputs)
        if not path:
            raise AgentTaskError("MISSING_FILE_PATH", "normalize_document requires a path or selected_file input.")
        document = DocumentNormalizeService.normalize(
            path=str(path),
            root=root or str(inputs.get("root") or ""),
            roots=roots,
            max_bytes=inputs.get("max_bytes"),
            chunk_chars=inputs.get("chunk_chars"),
        )
        return {"document": document, "lines": document.get("lines", []), "sections": document.get("sections", []), "chunks": document.get("chunks", [])}

    @classmethod
    def execute_extract_outline(cls, inputs: dict[str, Any], *, root: str = "", roots: list[str | Path] | None = None) -> dict[str, Any]:
        document = inputs.get("document")
        if not isinstance(document, dict):
            document = cls.execute_normalize_document(inputs, root=root, roots=roots)["document"]
        outline = TaskContextCollector.outline_from_document(document)
        return {"outline": outline, "sections": outline.get("sections", []), "metadata": outline.get("metadata", {})}

    @classmethod
    def execute_classify_content(cls, inputs: dict[str, Any]) -> dict[str, Any]:
        text = str(inputs.get("content") or inputs.get("new_content") or inputs.get("raw_request") or "")
        categories = []
        category_terms = {
            "background": ("背景", "现状", "问题"),
            "goal": ("目标", "能力", "实现"),
            "development_task": ("开发", "新增", "实现", "接口"),
            "test_task": ("测试", "用例", "验收"),
            "risk": ("风险", "安全", "权限"),
            "report": ("报告", "审计", "输出"),
        }
        for category, terms in category_terms.items():
            matched = [term for term in terms if term.lower() in text.lower()]
            if matched:
                categories.append({"category": category, "confidence": 0.72, "matched_terms": matched})
        if not categories:
            categories.append({"category": "uncategorized", "confidence": 0.4, "matched_terms": []})
        return {"content_categories": categories, "source_text": text}

    @classmethod
    def execute_compare_documents(cls, inputs: dict[str, Any], *, root: str = "", roots: list[str | Path] | None = None) -> dict[str, Any]:
        left = inputs.get("left_document")
        right = inputs.get("right_document")
        if not isinstance(left, dict) and inputs.get("left_path"):
            left = DocumentNormalizeService.normalize(path=str(inputs.get("left_path")), root=root, roots=roots)
        if not isinstance(right, dict) and inputs.get("right_path"):
            right = DocumentNormalizeService.normalize(path=str(inputs.get("right_path")), root=root, roots=roots)
        if not isinstance(left, dict) or not isinstance(right, dict):
            raise AgentTaskError("MISSING_DOCUMENT_PAIR", "compare_documents requires left and right documents.")
        diff = DocumentCompareService.diff_paragraphs(left, right)
        return {"diff": diff, "summary": diff.get("summary", {})}

    @classmethod
    def execute_compose_report(cls, inputs: dict[str, Any]) -> dict[str, Any]:
        title = str(inputs.get("title") or "Task execution report")
        if any(key in inputs for key in ("diff", "matches", "conflicts", "documents")):
            report = DocumentCompareReportService.build_report(
                title=title,
                files=inputs.get("files"),
                documents=inputs.get("documents"),
                diff=inputs.get("diff"),
                table_diff=inputs.get("table_diff"),
                matches=inputs.get("matches"),
                conflicts=inputs.get("conflicts"),
                missing_requirements=inputs.get("missing_requirements"),
                risk_points=inputs.get("risk_points"),
                audit=inputs.get("audit"),
                run_id=str(inputs.get("run_id") or ""),
                agent_id=str(inputs.get("agent_id") or ""),
            )
            return {"report": report, "markdown": DocumentCompareReportService.render_markdown(report)}
        sections = inputs.get("sections") if isinstance(inputs.get("sections"), list) else []
        markdown_lines = [f"# {title}", ""]
        for section in sections:
            if isinstance(section, dict):
                markdown_lines.extend([f"## {section.get('title', 'Section')}", "", str(section.get("content") or ""), ""])
        if not sections:
            markdown_lines.append(str(inputs.get("content") or inputs.get("summary") or ""))
        return {"report": {"title": title, "sections": sections, "summary": inputs.get("summary", "")}, "markdown": "\n".join(markdown_lines).strip() + "\n"}

    @classmethod
    def pause_frame(cls, frame_id: str, *, reason: str = "") -> dict[str, Any]:
        return AgentTaskStackService.pause(frame_id, reason=reason)

    @classmethod
    def resume_frame(cls, frame_id: str) -> dict[str, Any]:
        return AgentTaskStackService.resume(frame_id)

    @classmethod
    def continue_from_frame(cls, frame_id: str) -> dict[str, Any]:
        frame = AgentTaskStackService.get_frame(frame_id)
        return {
            "frame_id": frame_id,
            "task_id": frame["task_id"],
            "continuation_pointer": frame.get("continuation_pointer", ""),
            "local_context": frame.get("local_context", {}),
            "status": frame.get("status", ""),
        }

    @classmethod
    def retry_task(cls, task_id: str, *, max_retry: int = 1, reason: str = "") -> dict[str, Any]:
        task = AgentTaskModelService.get_task(task_id)
        metadata = deepcopy(task.get("metadata") or {})
        execution = metadata.setdefault("execution", {})
        retry_count = int(execution.get("retry_count") or 0)
        if retry_count > int(max_retry or 0):
            cls.apply_wait_status(task_id, AgentTaskStatus.BLOCKED.value, reason=reason or "retry budget exceeded")
            return {"task_id": task_id, "retry_allowed": False, "retry_count": retry_count, "status": AgentTaskStatus.BLOCKED.value}
        cls.apply_wait_status(task_id, AgentTaskStatus.READY.value, reason=reason or "retry requested")
        return {"task_id": task_id, "retry_allowed": True, "retry_count": retry_count, "status": AgentTaskStatus.READY.value}

    @classmethod
    def handle_failure(cls, task_id: str, *, frame_id: str, exc: Exception, max_retry: int) -> dict[str, Any]:
        task = AgentTaskModelService.get_task(task_id)
        metadata = deepcopy(task.get("metadata") or {})
        execution = metadata.setdefault("execution", {})
        retry_count = int(execution.get("retry_count") or 0) + 1
        execution["retry_count"] = retry_count
        execution["last_error"] = str(exc)
        execution["last_error_type"] = exc.__class__.__name__
        AgentTaskModelService.update_task(task_id, metadata=metadata)
        checkpoint = {"error": str(exc), "error_type": exc.__class__.__name__, "retry_count": retry_count}
        AgentTaskStackService.update_frame(frame_id, status="blocked" if retry_count > int(max_retry or 0) else "failed", checkpoint=checkpoint)
        if retry_count > int(max_retry or 0):
            cls.apply_wait_status(task_id, AgentTaskStatus.BLOCKED.value, reason=str(exc))
            status = AgentTaskStatus.BLOCKED.value
        else:
            cls.apply_wait_status(task_id, AgentTaskStatus.FAILED.value, reason=str(exc))
            status = AgentTaskStatus.FAILED.value
        return {"ok": False, "task_id": task_id, "frame_id": frame_id, "status": status, "retry_count": retry_count, "error": str(exc)}

    @classmethod
    def complete_task(cls, task_id: str, *, result: dict[str, Any]) -> None:
        task = AgentTaskModelService.get_task(task_id)
        metadata = deepcopy(task.get("metadata") or {})
        metadata.setdefault("execution", {})["completed_at"] = AgentTaskModelService.now()
        AgentTaskModelService.update_task(task_id, outputs=result, metadata=metadata)
        cls.apply_wait_status(task_id, AgentTaskStatus.VERIFIED.value, reason="execution completed")
        cls.apply_wait_status(task_id, AgentTaskStatus.COMPLETED.value, reason="execution completed")

    @classmethod
    def mark_running(cls, task_id: str) -> None:
        task = AgentTaskModelService.get_task(task_id)
        if task["status"] == AgentTaskStatus.PENDING.value:
            AgentTaskStateService.mark_ready(task_id, reason="execution starting")
        task = AgentTaskModelService.get_task(task_id)
        if task["status"] == AgentTaskStatus.READY.value:
            AgentTaskStateService.mark_running(task_id, reason="execution starting")

    @classmethod
    def block_task(cls, task_id: str, *, frame_id: str = "", reason: str, details: dict[str, Any] | None = None) -> dict[str, Any]:
        cls.apply_wait_status(task_id, AgentTaskStatus.BLOCKED.value, reason=reason)
        if frame_id:
            AgentTaskStackService.update_frame(frame_id, status="blocked", checkpoint={"reason": reason, "details": details or {}})
        return {"ok": False, "task_id": task_id, "frame_id": frame_id, "status": AgentTaskStatus.BLOCKED.value, "reason": reason, "details": details or {}}

    @staticmethod
    def apply_wait_status(task_id: str, status: str, *, reason: str = "") -> None:
        task = AgentTaskModelService.get_task(task_id)
        if task["status"] == status:
            return
        try:
            AgentTaskStateService.transition(task_id, status, reason=reason)
        except AgentTaskError:
            if status == AgentTaskStatus.BLOCKED.value and task["status"] == AgentTaskStatus.RUNNING.value:
                AgentTaskStateService.mark_blocked(task_id, reason=reason)
            else:
                raise

    @staticmethod
    def sync_parent_local_context(parent_frame: dict[str, Any] | None) -> None:
        if not parent_frame:
            return
        try:
            parent_task = AgentTaskModelService.get_task(parent_frame["task_id"])
        except AgentTaskError:
            return
        metadata = deepcopy(parent_task.get("metadata") or {})
        metadata["local_context"] = deepcopy(parent_frame.get("local_context", {}))
        AgentTaskModelService.update_task(parent_frame["task_id"], metadata=metadata)

    @staticmethod
    def merge_runtime_context(first: dict[str, Any], second: dict[str, Any]) -> dict[str, Any]:
        merged = deepcopy(first)
        for key, value in second.items():
            merged.setdefault(key, deepcopy(value))
        return merged

    @staticmethod
    def path_from_inputs(inputs: dict[str, Any]) -> str:
        for key in ("path", "file_path", "source_path"):
            if inputs.get(key):
                return str(inputs[key])
        for key in ("selected_file", "file"):
            value = inputs.get(key)
            if isinstance(value, dict):
                return str(value.get("path") or value.get("relative_path") or "")
            if value:
                return str(value)
        return ""
