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

import asyncio
import base64
import copy
import hashlib
import hmac
import inspect
import ipaddress
import json
import logging
import os
import time
from functools import partial, wraps
from typing import Any, Set

from api.utils.web_utils import CONTENT_TYPE_MAP, apply_safe_file_response_headers
from agent.component.file_parser import FileParser
from agent.component.schema import list_operator_manifests
import jwt
from quart import Response, jsonify, request, make_response

from agent.artifact_registry_service import AgentArtifactRegistryService, ArtifactPermissionError
from api.apps import current_user, login_required
from api.apps.services.canvas_replica_service import CanvasReplicaService
from api.db import CanvasCategory
from api.db.db_models import Task
from api.db.services.api_service import API4ConversationService
from api.db.services.agent_meeting_memory_service import AgentMeetingMemoryService
from api.db.services.agent_meeting_scheduler_service import AgentMeetingSchedulerService
from api.db.services.agent_document_write_coordinator_service import (
    AgentDocumentWriteCoordinatorService,
    DocumentWriteCoordinatorError,
)
from api.db.services.agent_public_response_service import AgentPublicResponseService
from api.db.services.agent_run_queue_service import AgentRunQueueService
from api.db.services.agent_run_service import AgentRunService, AgentRunStatus
from api.db.services.agent_teacher_registry_service import AgentTeacherRegistryService
from api.db.services.agent_turn_context_service import AgentTurnContextService
from api.db.services.agent_validation_service import AgentValidationService
from api.db.services.workspace_file_service import WorkspaceFileService
from api.db.services.canvas_service import (
    CanvasTemplateService,
    UserCanvasService,
    completion as agent_completion,
    completion_openai,
)
from api.db.services.document_service import DocumentService
from api.db.services.file_service import FileService
from api.db.services.knowledgebase_service import KnowledgebaseService
from api.db.services.pipeline_operation_log_service import PipelineOperationLogService
from api.db.services.task_service import CANVAS_DEBUG_DOC_ID, TaskService, queue_dataflow
from api.db.services.user_service import TenantService, UserService
from api.db.services.user_canvas_version import UserCanvasVersionService
from api.utils.api_utils import (
    add_tenant_id_to_kwargs,
    get_data_error_result,
    get_json_result,
    get_result,
    get_request_json,
    server_error_response,
    validate_request,
)
from common import settings
from common.ssrf_guard import assert_host_is_safe
from common.constants import RetCode
from common.exceptions import TaskCanceledException
from common.misc_utils import get_uuid, thread_pool_exec
from peewee import MySQLDatabase, PostgresqlDatabase

# Keeps strong references to fire-and-forget tasks so they are not GC'd before completion.
_background_tasks: Set[asyncio.Task] = set()


def _request_bool(value, default=False):
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "y", "on"}:
            return True
        if normalized in {"false", "0", "no", "n", "off", ""}:
            return False
    return bool(value)


def _request_deadline_ms(value) -> int | None:
    if value in (None, ""):
        return None
    try:
        deadline_ms = int(float(value))
    except Exception:
        raise ValueError("`deadline_ms` must be a positive integer.")
    if deadline_ms <= 0:
        raise ValueError("`deadline_ms` must be a positive integer.")
    return deadline_ms


def _agent_run_queue_enabled(req: dict | None = None) -> bool:
    """Return whether recoverable Agent runs should go through the queue."""
    if req and "queue" in req:
        return _request_bool(req.get("queue"), False)
    return _request_bool(os.environ.get("AGENT_RUN_QUEUE_ENABLED"), False)


def _is_agent_run_canceled(exc: Exception) -> bool:
    return isinstance(exc, TaskCanceledException) or "has been canceled" in str(exc).lower()


def _require_canvas_access_sync(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        if not UserCanvasService.accessible(kwargs.get('agent_id'), kwargs.get('tenant_id')):
            return get_json_result(data=False, message="Make sure you have permission to access the agent.", code=RetCode.OPERATING_ERROR)
        return func(*args, **kwargs)
    return wrapper


def _require_canvas_access_async(func):
    @wraps(func)
    async def wrapper(*args, **kwargs):
        agent_id = kwargs.get('agent_id')
        tenant_id = kwargs.get('tenant_id')
        if not await thread_pool_exec(UserCanvasService.accessible, agent_id, tenant_id):
            return get_json_result(data=False, message="Make sure you have permission to access the agent.", code=RetCode.OPERATING_ERROR)
        return await func(*args, **kwargs)
    return wrapper


def _require_canvas_owner_sync(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        if not UserCanvasService.query(user_id=kwargs.get('tenant_id'), id=kwargs.get('agent_id')):
            return get_json_result(data=False, message="Only the owner of the agent is authorized for this operation.", code=RetCode.OPERATING_ERROR)
        return func(*args, **kwargs)
    return wrapper


def _get_user_nickname(user_id: str) -> str:
    exists, user = UserService.get_by_id(user_id)
    if not exists:
        return user_id
    return str(getattr(user, "nickname", "") or user_id)


def _build_sse_response(body):
    resp = Response(body, mimetype="text/event-stream")
    resp.headers.add_header("Cache-control", "no-cache")
    resp.headers.add_header("Connection", "keep-alive")
    resp.headers.add_header("X-Accel-Buffering", "no")
    resp.headers.add_header("Content-Type", "text/event-stream; charset=utf-8")
    return resp


def _normalize_agent_reference_entry(reference):
    if not isinstance(reference, dict):
        return {"chunks": [], "doc_aggs": []}
    if "chunks" in reference or "doc_aggs" in reference:
        return {
            "chunks": reference.get("chunks", []),
            "doc_aggs": reference.get("doc_aggs", []),
        }
    return {
        "chunks": reference.get("reference", reference.get("chunks", [])) or [],
        "doc_aggs": reference.get("doc_aggs", []) or [],
    }


def _normalize_agent_session(conv):
    conv["message"] = conv.get("message", [])
    for info in conv["message"]:
        if "prompt" in info:
            info.pop("prompt")
    conv["agent_id"] = conv.pop("dialog_id")
    if isinstance(conv["reference"], dict):
        if "chunks" in conv["reference"]:
            conv["reference"] = [conv["reference"]]
        else:
            conv["reference"] = [value for _, value in sorted(conv["reference"].items(), key=lambda item: int(item[0]))]
    elif isinstance(conv["reference"], list):
        conv["reference"] = [_normalize_agent_reference_entry(reference) for reference in conv["reference"]]
    else:
        conv["reference"] = []

    if conv["reference"]:
        messages = [message for i, message in enumerate(conv["message"]) if i != 0 and message["role"] != "user"]
        for message, reference in zip(messages, conv["reference"]):
            chunks = reference.get("chunks", [])
            message["reference"] = [
                {
                    "id": chunk.get("chunk_id", chunk.get("id")),
                    "content": chunk.get("content_with_weight", chunk.get("content")),
                    "document_id": chunk.get("doc_id", chunk.get("document_id")),
                    "document_name": chunk.get("docnm_kwd", chunk.get("document_name")),
                    "dataset_id": chunk.get("kb_id", chunk.get("dataset_id")),
                    "image_id": chunk.get("image_id", chunk.get("img_id")),
                    "positions": chunk.get("positions", chunk.get("position_int")),
                }
                for chunk in chunks
            ]
    del conv["reference"]
    return conv


def _agent_session_list_result(data, total):
    return jsonify({"code": RetCode.SUCCESS, "message": "success", "data": data, "total": total})


def _normalize_public_dataset_ids(req: dict[str, Any]) -> list[str]:
    raw = req.get("request_dataset_ids")
    if raw is None:
        raw = req.get("dataset_ids")
    if raw is None:
        raw = req.get("kb_ids")
    if raw in (None, ""):
        return []
    if isinstance(raw, str):
        values = [raw]
    elif isinstance(raw, list):
        values = raw
    else:
        raise ValueError("`dataset_ids` must be a string array.")
    dataset_ids = []
    seen = set()
    for item in values:
        dataset_id = str(item or "").strip()
        if not dataset_id or dataset_id in seen:
            continue
        seen.add(dataset_id)
        dataset_ids.append(dataset_id)
    return dataset_ids


def _as_canvas_dict(canvas_obj) -> dict[str, Any]:
    if isinstance(canvas_obj, dict):
        return canvas_obj
    if hasattr(canvas_obj, "to_dict"):
        return canvas_obj.to_dict()
    result = {}
    for key in ("id", "user_id", "title", "canvas_category"):
        if hasattr(canvas_obj, key):
            result[key] = getattr(canvas_obj, key)
    return result


def _loads_dsl_dict(dsl: Any) -> dict[str, Any]:
    if isinstance(dsl, dict):
        return dsl
    if isinstance(dsl, str):
        try:
            parsed = json.loads(dsl)
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}
    return {}


def _collect_workflow_binding_ids(value: Any) -> set[str]:
    """Collect explicit workflow binding ids from an Agent DSL.

    The platform does not yet have a dedicated binding table. This supports a
    few stable metadata keys so bindings can be declared without a migration.
    """
    binding_keys = {
        "workflow_id",
        "workflow_ids",
        "bound_workflow_id",
        "bound_workflow_ids",
        "allowed_workflow_id",
        "allowed_workflow_ids",
        "workflow_bindings",
        "bound_workflows",
    }
    found: set[str] = set()

    def visit(item: Any, key: str = "") -> None:
        if isinstance(item, dict):
            for child_key, child_value in item.items():
                normalized_key = str(child_key or "").lower()
                if normalized_key in binding_keys:
                    visit(child_value, normalized_key)
                elif normalized_key in {"metadata", "agent_metadata", "settings", "config"}:
                    visit(child_value, normalized_key)
        elif isinstance(item, list):
            for child in item:
                visit(child, key)
        elif key in binding_keys and item not in (None, ""):
            found.add(str(item).strip())

    visit(value)
    return {item for item in found if item}


def _workflow_binding_allowed(agent_cvs: Any, agent_dsl: Any, workflow_id: str, workflow_cvs: Any) -> bool:
    agent_info = _as_canvas_dict(agent_cvs)
    workflow_info = _as_canvas_dict(workflow_cvs)
    if str(agent_info.get("id") or "") == str(workflow_id):
        return True
    explicit_bindings = _collect_workflow_binding_ids(_loads_dsl_dict(agent_dsl))
    if str(workflow_id) in explicit_bindings:
        return True
    # Until a dedicated binding table exists, same-owner canvases are treated as
    # an implicit binding after access checks pass. Team-shared cross-owner
    # workflows still require an explicit DSL binding.
    return bool(agent_info.get("user_id") and agent_info.get("user_id") == workflow_info.get("user_id"))


async def _resolve_agent_workflow(agent_id: str, req: dict[str, Any], tenant_id: str, release_mode: bool):
    workflow_id = str(req.get("workflow_id") or agent_id)
    agent_cvs, agent_dsl = await thread_pool_exec(
        UserCanvasService.get_agent_dsl_with_release,
        agent_id,
        release_mode,
        tenant_id,
    )
    if workflow_id == agent_id:
        return {
            "agent_cvs": agent_cvs,
            "workflow_cvs": agent_cvs,
            "agent_dsl": agent_dsl,
            "workflow_dsl": agent_dsl,
            "workflow_id": workflow_id,
            "explicit_workflow": False,
        }

    if not await thread_pool_exec(UserCanvasService.accessible, workflow_id, tenant_id):
        raise PermissionError("Make sure you have permission to access the workflow.")

    workflow_cvs, workflow_dsl = await thread_pool_exec(
        UserCanvasService.get_agent_dsl_with_release,
        workflow_id,
        release_mode,
        tenant_id,
    )
    if not _workflow_binding_allowed(agent_cvs, agent_dsl, workflow_id, workflow_cvs):
        raise PermissionError("Workflow is not bound to the requested agent.")

    return {
        "agent_cvs": agent_cvs,
        "workflow_cvs": workflow_cvs,
        "agent_dsl": agent_dsl,
        "workflow_dsl": workflow_dsl,
        "workflow_id": workflow_id,
        "explicit_workflow": True,
    }


def _agent_run_public_status(state: dict[str, Any] | None) -> str:
    if not isinstance(state, dict):
        return "failed"
    status = str(state.get("status") or "").lower()
    if status in {"queued", "running", "succeeded", "failed", "canceled", "timeout"}:
        return status
    return status or "running"


def _extract_public_session_answer(conv: dict[str, Any], message_id: str | None = None) -> dict[str, Any]:
    messages = conv.get("message") or []
    if not isinstance(messages, list):
        return {"answer": "", "references": []}
    references = conv.get("reference") or []
    if isinstance(references, dict):
        if "chunks" in references:
            references = [references]
        else:
            references = [value for _, value in sorted(references.items(), key=lambda item: int(item[0]))]
    if not isinstance(references, list):
        references = []
    references = [_normalize_agent_reference_entry(reference) for reference in references]

    assistant_messages = [
        message
        for index, message in enumerate(messages)
        if isinstance(message, dict) and index != 0 and message.get("role") != "user"
    ]
    selected_index = None
    selected_message = None
    if message_id:
        for index, message in enumerate(assistant_messages):
            if str(message.get("id") or "") == str(message_id):
                selected_index = index
                selected_message = message
                break
    if selected_message is None and assistant_messages:
        selected_index = len(assistant_messages) - 1
        selected_message = assistant_messages[-1]
    if selected_message is None:
        return {"answer": "", "references": []}
    return {
        "answer": selected_message.get("content", ""),
        "references": references[selected_index] if selected_index is not None and selected_index < len(references) else [],
        "message_id": selected_message.get("id") or message_id or "",
    }


def _release_validation_error(dsl):
    validation = AgentValidationService.validate_for_publish(dsl)
    if validation["ok"]:
        return None
    return get_json_result(
        data=validation,
        message="Agent publish validation failed.",
        code=RetCode.ARGUMENT_ERROR,
    )


def _ensure_default_agent_workspace(dsl: dict, agent_id: str, tenant_id: str = "", title: str = "") -> None:
    if not isinstance(dsl, dict) or not str(agent_id or "").strip():
        return
    workspace = dsl.get("workspace")
    if isinstance(workspace, dict) and workspace.get("managed"):
        return
    dsl["workspace"] = WorkspaceFileService.ensure_agent_workspace(
        str(agent_id),
        tenant_id=str(tenant_id or ""),
        title=str(title or ""),
    )


def _ensure_agent_workspace_file(agent_id: str, relative_path: str, content: str = "") -> None:
    workspace = WorkspaceFileService.ensure_agent_workspace(str(agent_id))
    root_path = workspace.get("root_path")
    if not root_path:
        return
    target = os.path.join(root_path, relative_path)
    os.makedirs(os.path.dirname(target), exist_ok=True)
    if not os.path.exists(target):
        with open(target, "w", encoding="utf-8") as file:
            file.write(content)


CASE_DOCUMENT_REVIEW_AGENT_ID = "6f6145de757a11f1b4075dddb426bed0"
CASE_DOCUMENT_REVIEW_AGENT_TITLE = "\u6587\u6863\u6838\u5bf9\u6848\u4f8b\u667a\u80fd\u4f53"
CASE_DOCUMENT_REVIEW_AGENT_LEGACY_TITLE = (
    "\u590d\u6742\u4efb\u52a1\u8d44\u6599\u6574\u7406\u4e0e"
    "\u6587\u6863\u6838\u5bf9\u6848\u4f8b\u667a\u80fd\u4f53"
)
CASE_DOCUMENT_REVIEW_LLM_ID = "deepseek-v4-flash___OpenAI-API@OpenAI-API-Compatible"
CASE_DOCUMENT_REVIEW_OUTPUT_PATH = "output/document-review-report.md"
CASE_DOCUMENT_REVIEW_NOTES = [
    {
        "id": "Note:CaseInputGuide",
        "name": "1. 输入说明",
        "text": "用户只需要提供任务说明、文件 A、文件 B 和可选输出格式。文件路径可以在运行页点浏览选择；工作区和报告输出空间由智能体配置负责。",
        "x": 40,
        "y": 40,
    },
    {
        "id": "Note:CasePlanningGuide",
        "name": "2. 任务理解与规划",
        "text": "GoalIntentClassifier 先识别目标类型；TaskContextCollector 搜集工作区上下文；TaskPlanner 拆解子任务；PreconditionChecker 检查路径、文件和执行条件。",
        "x": 620,
        "y": -80,
    },
    {
        "id": "Note:CaseFileGuide",
        "name": "3. 文件读取与结构化",
        "text": "DocumentNormalizer 分别读取两个文件并规范化为统一文档对象；ClauseExtractor 把段落、条款或要点抽出来，供后续精确比对和冲突判断使用。",
        "x": 40,
        "y": 450,
    },
    {
        "id": "Note:CaseCompareGuide",
        "name": "4. 差异、包含与冲突",
        "text": "DocumentDiff 做逐段差异；DocumentSemanticComparer 做语义匹配；DocumentConflictDetector 判断缺失要求、包含关系和可能冲突条款。",
        "x": 1040,
        "y": 760,
    },
    {
        "id": "Note:CaseLlmGuide",
        "name": "5. 大模型综合分析",
        "text": "Agent:Synthesis 已接入本机大模型 deepseek-v4-flash。它读取任务规划、文件差异、语义匹配、冲突结果和基础报告，输出结构化分析正文 content。",
        "x": 1740,
        "y": 80,
    },
    {
        "id": "Note:CaseOutputGuide",
        "name": "6. 报告、文件和审计",
        "text": "DocGenerator 把大模型正文生成可下载报告；TaskExecutionReportComposer 输出审计摘要；Message 节点把正文、审计摘要和下载链接统一返回给用户。",
        "x": 2140,
        "y": 80,
    },
    {
        "id": "Note:CaseWriteGuide",
        "name": "7. 输出空间与受控改写",
        "text": "普通报告自动写入智能体专用输出空间 output/document-review-report.md；只有修改用户原文件或应用 patch 时才需要 ManualApprove/HumanReview 审批。",
        "x": 1820,
        "y": 900,
    },
]


def _normalize_case_agent_title(agent_id: str, req: dict):
    """Keep the bundled training case name stable while old editors auto-save."""
    if agent_id == CASE_DOCUMENT_REVIEW_AGENT_ID and req.get("title") == CASE_DOCUMENT_REVIEW_AGENT_LEGACY_TITLE:
        req["title"] = CASE_DOCUMENT_REVIEW_AGENT_TITLE


def _case_note_node(note: dict):
    return {
        "data": {
            "form": {"text": note["text"]},
            "label": "Note",
            "name": note["name"],
        },
        "dragHandle": ".note-drag-handle",
        "height": 170,
        "id": note["id"],
        "measured": {"height": 170, "width": 360},
        "position": {"x": note["x"], "y": note["y"]},
        "selected": False,
        "sourcePosition": "right",
        "targetPosition": "left",
        "type": "noteNode",
        "width": 360,
    }


def _append_unique(items: list, value: str) -> None:
    if value not in items:
        items.append(value)


def _ensure_case_component_link(components: dict, source_id: str, target_id: str) -> None:
    source = components.get(source_id)
    target = components.get(target_id)
    if not isinstance(source, dict) or not isinstance(target, dict):
        return
    source_downstream = source.setdefault("downstream", [])
    target_upstream = target.setdefault("upstream", [])
    if isinstance(source_downstream, list):
        _append_unique(source_downstream, target_id)
    if isinstance(target_upstream, list):
        _append_unique(target_upstream, source_id)


def _ensure_case_graph_edge(graph: dict, edge_id: str, source_id: str, target_id: str) -> None:
    edges = graph.setdefault("edges", [])
    if not isinstance(edges, list):
        graph["edges"] = edges = []
    if any(edge.get("source") == source_id and edge.get("target") == target_id for edge in edges if isinstance(edge, dict)):
        return
    edges.append(
        {
            "data": {"isHovered": False},
            "id": edge_id,
            "source": source_id,
            "sourceHandle": "start",
            "target": target_id,
            "targetHandle": "end",
        }
    )


def _remove_case_optional_write_nodes(components: dict, graph: dict) -> None:
    optional_ids = {"ManualApprove:WriteGate", "WorkspacePatchApply:DryRun"}
    for optional_id in optional_ids:
        components.pop(optional_id, None)

    for component in components.values():
        if not isinstance(component, dict):
            continue
        for key in ("upstream", "downstream"):
            if isinstance(component.get(key), list):
                component[key] = [item for item in component[key] if item not in optional_ids]

    nodes = graph.get("nodes")
    if isinstance(nodes, list):
        graph["nodes"] = [node for node in nodes if node.get("id") not in optional_ids]
    edges = graph.get("edges")
    if isinstance(edges, list):
        graph["edges"] = [
            edge
            for edge in edges
            if edge.get("source") not in optional_ids and edge.get("target") not in optional_ids
        ]


def _replace_case_begin_refs(value: Any) -> Any:
    if isinstance(value, str):
        return value.replace("{begin@workspace_root}", "").replace(
            "{begin@write_target_path}",
            CASE_DOCUMENT_REVIEW_OUTPUT_PATH,
        )
    if isinstance(value, list):
        return [_replace_case_begin_refs(item) for item in value]
    if isinstance(value, dict):
        return {key: _replace_case_begin_refs(item) for key, item in value.items()}
    return value


def _normalize_case_agent_dsl(agent_id: str, req: dict):
    if agent_id != CASE_DOCUMENT_REVIEW_AGENT_ID or not isinstance(req.get("dsl"), dict):
        return

    dsl = req["dsl"]
    _ensure_default_agent_workspace(dsl, agent_id, title=req.get("title") or CASE_DOCUMENT_REVIEW_AGENT_TITLE)
    _ensure_agent_workspace_file(
        agent_id,
        CASE_DOCUMENT_REVIEW_OUTPUT_PATH,
        "# 文档核对案例智能体输出\n",
    )
    components = dsl.setdefault("components", {})
    graph = dsl.setdefault("graph", {})
    nodes = graph.setdefault("nodes", [])
    _remove_case_optional_write_nodes(components, graph)
    nodes = graph.setdefault("nodes", [])

    begin_params = {
        "enablePrologue": True,
        "inputs": {
            "task_request": {"name": "任务说明", "type": "paragraph", "optional": False, "options": []},
            "file_a_path": {"name": "文件 A", "type": "line", "optional": False, "options": []},
            "file_b_path": {"name": "文件 B", "type": "line", "optional": False, "options": []},
            "output_formats": {"name": "输出格式", "type": "line", "optional": True, "options": []},
        },
        "mode": "conversational",
        "prologue": (
            "请输入任务说明，并通过浏览按钮选择文件 A 和文件 B。"
            "智能体会读取文件、抽取结构、比对差异、调用大模型综合分析，并生成报告。"
        ),
    }
    begin_component = components.get("begin")
    if isinstance(begin_component, dict):
        begin_component.setdefault("obj", {})["component_name"] = "Begin"
        begin_component["obj"]["params"] = begin_params

    agent_params = {
        "cite": True,
        "delay_after_error": 1,
        "description": "复杂任务资料整理、文件比对和报告生成案例智能体",
        "frequency_penalty": 0.3,
        "llm_id": CASE_DOCUMENT_REVIEW_LLM_ID,
        "max_retries": 3,
        "max_rounds": 4,
        "max_tokens": 4096,
        "mcp": [],
        "message_history_window_size": 10,
        "outputs": {"content": {"type": "string", "value": ""}},
        "presence_penalty": 0.2,
        "prompts": [
            {
                "role": "user",
                "content": (
                    "用户任务：{begin@task_request}\n\n"
                    "工作区：系统配置的智能体工作区\n"
                    "文件 A：{begin@file_a_path}\n"
                    "文件 B：{begin@file_b_path}\n\n"
                    "任务意图：{GoalIntentClassifier:Intent@goal_intent}\n\n"
                    "候选上下文：{TaskContextCollector:Context@context_bundle}\n\n"
                    "任务规划：{TaskPlanner:Plan@task_plan}\n\n"
                    "前置条件检查：{PreconditionChecker:Check@precondition_result}\n\n"
                    "文件 A 条款：{ClauseExtractor:A@clauses}\n\n"
                    "文件 B 条款：{ClauseExtractor:B@clauses}\n\n"
                    "文件差异：{DocumentDiff:Text@diff}\n\n"
                    "语义匹配：{DocumentSemanticComparer:Compare@matches}\n\n"
                    "冲突和缺失：{DocumentConflictDetector:Conflict@conflicts}\n\n"
                    "基础比对报告：{DocumentCompareReportComposer:CompareReport@markdown}\n\n"
                    "请输出：\n"
                    "1. 任务理解和执行路径。\n"
                    "2. 文件读取、结构抽取和比对过程摘要。\n"
                    "3. 差异、包含、缺失和冲突清单。\n"
                    "4. 风险等级表格。\n"
                    "5. 最终报告摘要。\n"
                    "6. 普通报告会自动写入智能体输出空间；如果需要改用户原文件，只给出 dry-run 和人工审批建议。"
                ),
            }
        ],
        "sys_prompt": (
            "你是复杂任务资料整理与文档核对智能体。你必须基于上游节点输出进行综合分析，"
            "先解释任务目标，再按文件读取、结构抽取、差异比对、冲突判断、报告输出和受控写回建议组织答案。"
            "普通报告可以进入智能体输出空间；涉及修改用户原文件时，只提出 dry-run 和人工审批建议。"
        ),
        "temperature": 0.15,
        "tools": [],
        "top_p": 0.35,
    }

    agent_component = components.get("Agent:Synthesis")
    if isinstance(agent_component, dict):
        agent_component.setdefault("obj", {})["component_name"] = "Agent"
        agent_component["obj"]["params"] = agent_params

    write_params = {
        "root": "",
        "path": CASE_DOCUMENT_REVIEW_OUTPUT_PATH,
        "content": "\n\n---\n\n{Agent:Synthesis@content}",
        "mode": "append",
        "encoding": "utf-8",
        "expected_hash": "",
        "dry_run": False,
        "require_approval": False,
        "approval_id": "",
        "approved": True,
        "task_id": "",
        "max_bytes": 2097152,
        "reason": "写入文档核对案例智能体专用输出空间。",
        "outputs": {
            "write": {"type": "object", "value": {}},
            "file": {"type": "object", "value": {}},
            "diff": {"type": "string", "value": ""},
            "changed": {"type": "boolean", "value": False},
            "dry_run": {"type": "boolean", "value": False},
            "approval": {"type": "object", "value": {}},
            "audit": {"type": "object", "value": {}},
        },
    }
    write_component = components.get("WorkspaceFileWrite:WriteReport")
    if isinstance(write_component, dict):
        write_component.setdefault("obj", {})["component_name"] = "WorkspaceFileWrite"
        write_component["obj"]["params"] = write_params

    for node in nodes:
        if node.get("id") == "begin":
            data = node.setdefault("data", {})
            data["form"] = begin_params
            data["label"] = "Begin"
            data["name"] = "Begin"
        if node.get("id") == "Agent:Synthesis":
            data = node.setdefault("data", {})
            data["form"] = agent_params
            data["label"] = "Agent"
            data["name"] = "Agent:Synthesis"
            node["type"] = "agentNode"
        if node.get("id") == "WorkspaceFileWrite:WriteReport":
            data = node.setdefault("data", {})
            data["form"] = write_params
            data["label"] = "WorkspaceFileWrite"
            data["name"] = "WorkspaceFileWrite:WriteReport"

    by_id = {node.get("id"): node for node in nodes}
    for note in CASE_DOCUMENT_REVIEW_NOTES:
        next_note = _case_note_node(note)
        current = by_id.get(note["id"])
        if isinstance(current, dict):
            current.update(next_note)
        else:
            nodes.append(next_note)

    for component_id, component in components.items():
        if not isinstance(component, dict):
            continue
        obj = component.get("obj")
        if isinstance(obj, dict):
            params = obj.get("params")
            if isinstance(params, dict):
                obj["params"] = _replace_case_begin_refs(params)
    for node in nodes:
        data = node.get("data")
        if isinstance(data, dict) and isinstance(data.get("form"), dict):
            data["form"] = _replace_case_begin_refs(data["form"])

    message_component = components.get("Message:Answer")
    if isinstance(message_component, dict):
        params = message_component.setdefault("obj", {}).setdefault("params", {})
        params["content"] = [
            "{Agent:Synthesis@content}\n\n"
            "审计摘要：\n{TaskExecutionReportComposer:AuditReport@markdown}\n\n"
            "报告文档：{DocGenerator:ReportDoc@download}\n\n"
            "工作区输出：{WorkspaceFileWrite:WriteReport@file}"
        ]
        for node in nodes:
            if node.get("id") == "Message:Answer":
                data = node.setdefault("data", {})
                data["form"] = params
                data["label"] = "Message"
                data["name"] = "Message:Answer"

    _ensure_case_component_link(components, "Agent:Synthesis", "WorkspaceFileWrite:WriteReport")
    _ensure_case_component_link(components, "WorkspaceFileWrite:WriteReport", "Message:Answer")
    _ensure_case_graph_edge(graph, "e_case_report_write", "Agent:Synthesis", "WorkspaceFileWrite:WriteReport")
    _ensure_case_graph_edge(graph, "e_case_write_message", "WorkspaceFileWrite:WriteReport", "Message:Answer")


async def _run_workflow_session(
    tenant_id,
    agent_id,
    workflow_conv,
    canvas,
    query,
    files,
    inputs,
    user_id,
    session_id,
    custom_header,
    canvas_title,
    canvas_category,
    return_trace,
    stream,
    chat_template_kwargs=None,
    external_context=None,
    request_dataset_ids=None,
    run_id=None,
    workflow_id=None,
    workflow_version_title=None,
    deadline_ms=None,
    start_run_record=True,
    return_response=True,
):
    workflow_id = workflow_id or agent_id

    async def commit_runtime_replica():
        commit_ok = CanvasReplicaService.commit_after_run(
            canvas_id=workflow_id,
            tenant_id=str(tenant_id),
            runtime_user_id=user_id,
            dsl=json.loads(str(canvas)),
            canvas_category=canvas_category,
            title=canvas_title,
        )
        if not commit_ok:
            logging.error(
                "Canvas runtime replica commit failed: canvas_id=%s tenant_id=%s runtime_user_id=%s",
                workflow_id,
                tenant_id,
                user_id,
            )

    workflow_conv.setdefault("message", [])
    if isinstance(workflow_conv.get("reference"), dict):
        if "chunks" in workflow_conv["reference"]:
            workflow_conv["reference"] = [workflow_conv["reference"]]
        else:
            workflow_conv["reference"] = [
                value for _, value in sorted(workflow_conv["reference"].items(), key=lambda item: int(item[0]))
            ]
    elif not isinstance(workflow_conv.get("reference"), list):
        workflow_conv["reference"] = []
    workflow_conv["reference"] = [_normalize_agent_reference_entry(reference) for reference in workflow_conv["reference"]]

    turn_id = workflow_conv["message"][-1].get("id") if workflow_conv["message"] else get_uuid()
    full_content = ""
    reference = {}
    final_ans = {}
    trace_items = []
    structured_output = {}
    turn_context = AgentTurnContextService.normalize_request(
        inputs=inputs,
        external_context=external_context,
        query=query,
        agent_id=agent_id,
    )
    inputs = AgentTurnContextService.inject_inputs(inputs, turn_context)
    run_id = run_id or get_uuid()
    setattr(canvas, "_run_id", run_id)
    tenant_key = str(tenant_id)
    if start_run_record:
        AgentRunService.start(
            tenant_key,
            run_id,
            agent_id,
            session_id,
            turn_id,
            getattr(canvas, "task_id", ""),
            query,
            status=AgentRunStatus.RUNNING,
            mode="sse" if stream else "sync",
            metadata={"workflow_id": workflow_id, "workflow_version": workflow_version_title or "", "deadline_ms": deadline_ms},
        )
    else:
        AgentRunService.mark_running(tenant_key, run_id)
    AgentRunService.append_event(
        tenant_key,
        run_id,
        {
            "event": "workflow_started",
            "session_id": session_id,
            "run_id": run_id,
            "message_id": turn_id,
            "task_id": getattr(canvas, "task_id", ""),
            "created_at": int(time.time()),
            "data": {
                "workflow_id": workflow_id,
                "workflow_version": workflow_version_title or "",
                "deadline_ms": deadline_ms,
                "context_hash": turn_context["context_hash"],
                "constraint_hash": turn_context["constraint_hash"],
                "context_missing": turn_context["context_missing"],
                "context_issues": turn_context["issues"],
                "inputs": {
                    "query": query,
                    "files": files,
                    "inputs": inputs,
                },
                "created_at": time.time(),
            },
        },
    )
    run_kwargs = {
        "query": query,
        "files": files,
        "user_id": user_id,
        "inputs": inputs,
    }
    if chat_template_kwargs is not None:
        run_kwargs["chat_template_kwargs"] = chat_template_kwargs
    if external_context is not None:
        run_kwargs["external_context"] = external_context
    if request_dataset_ids is not None:
        run_kwargs["request_dataset_ids"] = request_dataset_ids

    def record_run_event(ans):
        ans["session_id"] = session_id
        ans["run_id"] = run_id
        AgentRunService.append_event(tenant_key, run_id, copy.deepcopy(ans))
        return ans

    async def persist_workflow_session():
        if not final_ans:
            return
        workflow_conv["message"].append(
            {
                "role": "assistant",
                "content": full_content,
                "created_at": time.time(),
                "id": turn_id,
            }
        )
        workflow_conv["reference"].append(_normalize_agent_reference_entry(reference))
        workflow_conv["dsl"] = json.loads(str(canvas))
        workflow_conv["source"] = workflow_conv.get("source") or "workflow"
        await thread_pool_exec(API4ConversationService.append_message, session_id, workflow_conv)
        await commit_runtime_replica()

    if stream:

        async def sse():
            nonlocal full_content, reference, final_ans, trace_items, structured_output
            done_sent = False
            try:
                async for ans in canvas.run(**run_kwargs):
                    ans = record_run_event(ans)
                    if ans.get("event") == "message":
                        full_content += ans.get("data", {}).get("content", "")
                    if ans.get("data", {}).get("reference", None):
                        reference.update(ans["data"]["reference"])
                    if ans.get("event") == "node_finished":
                        data = ans.get("data", {})
                        node_out = data.get("outputs", {})
                        component_id = data.get("component_id")
                        if component_id is not None and "structured" in node_out:
                            structured_output[component_id] = copy.deepcopy(node_out["structured"])
                        if return_trace:
                            trace_items.append(
                                {
                                    "component_id": data.get("component_id"),
                                    "trace": [copy.deepcopy(data)],
                                }
                            )
                    final_ans = ans
                    yield "data:" + json.dumps(ans, ensure_ascii=False) + "\n\n"

                if final_ans:
                    if "data" not in final_ans or not isinstance(final_ans["data"], dict):
                        final_ans["data"] = {}
                    final_ans["data"]["content"] = full_content
                    final_ans["data"]["reference"] = reference
                    if structured_output:
                        final_ans["data"]["structured"] = structured_output
                    if trace_items:
                        final_ans["data"]["trace"] = trace_items
                if final_ans and final_ans.get("event") == "workflow_failed":
                    AgentRunService.fail(tenant_key, run_id, final_ans.get("data", {}).get("error", "Workflow failed."))
                else:
                    await persist_workflow_session()
                    AgentRunService.finish(tenant_key, run_id)
            except Exception as exc:
                logging.exception(exc)
                canvas.cancel_task()
                canceled = _is_agent_run_canceled(exc)
                AgentRunService.append_event(
                    tenant_key,
                    run_id,
                    {
                        "event": "workflow_canceled" if canceled else "workflow_failed",
                        "session_id": session_id,
                        "run_id": run_id,
                        "message_id": turn_id,
                        "task_id": getattr(canvas, "task_id", ""),
                        "created_at": int(time.time()),
                        "data": {"error": str(exc), "created_at": time.time()},
                    },
                )
                if canceled:
                    AgentRunService.finish(tenant_key, run_id, AgentRunStatus.CANCELED, str(exc))
                else:
                    AgentRunService.fail(tenant_key, run_id, str(exc))
                yield (
                    "data:"
                    + json.dumps({"code": 500, "message": str(exc), "data": False, "run_id": run_id, "session_id": session_id}, ensure_ascii=False)
                    + "\n\n"
                )
            finally:
                if not done_sent:
                    done_sent = True
                    yield "data:[DONE]\n\n"

        return _build_sse_response(sse())

    async def run_canvas_non_stream():
        nonlocal full_content, reference, final_ans, trace_items, structured_output
        async for ans in canvas.run(**run_kwargs):
            ans = record_run_event(ans)
            if ans.get("event") == "message":
                full_content += ans.get("data", {}).get("content", "")
            if ans.get("data", {}).get("reference", None):
                reference.update(ans["data"]["reference"])
            if ans.get("event") == "node_finished":
                data = ans.get("data", {})
                node_out = data.get("outputs", {})
                component_id = data.get("component_id")
                if component_id is not None and "structured" in node_out:
                    structured_output[component_id] = copy.deepcopy(node_out["structured"])
                if return_trace:
                    trace_items.append(
                        {
                            "component_id": data.get("component_id"),
                            "trace": [copy.deepcopy(data)],
                        }
                    )
            final_ans = ans

    try:
        if deadline_ms:
            async with asyncio.timeout(float(deadline_ms) / 1000.0):
                await run_canvas_non_stream()
        else:
            await run_canvas_non_stream()
    except TimeoutError as exc:
        error_message = f"Agent run exceeded deadline_ms={deadline_ms}."
        logging.warning("Agent workflow timed out. run_id=%s deadline_ms=%s", run_id, deadline_ms)
        canvas.cancel_task()
        AgentRunService.append_event(
            tenant_key,
            run_id,
            {
                "event": "workflow_timeout",
                "session_id": session_id,
                "run_id": run_id,
                "message_id": turn_id,
                "task_id": getattr(canvas, "task_id", ""),
                "created_at": int(time.time()),
                "data": {"error": error_message, "created_at": time.time(), "deadline_ms": deadline_ms},
            },
        )
        AgentRunService.timeout(tenant_key, run_id, error_message)
        if not return_response:
            return {"error": error_message, "run_id": run_id, "session_id": session_id, "error_code": "AGENT_TIMEOUT"}
        return get_result(data=f"**ERROR**: {error_message}")
    except Exception as exc:
        logging.exception(exc)
        canvas.cancel_task()
        canceled = _is_agent_run_canceled(exc)
        AgentRunService.append_event(
            tenant_key,
            run_id,
            {
                "event": "workflow_canceled" if canceled else "workflow_failed",
                "session_id": session_id,
                "run_id": run_id,
                "message_id": turn_id,
                "task_id": getattr(canvas, "task_id", ""),
                "created_at": int(time.time()),
                "data": {"error": str(exc), "created_at": time.time()},
            },
        )
        if canceled:
            AgentRunService.finish(tenant_key, run_id, AgentRunStatus.CANCELED, str(exc))
        else:
            AgentRunService.fail(tenant_key, run_id, str(exc))
        if not return_response:
            return {"error": str(exc), "run_id": run_id, "session_id": session_id}
        return get_result(data=f"**ERROR**: {str(exc)}")

    if not final_ans:
        await commit_runtime_replica()
        AgentRunService.finish(tenant_key, run_id)
        if not return_response:
            return {}
        return get_result(data={})

    if final_ans.get("event") == "workflow_failed":
        error_message = final_ans.get("data", {}).get("error", "Workflow failed.")
        AgentRunService.fail(tenant_key, run_id, error_message)
        if not return_response:
            return final_ans
        return get_result(data=f"**ERROR**: {error_message}")

    if "data" not in final_ans or not isinstance(final_ans["data"], dict):
        final_ans["data"] = {}
    final_ans["data"]["content"] = full_content
    final_ans["data"]["reference"] = reference
    if structured_output:
        final_ans["data"]["structured"] = structured_output
    if trace_items:
        final_ans["data"]["trace"] = trace_items

    await persist_workflow_session()
    AgentRunService.finish(tenant_key, run_id)
    if not return_response:
        return final_ans
    return get_result(data=final_ans)


async def execute_queued_agent_run(payload: dict):
    """Execute one queued Agent run payload.

    The create-run API persists the user turn before enqueueing. The worker
    reloads the released/current DSL and the saved session, then delegates to
    the same workflow runner used by the in-process background mode.
    """
    AgentRunQueueService.validate_payload(payload)

    tenant_id = str(payload["tenant_id"])
    agent_id = payload["agent_id"]
    workflow_id = str(payload.get("workflow_id") or agent_id)
    session_id = payload["session_id"]
    query = payload.get("query", "")
    files = payload.get("files") or []
    inputs = payload.get("inputs") or {}
    user_id = str(payload.get("user_id") or tenant_id)
    release_mode = bool(payload.get("release", False))
    custom_header = payload.get("custom_header", "")
    return_trace = bool(payload.get("return_trace", False))
    chat_template_kwargs = payload.get("chat_template_kwargs")
    external_context = payload.get("external_context")
    request_dataset_ids = payload.get("request_dataset_ids") or []
    deadline_ms = payload.get("deadline_ms")
    run_id = payload["run_id"]

    from agent.canvas import Canvas

    workflow_ref = await _resolve_agent_workflow(
        agent_id,
        {"workflow_id": workflow_id},
        tenant_id,
        release_mode,
    )
    workflow_cvs = workflow_ref["workflow_cvs"]
    dsl = workflow_ref["workflow_dsl"]
    canvas_category = getattr(workflow_cvs, "canvas_category", CanvasCategory.Agent)
    if canvas_category == CanvasCategory.DataFlow:
        raise ValueError("Queued background runs for DataFlow canvases are not supported yet.")

    canvas = Canvas(dsl, tenant_id, canvas_id=workflow_id, custom_header=custom_header)
    exists, conv = await thread_pool_exec(API4ConversationService.get_by_id, session_id)
    if not exists:
        raise ValueError("Session not found!")
    if getattr(conv, "dialog_id", None) != agent_id:
        raise ValueError("Session does not belong to the requested agent.")

    workflow_conv = conv.to_dict()
    if not isinstance(workflow_conv.get("message"), list) or not workflow_conv["message"]:
        raise ValueError("Queued Agent run session has no user message.")

    workflow_version_title = await thread_pool_exec(
        UserCanvasVersionService.get_latest_version_title,
        workflow_cvs.id,
        release_mode=release_mode,
    )

    return await _run_workflow_session(
        tenant_id=tenant_id,
        agent_id=agent_id,
        workflow_conv=workflow_conv,
        canvas=canvas,
        query=query,
        files=files,
        inputs=inputs,
        user_id=user_id,
        session_id=session_id,
        custom_header=custom_header,
        canvas_title=getattr(workflow_cvs, "title", ""),
        canvas_category=canvas_category,
        return_trace=return_trace,
        stream=False,
        chat_template_kwargs=chat_template_kwargs,
        external_context=external_context,
        request_dataset_ids=request_dataset_ids,
        run_id=run_id,
        workflow_id=workflow_id,
        workflow_version_title=workflow_version_title,
        deadline_ms=deadline_ms,
        start_run_record=False,
        return_response=False,
    )


@manager.route("/agents/<agent_id>/sessions", methods=["GET"])  # noqa: F821
@login_required
@add_tenant_id_to_kwargs
@_require_canvas_access_sync
def list_agent_sessions(agent_id, tenant_id):
    session_id = request.args.get("id")
    user_id = request.args.get("user_id")
    page_number = int(request.args.get("page", 1))
    items_per_page = int(request.args.get("page_size", 30))
    keywords = request.args.get("keywords")
    from_date = request.args.get("from_date")
    to_date = request.args.get("to_date")
    orderby = request.args.get("orderby", "update_time")
    exp_user_id = request.args.get("exp_user_id")
    desc = request.args.get("desc") not in {"False", "false"}

    if exp_user_id:
        sessions = API4ConversationService.get_names(agent_id, exp_user_id)
        return _agent_session_list_result(sessions, len(sessions))

    include_dsl = request.args.get("dsl") not in {"False", "false"}
    total, sessions = API4ConversationService.get_list(
        agent_id,
        tenant_id,
        page_number,
        items_per_page,
        orderby,
        desc,
        session_id,
        user_id,
        include_dsl,
        keywords,
        from_date,
        to_date,
        exp_user_id=exp_user_id,
    )
    sessions = [_normalize_agent_session(session) for session in sessions]
    return _agent_session_list_result(sessions, total)


@manager.route("/agents/<agent_id>/sessions", methods=["POST"])  # noqa: F821
@login_required
@add_tenant_id_to_kwargs
@_require_canvas_access_async
async def create_agent_session(agent_id, tenant_id):
    from agent.canvas import Canvas

    req = await get_request_json()
    user_id = req.get("user_id") or request.args.get("user_id", tenant_id)
    release_mode = _request_bool(req.get("release", request.args.get("release")), False)

    try:
        cvs, dsl = UserCanvasService.get_agent_dsl_with_release(agent_id, release_mode, tenant_id)
    except LookupError:
        return get_data_error_result(message="Agent not found.")
    except PermissionError as e:
        return get_data_error_result(message=str(e))

    session_id = get_uuid()
    canvas = Canvas(dsl, tenant_id, agent_id, canvas_id=cvs.id)
    canvas.reset()

    cvs.dsl = json.loads(str(canvas))
    version_title = UserCanvasVersionService.get_latest_version_title(cvs.id, release_mode=release_mode)
    conv = {
        "id": session_id,
        "name": req.get("name", ""),
        "dialog_id": cvs.id,
        "user_id": user_id,
        "exp_user_id": user_id,
        "message": [{"role": "assistant", "content": canvas.get_prologue()}],
        "source": "agent",
        "dsl": cvs.dsl,
        "reference": [],
        "version_title": version_title,
    }
    API4ConversationService.save(**conv)
    return get_result(data=_normalize_agent_session(conv))


@manager.route("/agents/<agent_id>/sessions/<session_id>", methods=["GET"])  # noqa: F821
@login_required
@add_tenant_id_to_kwargs
@_require_canvas_access_sync
def get_agent_session(agent_id, session_id, tenant_id):
    exists, conv = API4ConversationService.get_by_id(session_id)
    if not exists:
        return get_data_error_result(message="Session not found!")
    if getattr(conv, "dialog_id", None) != agent_id:
        return get_data_error_result(message="Session does not belong to the requested agent.")
    return get_json_result(data=conv.to_dict())


@manager.route("/agents/<agent_id>/sessions/<session_id>", methods=["DELETE"])  # noqa: F821
@login_required
@add_tenant_id_to_kwargs
@_require_canvas_access_sync
def delete_agent_session_item(agent_id, session_id, tenant_id):
    exists, conv = API4ConversationService.get_by_id(session_id)
    if not exists:
        return get_data_error_result(message="Session not found!")
    if getattr(conv, "dialog_id", None) != agent_id:
        return get_data_error_result(message="Session does not belong to the requested agent.")
    return get_json_result(data=API4ConversationService.delete_by_id(session_id))


@manager.route("/agents/<agent_id>/runs", methods=["POST"])  # noqa: F821
@login_required
@add_tenant_id_to_kwargs
@_require_canvas_access_async
async def create_agent_background_run(agent_id, tenant_id):
    """Create a recoverable Agent run and execute it in a server-side task.

    This is the first background execution mode for ordinary Agent canvases. It
    intentionally does not replace the existing SSE endpoint yet; callers can
    opt in and poll `/agents/runs/<run_id>/events`.
    """
    req = await get_request_json()
    query = req.get("query", "") or req.get("question", "")
    files = req.get("files", [])
    inputs = req.get("inputs", {})
    session_id = req.get("session_id")
    runtime_user_id = req.get("user_id") or tenant_id
    user_id = str(runtime_user_id)
    release_mode = _request_bool(req.get("release", request.args.get("release")), False)
    custom_header = req.get("custom_header", "")
    return_trace = bool(req.get("return_trace", False))
    chat_template_kwargs = req.get("chat_template_kwargs")
    external_context = req.get("external_context")
    workflow_id = str(req.get("workflow_id") or agent_id)
    try:
        request_dataset_ids = _normalize_public_dataset_ids(req)
        deadline_ms = _request_deadline_ms(req.get("deadline_ms"))
    except ValueError as exc:
        return get_data_error_result(message=str(exc))

    try:
        from agent.canvas import Canvas

        workflow_ref = await _resolve_agent_workflow(
            agent_id,
            req,
            tenant_id,
            release_mode,
        )
    except LookupError:
        return get_data_error_result(message="Agent not found.")
    except PermissionError as exc:
        return get_data_error_result(message=str(exc))
    except Exception as exc:
        return server_error_response(exc)

    agent_cvs = workflow_ref["agent_cvs"]
    workflow_cvs = workflow_ref["workflow_cvs"]
    dsl = workflow_ref["workflow_dsl"]
    canvas_category = getattr(workflow_cvs, "canvas_category", CanvasCategory.Agent)
    if canvas_category == CanvasCategory.DataFlow:
        return get_data_error_result(message="Background runs for DataFlow canvases are not supported yet.")

    try:
        canvas = Canvas(dsl, str(tenant_id), canvas_id=workflow_id, custom_header=custom_header)
    except Exception as exc:
        return server_error_response(exc)

    turn_id = get_uuid()
    now = time.time()
    if session_id:
        exists, conv = await thread_pool_exec(API4ConversationService.get_by_id, session_id)
        if not exists:
            return get_data_error_result(message="Session not found!")
        if getattr(conv, "dialog_id", None) != agent_id:
            return get_data_error_result(message="Session does not belong to the requested agent.")
        workflow_conv = conv.to_dict()
        if not isinstance(workflow_conv.get("message"), list):
            workflow_conv["message"] = []
        workflow_conv["message"].append(
            {
                "role": "user",
                "content": query,
                "id": turn_id,
                "files": files,
                "created_at": now,
            }
        )
        await thread_pool_exec(API4ConversationService.update_by_id, session_id, workflow_conv)
    else:
        session_id = get_uuid()
        version_title = await thread_pool_exec(
            UserCanvasVersionService.get_latest_version_title,
            workflow_cvs.id,
            release_mode=release_mode,
        )
        workflow_conv = {
            "id": session_id,
            "dialog_id": agent_cvs.id,
            "user_id": user_id,
            "exp_user_id": user_id,
            "name": req.get("name", "") or str(query or "New Session")[:80],
            "message": [
                {
                    "role": "user",
                    "content": query,
                    "id": turn_id,
                    "files": files,
                    "created_at": now,
                }
            ],
            "reference": [],
            "source": "workflow",
            "dsl": json.loads(dsl) if isinstance(dsl, str) else dsl,
            "version_title": version_title,
        }
        await thread_pool_exec(API4ConversationService.save, **workflow_conv)

    workflow_version_title = await thread_pool_exec(
        UserCanvasVersionService.get_latest_version_title,
        workflow_cvs.id,
        release_mode=release_mode,
    )

    run_id = get_uuid()
    AgentRunService.start(
        str(tenant_id),
        run_id,
        agent_id,
        session_id,
        turn_id,
        getattr(canvas, "task_id", ""),
        query,
        status=AgentRunStatus.QUEUED,
        mode="background_queue" if _agent_run_queue_enabled(req) else "background",
        metadata={"workflow_id": workflow_id, "workflow_version": workflow_version_title or "", "deadline_ms": deadline_ms},
    )

    if _agent_run_queue_enabled(req):
        payload = AgentRunQueueService.build_payload(
            run_id=run_id,
            tenant_id=str(tenant_id),
            agent_id=agent_id,
            session_id=session_id,
            message_id=turn_id,
            query=query,
            workflow_id=workflow_id,
            files=files,
            inputs=inputs,
            user_id=user_id,
            release=release_mode,
            return_trace=return_trace,
            custom_header=custom_header,
            chat_template_kwargs=chat_template_kwargs,
            external_context=external_context,
            request_dataset_ids=request_dataset_ids,
            deadline_ms=deadline_ms,
        )
        if not AgentRunQueueService.enqueue(payload):
            AgentRunService.fail(str(tenant_id), run_id, "Failed to enqueue Agent run.")
            return get_data_error_result(message="Failed to enqueue Agent run.")
        return get_json_result(
            data={
                "run_id": run_id,
                "session_id": session_id,
                "message_id": turn_id,
                "task_id": getattr(canvas, "task_id", ""),
                "workflow_id": workflow_id,
                "status": AgentRunStatus.QUEUED,
                "queued": True,
            }
        )

    async def _background_run():
        try:
            await _run_workflow_session(
                tenant_id=tenant_id,
                agent_id=agent_id,
                workflow_conv=workflow_conv,
                canvas=canvas,
                query=query,
                files=files,
                inputs=inputs,
                user_id=user_id,
                session_id=session_id,
                custom_header=custom_header,
                canvas_title=getattr(workflow_cvs, "title", ""),
                canvas_category=canvas_category,
                return_trace=return_trace,
                stream=False,
                chat_template_kwargs=chat_template_kwargs,
                external_context=external_context,
                request_dataset_ids=request_dataset_ids,
                run_id=run_id,
                workflow_id=workflow_id,
                workflow_version_title=workflow_version_title,
                deadline_ms=deadline_ms,
                start_run_record=False,
                return_response=False,
            )
        except Exception as exc:
            logging.exception("Background agent run failed. run_id=%s", run_id)
            AgentRunService.fail(str(tenant_id), run_id, str(exc))

    task = asyncio.create_task(_background_run())
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)

    return get_json_result(
        data={
            "run_id": run_id,
            "session_id": session_id,
            "message_id": turn_id,
            "task_id": getattr(canvas, "task_id", ""),
            "workflow_id": workflow_id,
            "status": AgentRunStatus.QUEUED,
        }
    )


async def _prepare_meeting_agent_sessions(tenant_id, req, normalized_agents, meeting_id, turn_id, query, files, release_mode, user_id):
    prepared_agents = []
    now = time.time()
    for spec in normalized_agents:
        agent_id = spec["agent_id"]
        if not await thread_pool_exec(UserCanvasService.accessible, agent_id, tenant_id):
            raise PermissionError(f"Make sure you have permission to access the agent: {agent_id}.")
        workflow_ref = await _resolve_agent_workflow(
            agent_id,
            {"workflow_id": spec.get("workflow_id") or agent_id},
            tenant_id,
            release_mode,
        )
        agent_cvs = workflow_ref["agent_cvs"]
        workflow_cvs = workflow_ref["workflow_cvs"]
        dsl = workflow_ref["workflow_dsl"]
        workflow_id = workflow_ref["workflow_id"]
        if getattr(workflow_cvs, "canvas_category", CanvasCategory.Agent) == CanvasCategory.DataFlow:
            raise ValueError(f"Meeting runs for DataFlow canvases are not supported yet: {agent_id}.")

        session_id = spec.get("session_id")
        message_id = spec.get("message_id") or get_uuid()
        if session_id:
            exists, conv = await thread_pool_exec(API4ConversationService.get_by_id, session_id)
            if not exists:
                raise ValueError(f"Session not found for agent {agent_id}: {session_id}.")
            if getattr(conv, "dialog_id", None) != agent_id:
                raise ValueError(f"Session does not belong to agent {agent_id}: {session_id}.")
            workflow_conv = conv.to_dict()
            if not isinstance(workflow_conv.get("message"), list):
                workflow_conv["message"] = []
            workflow_conv["message"].append(
                {
                    "role": "user",
                    "content": query,
                    "id": message_id,
                    "files": files,
                    "created_at": now,
                    "meeting_id": meeting_id,
                    "meeting_turn_id": turn_id,
                }
            )
            await thread_pool_exec(API4ConversationService.update_by_id, session_id, workflow_conv)
        else:
            session_id = get_uuid()
            version_title = await thread_pool_exec(
                UserCanvasVersionService.get_latest_version_title,
                workflow_cvs.id,
                release_mode=release_mode,
            )
            workflow_conv = {
                "id": session_id,
                "dialog_id": agent_cvs.id,
                "user_id": user_id,
                "exp_user_id": user_id,
                "name": req.get("name", "") or f"{str(query or 'Meeting turn')[:60]} - {spec.get('role') or agent_id}",
                "message": [
                    {
                        "role": "user",
                        "content": query,
                        "id": message_id,
                        "files": files,
                        "created_at": now,
                        "meeting_id": meeting_id,
                        "meeting_turn_id": turn_id,
                    }
                ],
                "reference": [],
                "source": "workflow",
                "dsl": json.loads(dsl) if isinstance(dsl, str) else dsl,
                "version_title": version_title,
            }
            await thread_pool_exec(API4ConversationService.save, **workflow_conv)

        prepared = {**spec}
        prepared["session_id"] = session_id
        prepared["message_id"] = message_id
        prepared["workflow_id"] = workflow_id
        if not prepared.get("custom_header") and req.get("custom_header"):
            prepared["custom_header"] = req.get("custom_header")
        prepared_agents.append(prepared)
    return prepared_agents


@manager.route("/agents/meetings/runs", methods=["POST"])  # noqa: F821
@login_required
@add_tenant_id_to_kwargs
async def create_agent_meeting_runs(tenant_id):
    """Create one meeting turn and fan it out to multiple Agent runs."""
    req = await get_request_json()
    query = req.get("query", "") or req.get("question", "") or req.get("text", "")
    if not query:
        return get_data_error_result(message="`query` is required.")

    try:
        normalized_agents = AgentMeetingSchedulerService.normalize_agents(req.get("agents", []))
    except ValueError as exc:
        return get_data_error_result(message=str(exc))

    meeting_id = str(req.get("meeting_id") or get_uuid())
    turn_id = str(req.get("turn_id") or get_uuid())
    files = req.get("files", [])
    user_id = str(req.get("user_id") or tenant_id)
    release_mode = _request_bool(req.get("release", request.args.get("release")), True)

    try:
        prepared_agents = await _prepare_meeting_agent_sessions(
            tenant_id=tenant_id,
            req=req,
            normalized_agents=normalized_agents,
            meeting_id=meeting_id,
            turn_id=turn_id,
            query=query,
            files=files,
            release_mode=release_mode,
            user_id=user_id,
        )
        AgentMeetingMemoryService.append_shared(
            str(tenant_id),
            meeting_id,
            turn_id=turn_id,
            content=query,
            source="user",
            metadata={"files": files},
        )
        result = AgentMeetingSchedulerService.start_parallel_runs(
            tenant_id=str(tenant_id),
            meeting_id=meeting_id,
            turn_id=turn_id,
            query=query,
            agents=prepared_agents,
            files=files,
            shared_context=req.get("shared_context", ""),
            shared_memory=req.get("shared_memory") if isinstance(req.get("shared_memory"), list) else [],
            base_inputs=req.get("inputs") if isinstance(req.get("inputs"), dict) else {},
            user_id=user_id,
            release=release_mode,
            return_trace=_request_bool(req.get("return_trace"), True),
            enqueue=True,
        )
        return get_json_result(data=result)
    except LookupError:
        return get_data_error_result(message="Agent not found.")
    except PermissionError as exc:
        return get_data_error_result(message=str(exc))
    except ValueError as exc:
        return get_data_error_result(message=str(exc))
    except Exception as exc:
        return server_error_response(exc)


@manager.route("/agents/meetings/<meeting_id>/memory", methods=["POST"])  # noqa: F821
@login_required
@add_tenant_id_to_kwargs
async def append_agent_meeting_memory(meeting_id, tenant_id):
    """Append shared or per-agent memory for a meeting."""
    req = await get_request_json()
    content = str(req.get("content") or "").strip()
    if not content:
        return get_data_error_result(message="`content` is required.")

    turn_id = str(req.get("turn_id") or get_uuid())
    metadata = req.get("metadata") if isinstance(req.get("metadata"), dict) else {}
    scope = str(req.get("scope") or "shared").lower()
    if scope == "agent":
        agent_id = str(req.get("agent_id") or "").strip()
        if not agent_id:
            return get_data_error_result(message="`agent_id` is required for agent memory.")
        if not await thread_pool_exec(UserCanvasService.accessible, agent_id, tenant_id):
            return get_data_error_result(message="Make sure you have permission to access the agent.")
        record = AgentMeetingMemoryService.append_agent(
            str(tenant_id),
            meeting_id,
            agent_id,
            turn_id=turn_id,
            content=content,
            run_id=req.get("run_id"),
            role=str(req.get("role") or ""),
            metadata=metadata,
        )
    else:
        record = AgentMeetingMemoryService.append_shared(
            str(tenant_id),
            meeting_id,
            turn_id=turn_id,
            content=content,
            source=str(req.get("source") or "voice_service"),
            metadata=metadata,
        )
    return get_json_result(data={"meeting_id": meeting_id, "turn_id": turn_id, "memory": record})


@manager.route("/agents/meetings/results", methods=["POST"])  # noqa: F821
@login_required
@add_tenant_id_to_kwargs
async def get_agent_meeting_results(tenant_id):
    """Return fan-in summaries for a set of meeting Agent run ids."""
    req = await get_request_json()
    run_ids = req.get("run_ids", [])
    if not isinstance(run_ids, list) or not run_ids:
        return get_data_error_result(message="`run_ids` must contain at least one run id.")

    clean_run_ids = [str(run_id) for run_id in run_ids if str(run_id or "").strip()]
    for run_id in clean_run_ids:
        state = AgentRunService.get_state(str(tenant_id), run_id)
        if not state:
            return get_data_error_result(message=f"Agent run not found: {run_id}.")
        if not await thread_pool_exec(UserCanvasService.accessible, state.get("agent_id"), tenant_id):
            return get_data_error_result(message="Make sure you have permission to access the agent run.")
    return get_json_result(data=AgentMeetingSchedulerService.summarize_turn_results(tenant_id=str(tenant_id), run_ids=clean_run_ids))


@manager.route("/agents/teachers/defaults", methods=["GET"])  # noqa: F821
@login_required
@add_tenant_id_to_kwargs
def list_default_ai_teachers(tenant_id):
    validation = AgentTeacherRegistryService.validate_registry()
    return get_json_result(
        data={
            "teachers": AgentTeacherRegistryService.list_default_teachers(),
            "validation": validation,
        }
    )


@manager.route("/agents/<agent_id>/runs", methods=["GET"])  # noqa: F821
@login_required
@add_tenant_id_to_kwargs
@_require_canvas_access_sync
def list_agent_active_runs(agent_id, tenant_id):
    session_id = request.args.get("session_id")
    runs = AgentRunService.list_active(str(tenant_id), agent_id, session_id=session_id)
    return get_json_result(data={"runs": runs, "total": len(runs)})


def _get_accessible_agent_run(tenant_id, run_id):
    state = AgentRunService.get_state(tenant_id, run_id)
    if not state:
        return None
    if not UserCanvasService.accessible(state.get("agent_id"), tenant_id):
        return None
    return state


@manager.route("/agents/runs/<run_id>", methods=["GET"])  # noqa: F821
@login_required
@add_tenant_id_to_kwargs
def get_agent_run(run_id, tenant_id):
    state = _get_accessible_agent_run(tenant_id, run_id)
    if not state:
        return get_data_error_result(message="run not found.")
    return get_json_result(data=state)


@manager.route("/agents/runs/<run_id>/events", methods=["GET"])  # noqa: F821
@login_required
@add_tenant_id_to_kwargs
def get_agent_run_events(run_id, tenant_id):
    state = _get_accessible_agent_run(tenant_id, run_id)
    if not state:
        return get_data_error_result(message="run not found.")
    try:
        after_seq = int(request.args.get("after", -1))
    except Exception:
        after_seq = -1
    events = AgentRunService.get_events(tenant_id, run_id, after_seq)
    return get_json_result(
        data={
            "state": state,
            "events": events,
            "next_seq": events[-1]["seq"] if events else after_seq,
        }
    )


@manager.route("/agents/runs/<run_id>/trace", methods=["GET"])  # noqa: F821
@login_required
@add_tenant_id_to_kwargs
def get_agent_run_trace(run_id, tenant_id):
    state = _get_accessible_agent_run(tenant_id, run_id)
    if not state:
        return get_data_error_result(message="run not found.")
    trace = AgentRunService.get_trace(tenant_id, run_id)
    if not trace:
        return get_data_error_result(message="run not found.")
    return get_json_result(data=trace)


@manager.route("/agents/runs/<run_id>/artifacts", methods=["GET"])  # noqa: F821
@login_required
@add_tenant_id_to_kwargs
def get_agent_run_artifacts(run_id, tenant_id):
    state = _get_accessible_agent_run(tenant_id, run_id)
    if not state:
        return get_data_error_result(message="run not found.")
    artifacts = AgentRunService.get_artifacts(tenant_id, run_id)
    if artifacts is None:
        return get_data_error_result(message="run not found.")
    return get_json_result(data={"run_id": run_id, "artifacts": artifacts})


@manager.route("/agents/runs/<run_id>/cancel", methods=["POST"])  # noqa: F821
@login_required
@add_tenant_id_to_kwargs
def cancel_agent_run(run_id, tenant_id):
    state = _get_accessible_agent_run(tenant_id, run_id)
    if not state:
        return get_data_error_result(message="run not found.")
    return get_json_result(data={"canceled": AgentRunService.request_cancel(tenant_id, run_id)})


def _document_write_error_response(exc: DocumentWriteCoordinatorError):
    code = RetCode.ARGUMENT_ERROR if exc.code in {"INVALID_ARGUMENT", "INVALID_PATCH"} else RetCode.OPERATING_ERROR
    return get_json_result(data=exc.to_dict(), code=code, message=str(exc))


def _request_dict(req: dict, key: str) -> dict[str, Any]:
    value = req.get(key)
    return value if isinstance(value, dict) else {}


def _request_list(req: dict, key: str) -> list[Any]:
    value = req.get(key)
    return value if isinstance(value, list) else []


@manager.route("/agents/documents/<document_id>/snapshots", methods=["POST"])  # noqa: F821
@login_required
@add_tenant_id_to_kwargs
async def publish_agent_document_snapshot(document_id, tenant_id):
    req = await get_request_json()
    try:
        snapshot = AgentDocumentWriteCoordinatorService.publish_snapshot(
            tenant_id=str(tenant_id),
            document_id=document_id,
            content=req.get("content", ""),
            version=req.get("version"),
            metadata=_request_dict(req, "metadata"),
            source=str(req.get("source") or "api_snapshot_publish"),
            audit=_request_dict(req, "audit"),
        )
    except DocumentWriteCoordinatorError as exc:
        return _document_write_error_response(exc)
    except Exception as exc:
        return server_error_response(exc)
    return get_json_result(data=snapshot)


@manager.route("/agents/documents/<document_id>/snapshots/<int:version>", methods=["GET"])  # noqa: F821
@login_required
@add_tenant_id_to_kwargs
def get_agent_document_snapshot(document_id, version, tenant_id):
    try:
        snapshot = AgentDocumentWriteCoordinatorService.get_snapshot(
            tenant_id=str(tenant_id),
            document_id=document_id,
            version=version,
        )
    except DocumentWriteCoordinatorError as exc:
        return _document_write_error_response(exc)
    except Exception as exc:
        return server_error_response(exc)
    return get_json_result(data=snapshot)


@manager.route("/agents/documents/<document_id>/snapshots/current", methods=["GET"])  # noqa: F821
@login_required
@add_tenant_id_to_kwargs
def get_current_agent_document_snapshot(document_id, tenant_id):
    try:
        snapshot = AgentDocumentWriteCoordinatorService.get_snapshot(
            tenant_id=str(tenant_id),
            document_id=document_id,
        )
    except DocumentWriteCoordinatorError as exc:
        return _document_write_error_response(exc)
    except Exception as exc:
        return server_error_response(exc)
    return get_json_result(data=snapshot)


@manager.route("/agents/documents/<document_id>/patch-proposals", methods=["POST"])  # noqa: F821
@login_required
@add_tenant_id_to_kwargs
async def submit_agent_document_patch_proposal(document_id, tenant_id):
    req = await get_request_json()
    proposal = _request_dict(req, "proposal") or req
    proposal = {**proposal, "base_document_id": document_id}
    try:
        stored = AgentDocumentWriteCoordinatorService.submit_patch_proposal(
            tenant_id=str(tenant_id),
            proposal=proposal,
            authorized_agent_ids=_request_list(req, "authorized_agent_ids") or None,
        )
    except DocumentWriteCoordinatorError as exc:
        return _document_write_error_response(exc)
    except Exception as exc:
        return server_error_response(exc)
    return get_json_result(data=stored)


@manager.route("/agents/documents/<document_id>/writes", methods=["POST"])  # noqa: F821
@login_required
@add_tenant_id_to_kwargs
async def apply_agent_document_write(document_id, tenant_id):
    req = await get_request_json()
    try:
        result = AgentDocumentWriteCoordinatorService.apply_write_request(
            tenant_id=str(tenant_id),
            document_id=document_id,
            expected_version=int(req.get("expected_version") or 0),
            selected_proposals=[str(item) for item in _request_list(req, "selected_proposals")],
            merge_strategy=str(req.get("merge_strategy") or "single_writer"),
            source=str(req.get("source") or "api_write_coordinator"),
            audit=_request_dict(req, "audit"),
            authorized_agent_ids=_request_list(req, "authorized_agent_ids") or None,
        )
    except DocumentWriteCoordinatorError as exc:
        return _document_write_error_response(exc)
    except Exception as exc:
        return server_error_response(exc)
    return get_json_result(data=result)


@manager.route("/agents/documents/<document_id>/rollback", methods=["POST"])  # noqa: F821
@login_required
@add_tenant_id_to_kwargs
async def rollback_agent_document(document_id, tenant_id):
    req = await get_request_json()
    try:
        result = AgentDocumentWriteCoordinatorService.rollback(
            tenant_id=str(tenant_id),
            document_id=document_id,
            target_version=int(req.get("target_version") or 0),
            expected_version=int(req["expected_version"]) if req.get("expected_version") is not None else None,
            source=str(req.get("source") or "api_rollback"),
            audit=_request_dict(req, "audit"),
        )
    except DocumentWriteCoordinatorError as exc:
        return _document_write_error_response(exc)
    except Exception as exc:
        return server_error_response(exc)
    return get_json_result(data=result)


@manager.route("/agents/documents/<document_id>/audit", methods=["GET"])  # noqa: F821
@login_required
@add_tenant_id_to_kwargs
def list_agent_document_audit(document_id, tenant_id):
    try:
        audit = AgentDocumentWriteCoordinatorService.list_audit(
            tenant_id=str(tenant_id),
            document_id=document_id,
        )
    except DocumentWriteCoordinatorError as exc:
        return _document_write_error_response(exc)
    except Exception as exc:
        return server_error_response(exc)
    return get_json_result(data={"document_id": document_id, "audit": audit})


@manager.route("/agents/<agent_id>/invoke", methods=["POST"])  # noqa: F821
@login_required
@add_tenant_id_to_kwargs
@_require_canvas_access_async
async def invoke_agent_public(agent_id, tenant_id):
    """Run an Agent through the stable external response adapter."""
    req = await get_request_json()
    query = str(req.get("query", "") or req.get("question", "") or "").strip()
    if not query:
        return get_json_result(
            data=AgentPublicResponseService.build_response(
                agent_id=agent_id,
                workflow_id=str(req.get("workflow_id") or agent_id),
                status="failed",
                error=AgentPublicResponseService.normalize_error("INVALID_ARGUMENT", "`query` is required."),
            ),
            code=RetCode.ARGUMENT_ERROR,
            message="`query` is required.",
        )

    workflow_id = str(req.get("workflow_id") or agent_id)
    if _request_bool(req.get("stream"), False):
        return get_json_result(
            data=AgentPublicResponseService.build_response(
                agent_id=agent_id,
                workflow_id=workflow_id,
                status="failed",
                error=AgentPublicResponseService.normalize_error(
                    "UNSUPPORTED_STREAM",
                    "The public invoke endpoint returns a standard non-stream result. Use background runs for async execution.",
                ),
            ),
            code=RetCode.ARGUMENT_ERROR,
            message="The public invoke endpoint does not support stream output.",
        )
    try:
        request_dataset_ids = _normalize_public_dataset_ids(req)
        deadline_ms = _request_deadline_ms(req.get("deadline_ms"))
    except ValueError as exc:
        return get_json_result(
            data=AgentPublicResponseService.build_response(
                agent_id=agent_id,
                workflow_id=workflow_id,
                status="failed",
                error=AgentPublicResponseService.normalize_error("INVALID_ARGUMENT", str(exc)),
            ),
            code=RetCode.ARGUMENT_ERROR,
            message=str(exc),
        )

    release_mode = _request_bool(req.get("release", request.args.get("release")), True)
    files = req.get("files", [])
    inputs = req.get("inputs", {})
    session_id = req.get("session_id")
    user_id = str(req.get("user_id") or tenant_id)
    custom_header = req.get("custom_header", "")
    return_trace = bool(req.get("return_trace", False))
    chat_template_kwargs = req.get("chat_template_kwargs")

    try:
        from agent.canvas import Canvas

        workflow_ref = await _resolve_agent_workflow(
            agent_id,
            req,
            tenant_id,
            release_mode,
        )
    except LookupError:
        return get_data_error_result(message="Agent not found.")
    except PermissionError as exc:
        return get_data_error_result(message=str(exc))
    except Exception as exc:
        return server_error_response(exc)

    agent_cvs = workflow_ref["agent_cvs"]
    workflow_cvs = workflow_ref["workflow_cvs"]
    dsl = workflow_ref["workflow_dsl"]
    canvas_category = getattr(workflow_cvs, "canvas_category", CanvasCategory.Agent)
    if canvas_category == CanvasCategory.DataFlow:
        return get_json_result(
            data=AgentPublicResponseService.build_response(
                agent_id=agent_id,
                workflow_id=workflow_id,
                status="failed",
                error=AgentPublicResponseService.normalize_error(
                    "UNSUPPORTED_CANVAS_TYPE",
                    "The public invoke endpoint does not support DataFlow canvases.",
                ),
            ),
            code=RetCode.ARGUMENT_ERROR,
            message="The public invoke endpoint does not support DataFlow canvases.",
        )

    try:
        canvas = Canvas(dsl, str(tenant_id), canvas_id=workflow_id, custom_header=custom_header)
    except Exception as exc:
        return server_error_response(exc)

    turn_id = get_uuid()
    now = time.time()
    if session_id:
        exists, conv = await thread_pool_exec(API4ConversationService.get_by_id, session_id)
        if not exists:
            return get_data_error_result(message="Session not found!")
        if getattr(conv, "dialog_id", None) != agent_id:
            return get_data_error_result(message="Session does not belong to the requested agent.")
        workflow_conv = conv.to_dict()
        if not isinstance(workflow_conv.get("message"), list):
            workflow_conv["message"] = []
        workflow_conv["message"].append(
            {
                "role": "user",
                "content": query,
                "id": turn_id,
                "files": files,
                "created_at": now,
            }
        )
        await thread_pool_exec(API4ConversationService.update_by_id, session_id, workflow_conv)
    else:
        session_id = get_uuid()
        version_title = await thread_pool_exec(
            UserCanvasVersionService.get_latest_version_title,
            workflow_cvs.id,
            release_mode=release_mode,
        )
        workflow_conv = {
            "id": session_id,
            "dialog_id": agent_cvs.id,
            "user_id": user_id,
            "exp_user_id": user_id,
            "name": req.get("name", "") or str(query or "New Session")[:80],
            "message": [
                {
                    "role": "user",
                    "content": query,
                    "id": turn_id,
                    "files": files,
                    "created_at": now,
                }
            ],
            "reference": [],
            "source": "workflow",
            "dsl": json.loads(dsl) if isinstance(dsl, str) else dsl,
            "version_title": version_title,
        }
        await thread_pool_exec(API4ConversationService.save, **workflow_conv)

    workflow_version_title = await thread_pool_exec(
        UserCanvasVersionService.get_latest_version_title,
        workflow_cvs.id,
        release_mode=release_mode,
    )

    run_id = get_uuid()
    final_ans = await _run_workflow_session(
        tenant_id=tenant_id,
        agent_id=agent_id,
        workflow_conv=workflow_conv,
        canvas=canvas,
        query=query,
        files=files,
        inputs=inputs,
        user_id=user_id,
        session_id=session_id,
        custom_header=custom_header,
        canvas_title=getattr(workflow_cvs, "title", ""),
        canvas_category=canvas_category,
        return_trace=return_trace,
        stream=False,
        chat_template_kwargs=chat_template_kwargs,
        external_context=req.get("external_context"),
        request_dataset_ids=request_dataset_ids,
        run_id=run_id,
        workflow_id=workflow_id,
        workflow_version_title=workflow_version_title,
        deadline_ms=deadline_ms,
        return_response=False,
    )
    trace = AgentRunService.get_trace(str(tenant_id), run_id) or {}
    error = None
    if isinstance(final_ans, dict) and final_ans.get("error"):
        error = AgentPublicResponseService.normalize_error("AGENT_RUN_FAILED", final_ans.get("error"))
    public_response = AgentPublicResponseService.from_final_answer(
        agent_id=agent_id,
        workflow_id=workflow_id,
        run_id=run_id,
        session_id=session_id,
        message_id=turn_id,
        final_answer=final_ans,
        trace=trace,
        status="failed" if error else None,
        error=error,
    )
    return get_json_result(data=public_response)


@manager.route("/agents/runs/<run_id>/result", methods=["GET"])  # noqa: F821
@login_required
@add_tenant_id_to_kwargs
def get_agent_run_public_result(run_id, tenant_id):
    state = _get_accessible_agent_run(str(tenant_id), run_id)
    if not state:
        return get_data_error_result(message="run not found.")
    trace = AgentRunService.get_trace(str(tenant_id), run_id) or {}
    session_answer = {"answer": "", "references": [], "message_id": state.get("message_id", "")}
    session_id = state.get("session_id")
    if session_id:
        exists, conv = API4ConversationService.get_by_id(session_id)
        if exists and getattr(conv, "dialog_id", None) == state.get("agent_id"):
            session_answer = _extract_public_session_answer(conv.to_dict(), state.get("message_id"))
    status = _agent_run_public_status(state)
    error = None
    if status in {"failed", "canceled", "timeout"}:
        trace_workflow = trace.get("workflow") if isinstance(trace.get("workflow"), dict) else {}
        error_code = "AGENT_TIMEOUT" if status == "timeout" else "AGENT_RUN_" + status.upper()
        error = AgentPublicResponseService.normalize_error(
            error_code,
            state.get("error") or trace_workflow.get("error") or status,
            retryable=status in {"timeout"},
        )
    metadata = state.get("metadata") if isinstance(state.get("metadata"), dict) else {}
    return get_json_result(
        data=AgentPublicResponseService.build_response(
            agent_id=state.get("agent_id", ""),
            workflow_id=metadata.get("workflow_id") or state.get("agent_id", ""),
            run_id=run_id,
            session_id=session_id or "",
            message_id=session_answer.get("message_id") or state.get("message_id", ""),
            status=status,
            answer=session_answer.get("answer", ""),
            references=session_answer.get("references"),
            downloads=trace.get("downloads"),
            trace=trace,
            error=error,
        )
    )


@manager.route("/agents/download", methods=["GET"])  # noqa: F821
@login_required
@add_tenant_id_to_kwargs
async def download_agent_file(tenant_id):
    id = request.args.get("id")
    run_id = request.args.get("run_id") or ""
    session_id = request.args.get("session_id") or ""
    logging.info("Agent file download requested: tenant_id=%s file_id=%s run_id=%s", tenant_id, id, run_id)
    try:
        artifact = AgentArtifactRegistryService.authorize_download(
            tenant_id=str(tenant_id),
            artifact_id=str(id or ""),
            requested_run_id=run_id,
            requested_session_id=session_id,
        )
        if run_id:
            state = _get_accessible_agent_run(str(tenant_id), run_id)
            if not state:
                AgentArtifactRegistryService.record_audit(
                    tenant_id=str(tenant_id),
                    artifact_id=str(id or ""),
                    event="permission_denied",
                    payload={"action": "artifact_download", "reason": "run_not_accessible", "requested_run_id": run_id},
                )
                return get_json_result(data=False, message="No authorization.", code=RetCode.AUTHENTICATION_ERROR)
            if session_id and state.get("session_id") != session_id:
                AgentArtifactRegistryService.record_audit(
                    tenant_id=str(tenant_id),
                    artifact_id=str(id or ""),
                    event="permission_denied",
                    payload={
                        "action": "artifact_download",
                        "reason": "session_id_mismatch",
                        "requested_session_id": session_id,
                        "run_session_id": state.get("session_id"),
                    },
                )
                return get_json_result(data=False, message="No authorization.", code=RetCode.AUTHENTICATION_ERROR)
        blob = await thread_pool_exec(FileService.get_blob, tenant_id, id)
        AgentArtifactRegistryService.record_audit(
            tenant_id=str(tenant_id),
            artifact_id=str(id or ""),
            event="artifact_downloaded",
            payload={"run_id": run_id, "session_id": session_id},
        )
        response = await make_response(blob)
        mime_type = artifact.get("mime_type") or "application/octet-stream"
        ext = (artifact.get("filename") or "").rsplit(".", 1)[-1] if "." in (artifact.get("filename") or "") else ""
        apply_safe_file_response_headers(response, mime_type, ext)
        return response
    except ArtifactPermissionError as exc:
        logging.warning("Agent artifact download denied. tenant_id=%s artifact_id=%s error=%s", tenant_id, id, exc.code)
        return get_json_result(data=exc.to_dict(), message=str(exc), code=RetCode.AUTHENTICATION_ERROR)


async def _iter_session_completion_events(tenant_id, agent_id, req, return_trace):
    # Stream and non-stream session completions share the same event parsing and trace injection.
    trace_items = []
    async for answer in agent_completion(tenant_id=tenant_id, agent_id=agent_id, **req):
        if isinstance(answer, str):
            try:
                ans = json.loads(answer[5:])
            except Exception:
                continue
        else:
            ans = answer

        event = ans.get("event")
        if event == "node_finished":
            if return_trace:
                data = ans.get("data", {})
                trace_items.append(
                    {
                        "component_id": data.get("component_id"),
                        "trace": [copy.deepcopy(data)],
                    }
                )
                ans.setdefault("data", {})["trace"] = trace_items
            yield ans
            continue

        if event in ["message", "message_end"]:
            yield ans


@manager.route("/agents/templates", methods=["GET"])  # noqa: F821
@login_required
def list_agent_template():
    return get_json_result(data=CanvasTemplateService.get_all_with_builtin())


@manager.route("/agents/operators/schema", methods=["GET"])  # noqa: F821
@login_required
def list_agent_operator_schema():
    return get_json_result(data={"operators": list_operator_manifests()})


@manager.route("/agents/file-parser/health", methods=["GET"])  # noqa: F821
@login_required
def file_parser_health():
    layout_recognize = request.args.get("layout_recognize", "DeepDOC")
    deep = _request_bool(request.args.get("deep"), False)
    return get_json_result(data=FileParser.local_ocr_deepdoc_health(layout_recognize=layout_recognize, deep=deep))


@manager.route("/agents/prompts", methods=["GET"])  # noqa: F821
@login_required
def prompts():
    from rag.prompts.generator import (
        ANALYZE_TASK_SYSTEM,
        ANALYZE_TASK_USER,
        CITATION_PROMPT_TEMPLATE,
        NEXT_STEP,
        REFLECT,
    )

    return get_json_result(
        data={
            "task_analysis": f"{ANALYZE_TASK_SYSTEM}\n\n{ANALYZE_TASK_USER}",
            "plan_generation": NEXT_STEP,
            "reflection": REFLECT,
            "citation_guidelines": CITATION_PROMPT_TEMPLATE,
        }
    )


@manager.route("/agents", methods=["GET"])  # noqa: F821
@login_required
@add_tenant_id_to_kwargs
def list_agents(tenant_id):
    keywords = request.args.get("keywords", "")
    canvas_category = request.args.get("canvas_category")
    owner_ids = [item for item in request.args.get("owner_ids", "").strip().split(",") if item]
    tags = [item for item in request.args.get("tags", "").strip().split(",") if item]

    page_number = int(request.args.get("page", 0))
    items_per_page = int(request.args.get("page_size", 0))
    order_by = request.args.get("orderby", "create_time")
    desc = str(request.args.get("desc", "true")).lower() != "false"
    tenants = TenantService.get_joined_tenants_by_user_id(tenant_id)
    authorized_owner_ids = {member["tenant_id"] for member in tenants}
    authorized_owner_ids.add(tenant_id)

    if owner_ids:
        requested_owner_ids = set(owner_ids)
        unauthorized_owner_ids = requested_owner_ids - authorized_owner_ids
        if unauthorized_owner_ids:
            return get_json_result(
                data=False,
                message="Only authorized owner_ids can be queried.",
                code=RetCode.OPERATING_ERROR,
            )
        effective_owner_ids = list(requested_owner_ids)
    else:
        effective_owner_ids = list(authorized_owner_ids)

    canvas, total = UserCanvasService.get_by_tenant_ids(
        effective_owner_ids,
        tenant_id,
        page_number,
        items_per_page,
        order_by,
        desc,
        keywords,
        canvas_category,
        tags,
    )

    return get_json_result(data={"canvas": canvas, "total": total})


@manager.route("/agents/tags", methods=["GET"])  # noqa: F821
@login_required
@add_tenant_id_to_kwargs
def list_agent_tags(tenant_id):
    """Aggregate tag usage counts across agents visible to the caller."""
    canvas_category = request.args.get("canvas_category")
    tenants = TenantService.get_joined_tenants_by_user_id(tenant_id)
    joined_ids = list({member["tenant_id"] for member in tenants} | {tenant_id})
    counts = UserCanvasService.list_tags(joined_ids, tenant_id, canvas_category)
    logging.info(
        "list_agent_tags tenant=%s canvas_category=%s tags_count=%d",
        tenant_id,
        canvas_category,
        len(counts),
    )
    return get_json_result(data=[{"tag": k, "count": v} for k, v in sorted(counts.items(), key=lambda x: (-x[1], x[0]))])


@manager.route("/agents/<canvas_id>/tags", methods=["PUT"])  # noqa: F821
@login_required
@add_tenant_id_to_kwargs
async def update_agent_tags(tenant_id, canvas_id):
    if not UserCanvasService.accessible(canvas_id, tenant_id):
        logging.info(
            "update_agent_tags denied tenant=%s canvas_id=%s reason=no_permission",
            tenant_id,
            canvas_id,
        )
        return get_json_result(
            data=False,
            message="Agent not found or no permission.",
            code=RetCode.OPERATING_ERROR,
        )
    req = await get_request_json()
    tags = req.get("tags", "")
    incoming = tags if isinstance(tags, (list, tuple)) else [t for t in str(tags).split(",") if t.strip()]
    rows_affected = UserCanvasService.update_tags(canvas_id, tags)
    if rows_affected == 0:
        logging.info(
            "update_agent_tags miss tenant=%s canvas_id=%s incoming_count=%d rows=0",
            tenant_id,
            canvas_id,
            len(incoming),
        )
        return get_json_result(
            data=False,
            message="Agent not found or no permission.",
            code=RetCode.OPERATING_ERROR,
        )
    logging.info(
        "update_agent_tags ok tenant=%s canvas_id=%s incoming_count=%d rows=%d",
        tenant_id,
        canvas_id,
        len(incoming),
        rows_affected,
    )
    return get_json_result(data=True)


@manager.route("/agents", methods=["POST"])  # noqa: F821
@login_required
@add_tenant_id_to_kwargs
async def create_agent(tenant_id):
    req = {k: v for k, v in (await get_request_json()).items() if v is not None}
    req["canvas_type"] = req.get("canvas_type","")
    req["user_id"] = tenant_id
    req["canvas_category"] = req.get("canvas_category") or CanvasCategory.Agent
    req["release"] = _request_bool(req.get("release"), False)
    req["avatar"] = req.get("avatar") or "/righttime-logo.png"

    if req.get("dsl") is None:
        return get_json_result(
            data=False,
            message="No DSL data in request.",
            code=RetCode.ARGUMENT_ERROR,
        )

    try:
        req["dsl"] = CanvasReplicaService.normalize_dsl(req["dsl"])
    except ValueError as exc:
        return get_json_result(
            data=False,
            message=str(exc),
            code=RetCode.ARGUMENT_ERROR,
        )

    if req.get("title") is None:
        return get_json_result(
            data=False,
            message="No title in request.",
            code=RetCode.ARGUMENT_ERROR,
        )

    req["title"] = req["title"].strip()
    if UserCanvasService.query(
        user_id=tenant_id,
        title=req["title"],
        canvas_category=req["canvas_category"],
    ):
        return get_data_error_result(message=f"{req['title']} already exists.")

    req["id"] = get_uuid()
    _ensure_default_agent_workspace(req["dsl"], req["id"], tenant_id=tenant_id, title=req["title"])

    if req.get("release") is True:
        validation_error = _release_validation_error(req["dsl"])
        if validation_error:
            return validation_error

    if not UserCanvasService.save(**req):
        return get_data_error_result(message="Fail to create agent.")

    owner_nickname = _get_user_nickname(tenant_id)
    UserCanvasVersionService.save_or_replace_latest(
        user_canvas_id=req["id"],
        title=UserCanvasVersionService.build_version_title(owner_nickname, req.get("title")),
        dsl=req["dsl"],
        release=req.get("release"),
    )
    replica_ok = CanvasReplicaService.replace_for_set(
        canvas_id=req["id"],
        tenant_id=str(tenant_id),
        runtime_user_id=str(tenant_id),
        dsl=req["dsl"],
        canvas_category=req["canvas_category"],
        title=req.get("title", ""),
    )
    if not replica_ok:
        return get_data_error_result(message="canvas saved, but replica sync failed.")

    exists, created_agent = UserCanvasService.get_by_canvas_id(req["id"])
    if not exists:
        return get_data_error_result(message="Fail to create agent.")
    return get_json_result(data=created_agent)


@manager.route("/agents/<agent_id>/upload", methods=["POST"])  # noqa: F821
@login_required
@add_tenant_id_to_kwargs
@_require_canvas_access_async
async def upload_agent_file(agent_id, tenant_id):
    files = await request.files
    file_objs = files.getlist("file") if files and files.get("file") else []
    logging.info(
        "Agent file upload requested: tenant_id=%s agent_id=%s file_count=%s",
        tenant_id,
        agent_id,
        len(file_objs),
    )
    try:
        if len(file_objs) == 1:
            uploaded = await thread_pool_exec(
                FileService.upload_info, tenant_id, file_objs[0], request.args.get("url")
            )
            return get_json_result(data=uploaded)
        results = await asyncio.gather(
            *(thread_pool_exec(FileService.upload_info, tenant_id, file_obj) for file_obj in file_objs)
        )
        return get_json_result(data=results)
    except Exception as exc:
        logging.exception(
            "Agent file upload failed: tenant_id=%s agent_id=%s",
            tenant_id,
            agent_id,
        )
        return server_error_response(exc)


@manager.route("/agents/<agent_id>/components/<component_id>/input-form", methods=["GET"])  # noqa: F821
@login_required
@add_tenant_id_to_kwargs
@_require_canvas_access_sync
def get_agent_component_input_form(agent_id, component_id, tenant_id):
    try:
        from agent.canvas import Canvas

        exists, user_canvas = UserCanvasService.get_by_id(agent_id)
        if not exists:
            return get_data_error_result(message="canvas not found.")
        canvas = Canvas(json.dumps(user_canvas.dsl), tenant_id, canvas_id=user_canvas.id)
        return get_json_result(data=canvas.get_component_input_form(component_id))
    except Exception as exc:
        return server_error_response(exc)


@manager.route("/agents/<agent_id>/components/<component_id>/contract", methods=["GET"])  # noqa: F821
@login_required
@add_tenant_id_to_kwargs
@_require_canvas_access_sync
def get_agent_component_contract(agent_id, component_id, tenant_id):
    try:
        from agent.canvas import Canvas

        exists, user_canvas = UserCanvasService.get_by_id(agent_id)
        if not exists:
            return get_data_error_result(message="canvas not found.")
        canvas = Canvas(json.dumps(user_canvas.dsl), tenant_id, canvas_id=user_canvas.id)
        return get_json_result(data=canvas.get_component_contract(component_id))
    except Exception as exc:
        return server_error_response(exc)


@manager.route("/agents/<agent_id>/validate", methods=["GET", "POST"])  # noqa: F821
@login_required
@add_tenant_id_to_kwargs
@_require_canvas_access_async
async def validate_agent(agent_id, tenant_id):
    try:
        dsl = None
        if request.method == "POST":
            req = await get_request_json()
            dsl = req.get("dsl")
            if dsl is not None:
                dsl = CanvasReplicaService.normalize_dsl(dsl)
        if dsl is None:
            exists, user_canvas = UserCanvasService.get_by_id(agent_id)
            if not exists:
                return get_data_error_result(message="canvas not found.")
            dsl = user_canvas.dsl
        return get_json_result(data=AgentValidationService.validate_for_publish(dsl))
    except ValueError as exc:
        return get_json_result(
            data=False,
            message=str(exc),
            code=RetCode.ARGUMENT_ERROR,
        )
    except Exception as exc:
        return server_error_response(exc)


@manager.route("/agents/<agent_id>/components/<component_id>/debug", methods=["POST"])  # noqa: F821
@validate_request("params")
@login_required
@add_tenant_id_to_kwargs
@_require_canvas_access_async
async def debug_agent_component(agent_id, component_id, tenant_id):
    req = await get_request_json()
    try:
        from agent.canvas import Canvas
        from agent.component import LLM

        _, user_canvas = UserCanvasService.get_by_id(agent_id)
        canvas = Canvas(json.dumps(user_canvas.dsl), tenant_id, canvas_id=user_canvas.id)
        canvas.reset()
        canvas.message_id = get_uuid()
        component = canvas.get_component(component_id)["obj"]
        component.reset()

        if isinstance(component, LLM):
            component.set_debug_inputs(req["params"])
        component.invoke(**{k: o["value"] for k, o in req["params"].items()})
        outputs = component.output()
        for k in outputs.keys():
            if isinstance(outputs[k], partial):
                txt = ""
                iter_obj = outputs[k]()
                if inspect.isasyncgen(iter_obj):
                    async for c in iter_obj:
                        txt += c
                else:
                    for c in iter_obj:
                        txt += c
                outputs[k] = txt
        return get_json_result(data=outputs)
    except Exception as exc:
        return server_error_response(exc)


@manager.route("/agents/<agent_id>", methods=["GET"])  # noqa: F821
@login_required
@add_tenant_id_to_kwargs
def get_agent(agent_id, tenant_id):
    if not UserCanvasService.accessible(agent_id, tenant_id):
        return get_data_error_result(message="canvas not found.")

    exists, canvas = UserCanvasService.get_by_canvas_id(agent_id)
    if not exists:
        return get_data_error_result(message="canvas not found.")

    try:
        CanvasReplicaService.bootstrap(
            canvas_id=agent_id,
            tenant_id=str(tenant_id),
            runtime_user_id=str(tenant_id),
            dsl=canvas.get("dsl"),
            canvas_category=canvas.get("canvas_category", CanvasCategory.Agent),
            title=canvas.get("title", ""),
        )
    except ValueError as exc:
        return get_data_error_result(message=str(exc))

    last_publish_time = None
    versions = UserCanvasVersionService.list_by_canvas_id(agent_id)
    if versions:
        released_versions = [version for version in versions if version.release]
        if released_versions:
            released_versions.sort(key=lambda version: version.update_time, reverse=True)
            last_publish_time = released_versions[0].update_time

    from agent.dsl_migration import normalize_chunker_dsl

    canvas["dsl"] = normalize_chunker_dsl(canvas.get("dsl", {}))
    canvas["last_publish_time"] = last_publish_time

    if canvas.get("canvas_category") == CanvasCategory.DataFlow:
        datasets = list(KnowledgebaseService.query(pipeline_id=agent_id))
        canvas["datasets"] = [{"id": item.id, "name": item.name, "avatar": item.avatar} for item in datasets]

    return get_json_result(data=canvas)


@manager.route("/agents/<agent_id>/versions", methods=["GET"])  # noqa: F821
@login_required
@add_tenant_id_to_kwargs
@_require_canvas_access_sync
def list_agent_versions(agent_id, tenant_id):
    try:
        versions = sorted(
            [item.to_dict() for item in UserCanvasVersionService.list_by_canvas_id(agent_id)],
            key=lambda item: item["update_time"] * -1,
        )
        return get_json_result(data=versions)
    except Exception as exc:
        return get_data_error_result(message=f"Error getting history files: {exc}")


@manager.route("/agents/<agent_id>/versions/<version_id>", methods=["GET"])  # noqa: F821
@login_required
@add_tenant_id_to_kwargs
@_require_canvas_access_sync
def get_agent_version(agent_id, version_id, tenant_id):
    try:
        exists, version = UserCanvasVersionService.get_by_id(version_id)
        if not exists or not version or str(version.user_canvas_id) != str(agent_id):
            return get_data_error_result(message="Version not found.")
        return get_json_result(data=version.to_dict())
    except Exception as exc:
        return get_data_error_result(message=f"Error getting history file: {exc}")


@manager.route("/agents/<agent_id>/logs/<message_id>", methods=["GET"])  # noqa: F821
@login_required
@add_tenant_id_to_kwargs
@_require_canvas_access_async
async def get_agent_logs(agent_id, message_id, tenant_id):
    try:
        from rag.utils.redis_conn import REDIS_CONN

        binary = await thread_pool_exec(REDIS_CONN.get, f"{agent_id}-{message_id}-logs")
        if not binary:
            return get_json_result(data={})

        payload = binary.decode("utf-8") if isinstance(binary, bytes) else binary
        return get_json_result(data=json.loads(payload))
    except Exception as exc:
        logging.exception(exc)
        return server_error_response(exc)


@manager.route("/agents/<agent_id>", methods=["DELETE"])  # noqa: F821
@login_required
@add_tenant_id_to_kwargs
@_require_canvas_owner_sync
def delete_agent(agent_id, tenant_id):
    UserCanvasService.delete_by_id(agent_id)
    return get_json_result(data=True)


@manager.route("/agents/<agent_id>", methods=["PUT"])  # noqa: F821
@login_required
@add_tenant_id_to_kwargs
@_require_canvas_access_async
async def update_agent(agent_id, tenant_id):
    req = {k: v for k, v in (await get_request_json()).items() if v is not None}
    req["canvas_type"] = req.get("canvas_type","")
    release_value = None
    if "release" in req:
        release_value = _request_bool(req.get("release"), False)
        req["release"] = release_value
    if "avatar" in req:
        req["avatar"] = req.get("avatar") or "/righttime-logo.png"

    if req.get("dsl") is not None:
        try:
            req["dsl"] = CanvasReplicaService.normalize_dsl(req["dsl"])
        except ValueError as exc:
            return get_json_result(
                data=False,
                message=str(exc),
                code=RetCode.ARGUMENT_ERROR,
            )

    if req.get("title") is not None:
        req["title"] = req["title"].strip()
    _normalize_case_agent_title(agent_id, req)
    _normalize_case_agent_dsl(agent_id, req)

    _, current_agent = UserCanvasService.get_by_id(agent_id)
    agent_title_for_version = req.get("title") or (current_agent.title if current_agent else "")
    canvas_category = (
        req.get("canvas_category")
        or (current_agent.canvas_category if current_agent else CanvasCategory.Agent)
    )
    owner_nickname = _get_user_nickname(tenant_id)

    if release_value is True:
        version_dsl = req.get("dsl") if req.get("dsl") is not None else current_agent.dsl
        validation_error = _release_validation_error(version_dsl)
        if validation_error:
            return validation_error

    UserCanvasService.update_by_id(agent_id, req)

    if req.get("dsl") is not None or release_value is True:
        version_dsl = req.get("dsl") if req.get("dsl") is not None else current_agent.dsl
        UserCanvasVersionService.save_or_replace_latest(
            user_canvas_id=agent_id,
            title=UserCanvasVersionService.build_version_title(owner_nickname, agent_title_for_version),
            dsl=version_dsl,
            release=release_value,
        )

    if req.get("dsl") is not None:
        replica_ok = CanvasReplicaService.replace_for_set(
            canvas_id=agent_id,
            tenant_id=str(tenant_id),
            runtime_user_id=str(tenant_id),
            dsl=req["dsl"],
            canvas_category=canvas_category,
            title=agent_title_for_version,
        )
        if not replica_ok:
            return get_data_error_result(message="agent saved, but replica sync failed.")

    return get_json_result(data=True)


@manager.route("/agents/<agent_id>/reset", methods=["POST"])  # noqa: F821
@login_required
@add_tenant_id_to_kwargs
@_require_canvas_access_async
async def reset_agent(agent_id, tenant_id):
    try:
        from agent.canvas import Canvas

        exists, user_canvas = UserCanvasService.get_by_id(agent_id)
        if not exists:
            return get_data_error_result(message="canvas not found.")

        canvas = Canvas(json.dumps(user_canvas.dsl), tenant_id, canvas_id=user_canvas.id)
        canvas.reset()
        dsl = json.loads(str(canvas))
        UserCanvasService.update_by_id(agent_id, {"dsl": dsl})
        replica_ok = CanvasReplicaService.replace_for_set(
            canvas_id=agent_id,
            tenant_id=str(tenant_id),
            runtime_user_id=str(tenant_id),
            dsl=dsl,
            canvas_category=user_canvas.canvas_category,
            title=user_canvas.title,
        )
        if not replica_ok:
            return get_data_error_result(message="agent reset, but replica sync failed.")
        return get_json_result(data=dsl)
    except Exception as exc:
        return server_error_response(exc)


@manager.route("/agents/rerun", methods=["POST"])  # noqa: F821
@validate_request("id", "dsl", "component_id")
@login_required
@add_tenant_id_to_kwargs
async def rerun_agent(tenant_id):
    from rag.nlp import search

    req = await get_request_json()
    doc = PipelineOperationLogService.get_documents_info(req["id"])
    if not doc:
        return get_data_error_result(message="Document not found.")
    doc = doc[0]
    if 0 < doc["progress"] < 1:
        return get_data_error_result(message=f"`{doc['name']}` is processing...")

    if settings.docStoreConn.index_exist(search.index_name(tenant_id), doc["kb_id"]):
        settings.docStoreConn.delete({"doc_id": doc["id"]}, search.index_name(tenant_id), doc["kb_id"])
    doc["progress_msg"] = ""
    doc["chunk_num"] = 0
    doc["token_num"] = 0
    DocumentService.clear_chunk_num_when_rerun(doc["id"])
    DocumentService.update_by_id(doc["id"], doc)
    TaskService.filter_delete([Task.doc_id == doc["id"]])

    dsl = req["dsl"]
    dsl["path"] = [req["component_id"]]
    PipelineOperationLogService.update_by_id(req["id"], {"dsl": dsl})
    queue_dataflow(
        tenant_id=tenant_id,
        flow_id=req["id"],
        task_id=get_uuid(),
        doc_id=doc["id"],
        priority=0,
        rerun=True,
    )
    return get_json_result(data=True)


@manager.route("/agents/test_db_connection", methods=["POST"])  # noqa: F821
@validate_request("db_type", "database", "username", "host", "port", "password")
@login_required
async def test_db_connection():
    req = await get_request_json()
    try:
        safe_host = assert_host_is_safe(req["host"])
    except ValueError as exc:
        logging.warning(
            "Rejected test_db_connection: unsafe host %r (db_type=%s, user=%s): %s",
            req.get("host"), req.get("db_type"), current_user.id, exc,
        )
        return get_data_error_result(message=str(exc))
    except OSError as exc:
        logging.warning(
            "Rejected test_db_connection: cannot resolve host %r (db_type=%s, user=%s): %s",
            req.get("host"), req.get("db_type"), current_user.id, exc,
        )
        logging.debug("Full resolver exception for host %r", req.get("host"), exc_info=True)
        return get_data_error_result(message=f"Could not resolve host {req.get('host')!r}.")
    try:
        if req["db_type"] in ["mysql", "mariadb"]:
            db = MySQLDatabase(
                req["database"],
                user=req["username"],
                host=safe_host,
                port=req["port"],
                password=req["password"],
            )
            with db.connection_context():
                db.execute_sql("SELECT 1")
        elif req["db_type"] == "oceanbase":
            db = MySQLDatabase(
                req["database"],
                user=req["username"],
                host=safe_host,
                port=req["port"],
                password=req["password"],
                charset="utf8mb4",
            )
            with db.connection_context():
                db.execute_sql("SELECT 1")
        elif req["db_type"] == "postgres":
            db = PostgresqlDatabase(
                req["database"],
                user=req["username"],
                host=safe_host,
                port=req["port"],
                password=req["password"],
            )
            with db.connection_context():
                db.execute_sql("SELECT 1")
        elif req["db_type"] == "mssql":
            import pyodbc

            connection_string = (
                f"DRIVER={{ODBC Driver 17 for SQL Server}};"
                f"SERVER={safe_host},{req['port']};"
                f"DATABASE={req['database']};"
                f"UID={req['username']};"
                f"PWD={req['password']};"
            )
            db = pyodbc.connect(connection_string)
            try:
                cursor = db.cursor()
                try:
                    cursor.execute("SELECT 1")
                finally:
                    cursor.close()
            finally:
                db.close()
        elif req["db_type"] == "IBM DB2":
            import ibm_db

            conn_str = (
                f"DATABASE={req['database']};"
                f"HOSTNAME={safe_host};"
                f"PORT={req['port']};"
                f"PROTOCOL=TCPIP;"
                f"UID={req['username']};"
                f"PWD={req['password']};"
            )
            logging.info(
                "DATABASE=%s;HOSTNAME=%s;PORT=%s;PROTOCOL=TCPIP;UID=%s;PWD=****;",
                req["database"],
                safe_host,
                req["port"],
                req["username"],
            )
            conn = ibm_db.connect(conn_str, "", "")
            stmt = ibm_db.exec_immediate(conn, "SELECT 1 FROM sysibm.sysdummy1")
            ibm_db.fetch_assoc(stmt)
            ibm_db.close(conn)
        elif req["db_type"] == "trino":
            import os
            import trino

            db_name = req["database"]
            if "." in db_name:
                catalog, schema = db_name.split(".", 1)
            elif "/" in db_name:
                catalog, schema = db_name.split("/", 1)
            else:
                catalog, schema = db_name, "default"

            http_scheme = "https" if os.environ.get("TRINO_USE_TLS", "0") == "1" else "http"
            auth = None
            if http_scheme == "https" and req.get("password"):
                auth = trino.BasicAuthentication(req.get("username") or "ragflow", req["password"])

            conn = trino.dbapi.connect(
                host=safe_host,
                port=int(req["port"] or 8080),
                user=req["username"] or "ragflow",
                catalog=catalog,
                schema=schema or "default",
                http_scheme=http_scheme,
                auth=auth,
            )
            try:
                cur = conn.cursor()
                try:
                    cur.execute("SELECT 1")
                    cur.fetchall()
                finally:
                    cur.close()
            finally:
                conn.close()
        else:
            return server_error_response("Unsupported database type.")

        return get_json_result(data="Database Connection Successful!")
    except Exception as exc:
        return server_error_response(exc)


@manager.route("/agents/chat/completion", methods=["POST"])  # noqa: F821
@manager.route("/agents/chat/completions", methods=["POST"])  # noqa: F821
@login_required
@add_tenant_id_to_kwargs
async def agent_chat_completion(tenant_id, agent_id=None):
    # This endpoint serves two execution modes:
    # 1. Draft/runtime execution without session state. The request runs against the caller's
    #    runtime replica, which is populated from the editable canvas state.
    # 2. Session continuation with an existing session_id. The request resumes from the stored
    #    API4Conversation state and must stay bound to the same agent and an accessible canvas.
    #
    # Security constraints:
    # - agent_id is always supplied at the route layer and is not forwarded downstream as a free-form kwarg.
    # - New runs without session_id must pass UserCanvasService.accessible(...) before the runtime replica is loaded.
    # - Existing sessions are validated here at the route layer before handing control to the lower-level
    #   completion functions, so canvas_service only executes a pre-authorized session payload.
    #
    # Response modes:
    # - Regular mode emits internal agent events.
    # - openai-compatible mode reshapes the same execution into an OpenAI-like wire format.
    req = await get_request_json()
    agent_id = agent_id or req.get("agent_id")
    openai_compatible = bool(req.get("openai-compatible", False))
    if not agent_id:
        return get_json_result(
            data=False,
            message="`agent_id` is required.",
            code=RetCode.ARGUMENT_ERROR,
        )
    # Route-level selectors should not be forwarded into the lower-level completion functions.
    req = dict(req)
    req.pop("agent_id", None)
    req.pop("openai-compatible", None)
    try:
        request_dataset_ids = _normalize_public_dataset_ids(req)
    except ValueError as exc:
        return get_data_error_result(message=str(exc))
    session_id = req.get("session_id")
    workflow_session = False
    workflow_conv = None
    if session_id:
        exists, conv = API4ConversationService.get_by_id(session_id)
        if not exists:
            return get_data_error_result(message="Session not found!")
        if conv.dialog_id != agent_id:
            return get_json_result(
                data=False,
                message="Session does not belong to the requested agent.",
                code=RetCode.OPERATING_ERROR,
            )
        if not UserCanvasService.accessible(agent_id, tenant_id):
            return get_json_result(
                data=False,
                message="Only authorized users can access this agent session.",
                code=RetCode.OPERATING_ERROR,
            )
        workflow_session = getattr(conv, "source", "") == "workflow"
        if workflow_session:
            workflow_conv = conv.to_dict()

    if openai_compatible:
        # OpenAI-compatible mode uses a different wire format, keep it separate from regular agent events.
        messages = req.get("messages", [])
        if not messages:
            return get_data_error_result(message="You must provide at least one message.")
        question = next((m.get("content", "") for m in reversed(messages) if m.get("role") == "user"), "")
        stream = req.pop("stream", False)
        session_id = req.pop("session_id", req.get("id", "")) or req.get("metadata", {}).get("id", "")
        if stream:
            return _build_sse_response(
                completion_openai(
                    tenant_id,
                    agent_id,
                    question,
                    session_id=session_id,
                    stream=True,
                    **req,
                )
            )

        async for response in completion_openai(
            tenant_id,
            agent_id,
            question,
            session_id=session_id,
            stream=False,
            **req,
        ):
            return jsonify(response)
        return None

    if workflow_session:
        query = req.get("query", "") or req.get("question", "")
        files = req.get("files", [])
        inputs = req.get("inputs", {})
        runtime_user_id = req.get("user_id") or tenant_id
        user_id = str(runtime_user_id)
        custom_header = req.get("custom_header", "")

        _, cvs = await thread_pool_exec(UserCanvasService.get_by_id, agent_id)
        if not cvs:
            return get_data_error_result(message="canvas not found.")

        if not isinstance(workflow_conv.get("message"), list):
            workflow_conv["message"] = []
        if isinstance(workflow_conv.get("reference"), dict):
            if "chunks" in workflow_conv["reference"]:
                workflow_conv["reference"] = [workflow_conv["reference"]]
            else:
                workflow_conv["reference"] = [
                    value for _, value in sorted(workflow_conv["reference"].items(), key=lambda item: int(item[0]))
                ]
        elif not isinstance(workflow_conv.get("reference"), list):
            workflow_conv["reference"] = []
        workflow_conv["reference"] = [_normalize_agent_reference_entry(reference) for reference in workflow_conv["reference"]]
        turn_id = get_uuid()
        workflow_conv["message"].append(
            {
                "role": "user",
                "content": query,
                "id": turn_id,
                "files": files,
                "created_at": time.time(),
            }
        )
        await thread_pool_exec(API4ConversationService.update_by_id, session_id, workflow_conv)

        try:
            from agent.canvas import Canvas

            workflow_dsl = workflow_conv.get("dsl", {})
            if isinstance(workflow_dsl, str):
                dsl_str = workflow_dsl
            else:
                dsl_str = json.dumps(workflow_dsl, ensure_ascii=False)
            canvas = Canvas(dsl_str, str(tenant_id), canvas_id=agent_id, custom_header=custom_header)
        except Exception as exc:
            return server_error_response(exc)

        return await _run_workflow_session(
            tenant_id=tenant_id,
            agent_id=agent_id,
            workflow_conv=workflow_conv,
            canvas=canvas,
            query=query,
            files=files,
            inputs=inputs,
            user_id=user_id,
            session_id=session_id,
            custom_header=custom_header,
            canvas_title=getattr(cvs, "title", ""),
            canvas_category=getattr(cvs, "canvas_category", CanvasCategory.Agent),
            return_trace=bool(req.get("return_trace", False)),
            stream=req.get("stream", True),
            chat_template_kwargs=req.get("chat_template_kwargs"),
            external_context=req.get("external_context"),
            request_dataset_ids=request_dataset_ids,
        )

    if not session_id:
        if not UserCanvasService.accessible(agent_id, tenant_id):
            return get_json_result(
                data=False,
                message="Make sure you have permission to access the agent.",
                code=RetCode.OPERATING_ERROR,
            )

        # Keep the original workflow execution path, but assign a session_id so the
        # response shape stays closer to the older agent completion contract.
        query = req.get("query", "") or req.get("question", "")
        files = req.get("files", [])
        inputs = req.get("inputs", {})
        runtime_user_id = req.get("user_id") or tenant_id
        user_id = str(runtime_user_id)
        custom_header = req.get("custom_header", "")
        session_id = get_uuid()

        _, cvs = await thread_pool_exec(UserCanvasService.get_by_id, agent_id)
        if not cvs:
            return get_data_error_result(message="canvas not found.")

        replica_payload = CanvasReplicaService.load_for_run(
            canvas_id=agent_id,
            tenant_id=str(tenant_id),
            runtime_user_id=user_id,
        )
        if not replica_payload:
            try:
                replica_payload = CanvasReplicaService.bootstrap(
                    canvas_id=agent_id,
                    tenant_id=str(tenant_id),
                    runtime_user_id=user_id,
                    dsl=cvs.dsl,
                    canvas_category=getattr(cvs, "canvas_category", CanvasCategory.Agent),
                    title=getattr(cvs, "title", ""),
                )
            except ValueError as exc:
                return get_data_error_result(message=str(exc))
        if not replica_payload:
            return get_data_error_result(message="canvas replica not found, please fetch the agent first.")

        replica_dsl = replica_payload.get("dsl", {})
        canvas_title = replica_payload.get("title", "")
        canvas_category = replica_payload.get("canvas_category", CanvasCategory.Agent)
        dsl_str = json.dumps(replica_dsl, ensure_ascii=False)

        if cvs.canvas_category == CanvasCategory.DataFlow:
            from rag.flow.pipeline import Pipeline

            task_id = get_uuid()
            workflow_conv = {
                "id": session_id,
                "dialog_id": cvs.id,
                "user_id": user_id,
                "exp_user_id": user_id,
                "name": req.get("name", ""),
                "message": [
                    {
                        "role": "user",
                        "content": query,
                        "id": task_id,
                        "files": files,
                        "created_at": time.time(),
                    }
                ],
                "reference": [],
                "source": "workflow",
                "dsl": replica_dsl,
                "version_title": await thread_pool_exec(
                    UserCanvasVersionService.get_latest_version_title,
                    cvs.id,
                    release_mode=False,
                ),
            }
            await thread_pool_exec(API4ConversationService.save, **workflow_conv)
            Pipeline(
                dsl_str,
                tenant_id=str(tenant_id),
                doc_id=CANVAS_DEBUG_DOC_ID,
                task_id=task_id,
                flow_id=agent_id,
            )
            ok, error_message = await thread_pool_exec(
                queue_dataflow,
                user_id,
                agent_id,
                task_id,
                CANVAS_DEBUG_DOC_ID,
                files[0],
                0,
            )
            if not ok:
                return get_data_error_result(message=error_message)
            return get_json_result(data={"message_id": task_id, "session_id": session_id})

        try:
            from agent.canvas import Canvas

            canvas = Canvas(dsl_str, str(tenant_id), canvas_id=agent_id, custom_header=custom_header)
        except Exception as exc:
            return server_error_response(exc)
        turn_id = get_uuid()
        workflow_conv = {
            "id": session_id,
            "dialog_id": cvs.id,
            "user_id": user_id,
            "exp_user_id": user_id,
            "name": req.get("name", ""),
            "message": [
                {
                    "role": "user",
                    "content": query,
                    "id": turn_id,
                    "files": files,
                    "created_at": time.time(),
                }
            ],
            "reference": [],
            "source": "workflow",
            "dsl": replica_dsl,
            "version_title": await thread_pool_exec(
                UserCanvasVersionService.get_latest_version_title,
                cvs.id,
                release_mode=False,
            ),
        }
        workflow_conv["reference"] = [_normalize_agent_reference_entry(reference) for reference in workflow_conv["reference"]]
        await thread_pool_exec(API4ConversationService.save, **workflow_conv)
        return await _run_workflow_session(
            tenant_id=tenant_id,
            agent_id=agent_id,
            workflow_conv=workflow_conv,
            canvas=canvas,
            query=query,
            files=files,
            inputs=inputs,
            user_id=user_id,
            session_id=session_id,
            custom_header=custom_header,
            canvas_title=canvas_title,
            canvas_category=canvas_category,
            return_trace=bool(req.get("return_trace", False)),
            stream=req.get("stream", True),
            chat_template_kwargs=req.get("chat_template_kwargs"),
            external_context=req.get("external_context"),
            request_dataset_ids=request_dataset_ids,
        )

    return_trace = bool(req.get("return_trace", False))
    if req.get("stream", True):

        async def generate():
            async for ans in _iter_session_completion_events(tenant_id, agent_id, req, return_trace):
                yield "data:" + json.dumps(ans, ensure_ascii=False) + "\n\n"
            yield "data:[DONE]\n\n"

        return _build_sse_response(generate())

    full_content = ""
    reference = {}
    final_ans = {}
    trace_items = []
    structured_output = {}
    async for ans in _iter_session_completion_events(tenant_id, agent_id, req, return_trace):
        try:
            if ans["event"] == "message":
                full_content += ans["data"]["content"]
            if ans.get("data", {}).get("reference", None):
                reference.update(ans["data"]["reference"])
            if ans.get("event") == "node_finished":
                data = ans.get("data", {})
                node_out = data.get("outputs", {})
                component_id = data.get("component_id")
                if component_id is not None and "structured" in node_out:
                    structured_output[component_id] = copy.deepcopy(node_out["structured"])
                if return_trace:
                    trace_items.append(
                        {
                            "component_id": data.get("component_id"),
                            "trace": [copy.deepcopy(data)],
                        }
                    )
            final_ans = ans
        except Exception as exc:
            return get_result(data=f"**ERROR**: {str(exc)}")

    if not final_ans:
        return get_result(data={})

    if "data" not in final_ans or not isinstance(final_ans["data"], dict):
        final_ans["data"] = {}
    final_ans["data"]["content"] = full_content
    final_ans["data"]["reference"] = reference
    if structured_output:
        final_ans["data"]["structured"] = structured_output
    if return_trace and final_ans:
        final_ans["data"]["trace"] = trace_items
    return get_result(data=final_ans)


@manager.route("/agents/<agent_id>/webhook", methods=["POST", "GET", "PUT", "PATCH", "DELETE", "HEAD"])  # noqa: F821
@manager.route("/agents/<agent_id>/webhook/test",methods=["POST", "GET", "PUT", "PATCH", "DELETE", "HEAD"],)  # noqa: F821
async def webhook(agent_id: str):
    is_test = request.path.startswith(f"/api/v1/agents/{agent_id}/webhook/test")
    start_ts = time.time()

    # 1. Fetch canvas by agent_id
    exists, cvs = UserCanvasService.get_by_id(agent_id)
    if not exists:
        return get_data_error_result(code=RetCode.BAD_REQUEST,message="Canvas not found."),RetCode.BAD_REQUEST

    # 2. Check canvas category
    if cvs.canvas_category == CanvasCategory.DataFlow:
        return get_data_error_result(code=RetCode.BAD_REQUEST,message="Dataflow can not be triggered by webhook."),RetCode.BAD_REQUEST

    # 3. Load DSL from canvas
    dsl = getattr(cvs, "dsl", None)
    if not isinstance(dsl, dict):
        return get_data_error_result(code=RetCode.BAD_REQUEST,message="Invalid DSL format."),RetCode.BAD_REQUEST

    # 4. Check webhook configuration in DSL
    webhook_cfg = {}
    components = dsl.get("components", {})
    for k, _ in components.items():
        cpn_obj = components[k]["obj"]
        if cpn_obj["component_name"].lower() == "begin" and cpn_obj["params"]["mode"] == "Webhook":
            webhook_cfg = cpn_obj["params"]

    if not webhook_cfg:
        return get_data_error_result(code=RetCode.BAD_REQUEST,message="Webhook not configured for this agent."),RetCode.BAD_REQUEST

    # 5. Validate request method against webhook_cfg.methods
    allowed_methods = webhook_cfg.get("methods", [])
    request_method = request.method.upper()
    if allowed_methods and request_method not in allowed_methods:
        return get_data_error_result(
            code=RetCode.BAD_REQUEST,message=f"HTTP method '{request_method}' not allowed for this webhook."
        ),RetCode.BAD_REQUEST

    # 6. Validate webhook security
    async def validate_webhook_security(security_cfg: dict):
        """Validate webhook security rules based on security configuration."""

        if not security_cfg:
            return  # No security config → allowed by default

        # 1. Validate max body size
        await _validate_max_body_size(security_cfg)

        # 2. Validate IP whitelist
        _validate_ip_whitelist(security_cfg)

        # # 3. Validate rate limiting
        _validate_rate_limit(security_cfg)

        # 4. Validate authentication
        auth_type = security_cfg.get("auth_type", "none")

        if auth_type == "none":
            return

        if auth_type == "token":
            _validate_token_auth(security_cfg)

        elif auth_type == "basic":
            _validate_basic_auth(security_cfg)

        elif auth_type == "jwt":
            _validate_jwt_auth(security_cfg)

        else:
            raise Exception(f"Unsupported auth_type: {auth_type}")

    async def _validate_max_body_size(security_cfg):
        """Check request size does not exceed max_body_size."""
        max_size = security_cfg.get("max_body_size")
        if not max_size:
            return

        # Convert "10MB" → bytes
        units = {"kb": 1024, "mb": 1024**2}
        size_str = max_size.lower()

        for suffix, factor in units.items():
            if size_str.endswith(suffix):
                limit = int(size_str.replace(suffix, "")) * factor
                break
        else:
            raise Exception("Invalid max_body_size format")
        MAX_LIMIT = 10 * 1024 * 1024  # 10MB
        if limit > MAX_LIMIT:
            raise Exception("max_body_size exceeds maximum allowed size (10MB)")

        content_length = request.content_length or 0
        if content_length > limit:
            raise Exception(f"Request body too large: {content_length} > {limit}")

    def _validate_ip_whitelist(security_cfg):
        """Allow only IPs listed in ip_whitelist."""
        whitelist = security_cfg.get("ip_whitelist", [])
        if not whitelist:
            return

        client_ip = request.remote_addr


        for rule in whitelist:
            if "/" in rule:
                # CIDR notation
                if ipaddress.ip_address(client_ip) in ipaddress.ip_network(rule, strict=False):
                    return
            else:
                # Single IP
                if client_ip == rule:
                    return

        raise Exception(f"IP {client_ip} is not allowed by whitelist")

    def _validate_rate_limit(security_cfg):
        """Simple in-memory rate limiting."""
        rl = security_cfg.get("rate_limit")
        if not rl:
            return

        limit = int(rl.get("limit", 60))
        if limit <= 0:
            raise Exception("rate_limit.limit must be > 0")
        per = rl.get("per", "minute")

        window = {
            "second": 1,
            "minute": 60,
            "hour": 3600,
            "day": 86400,
        }.get(per)

        if not window:
            raise Exception(f"Invalid rate_limit.per: {per}")

        capacity = limit
        rate = limit / window
        cost = 1

        key = f"rl:tb:{agent_id}"
        now = time.time()

        try:
            from rag.utils.redis_conn import REDIS_CONN

            res = REDIS_CONN.lua_token_bucket(
                keys=[key],
                args=[capacity, rate, now, cost],
                client=REDIS_CONN.REDIS,
            )

            allowed = int(res[0])
            if allowed != 1:
                raise Exception("Too many requests (rate limit exceeded)")

        except Exception as e:
            raise Exception(f"Rate limit error: {e}")

    def _validate_token_auth(security_cfg):
        """Validate header-based token authentication."""
        token_cfg = security_cfg.get("token",{})
        header = token_cfg.get("token_header")
        token_value = token_cfg.get("token_value")

        provided = request.headers.get(header)
        if provided != token_value:
            raise Exception("Invalid token authentication")

    def _validate_basic_auth(security_cfg):
        """Validate HTTP Basic Auth credentials."""
        auth_cfg = security_cfg.get("basic_auth", {})
        username = auth_cfg.get("username")
        password = auth_cfg.get("password")

        auth = request.authorization
        if not auth or auth.username != username or auth.password != password:
            raise Exception("Invalid Basic Auth credentials")

    def _validate_jwt_auth(security_cfg):
        """Validate JWT token in Authorization header."""
        jwt_cfg = security_cfg.get("jwt", {})
        secret = jwt_cfg.get("secret")
        if not secret:
            raise Exception("JWT secret not configured")

        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            raise Exception("Missing Bearer token")

        token = auth_header[len("Bearer "):].strip()
        if not token:
            raise Exception("Empty Bearer token")

        alg = (jwt_cfg.get("algorithm") or "HS256").upper()

        decode_kwargs = {
            "key": secret,
            "algorithms": [alg],
        }
        options = {}
        if jwt_cfg.get("audience"):
            decode_kwargs["audience"] = jwt_cfg["audience"]
            options["verify_aud"] = True
        else:
            options["verify_aud"] = False

        if jwt_cfg.get("issuer"):
            decode_kwargs["issuer"] = jwt_cfg["issuer"]
            options["verify_iss"] = True
        else:
            options["verify_iss"] = False
        try:
            decoded = jwt.decode(
                token,
                options=options,
                **decode_kwargs,
            )
        except Exception as e:
            raise Exception(f"Invalid JWT: {str(e)}")

        raw_required_claims = jwt_cfg.get("required_claims", [])
        if isinstance(raw_required_claims, str):
            required_claims = [raw_required_claims]
        elif isinstance(raw_required_claims, (list, tuple, set)):
            required_claims = list(raw_required_claims)
        else:
            required_claims = []

        required_claims = [
            c for c in required_claims
            if isinstance(c, str) and c.strip()
        ]

        RESERVED_CLAIMS = {"exp", "sub", "aud", "iss", "nbf", "iat"}
        for claim in required_claims:
            if claim in RESERVED_CLAIMS:
                raise Exception(f"Reserved JWT claim cannot be required: {claim}")

        for claim in required_claims:
            if claim not in decoded:
                raise Exception(f"Missing JWT claim: {claim}")

        return decoded

    try:
        security_config=webhook_cfg.get("security", {})
        await validate_webhook_security(security_config)
    except Exception as e:
        return get_data_error_result(code=RetCode.BAD_REQUEST,message=str(e)),RetCode.BAD_REQUEST
    if not isinstance(cvs.dsl, str):
        dsl = json.dumps(cvs.dsl, ensure_ascii=False)
    try:
        from agent.canvas import Canvas

        canvas = Canvas(dsl, cvs.user_id, agent_id, canvas_id=agent_id)
    except Exception as e:
        resp=get_data_error_result(code=RetCode.BAD_REQUEST,message=str(e))
        resp.status_code = RetCode.BAD_REQUEST
        return resp

    # 7. Parse request body
    async def parse_webhook_request(content_type):
        """Parse request based on content-type and return structured data."""

        # 1. Query
        query_data = {k: v for k, v in request.args.items()}

        # 2. Headers
        header_data = {k: v for k, v in request.headers.items()}

        # 3. Body
        ctype = request.headers.get("Content-Type", "").split(";")[0].strip()
        if ctype and ctype != content_type:
            raise ValueError(
                f"Invalid Content-Type: expect '{content_type}', got '{ctype}'"
            )

        body_data: dict = {}

        try:
            if ctype == "application/json":
                body_data = await request.get_json() or {}

            elif ctype == "multipart/form-data":
                nonlocal canvas
                form = await request.form
                files = await request.files

                body_data = {}

                for key, value in form.items():
                    body_data[key] = value

                if len(files) > 10:
                    raise Exception("Too many uploaded files")
                for key, file in files.items():
                    desc = FileService.upload_info(
                        cvs.user_id,           # user
                        file,              # FileStorage
                        None                   # url (None for webhook)
                    )
                    file_parsed= await canvas.get_files_async([desc])
                    body_data[key] = file_parsed

            elif ctype == "application/x-www-form-urlencoded":
                form = await request.form
                body_data = dict(form)

            else:
                # text/plain / octet-stream / empty / unknown
                raw = await request.get_data()
                if raw:
                    try:
                        body_data = json.loads(raw.decode("utf-8"))
                    except Exception:
                        body_data = {}
                else:
                    body_data = {}

        except Exception:
            body_data = {}

        return {
            "query": query_data,
            "headers": header_data,
            "body": body_data,
            "content_type": ctype,
        }

    def extract_by_schema(data, schema, name="section"):
        """
        Extract only fields defined in schema.
        Required fields must exist.
        Optional fields default to type-based default values.
        Type validation included.
        """
        props = schema.get("properties", {})
        required = schema.get("required", [])

        extracted = {}

        for field, field_schema in props.items():
            field_type = field_schema.get("type")

            # 1. Required field missing
            if field in required and field not in data:
                raise Exception(f"{name} missing required field: {field}")

            # 2. Optional → default value
            if field not in data:
                extracted[field] = default_for_type(field_type)
                continue

            raw_value = data[field]

            # 3. Auto convert value
            try:
                value = auto_cast_value(raw_value, field_type)
            except Exception as e:
                raise Exception(f"{name}.{field} auto-cast failed: {str(e)}")

            # 4. Type validation
            if not validate_type(value, field_type):
                raise Exception(
                    f"{name}.{field} type mismatch: expected {field_type}, got {type(value).__name__}"
                )

            extracted[field] = value

        return extracted


    def default_for_type(t):
        """Return default value for the given schema type."""
        if t == "file":
            return []
        if t == "object":
            return {}
        if t == "boolean":
            return False
        if t == "number":
            return 0
        if t == "string":
            return ""
        if t and t.startswith("array"):
            return []
        if t == "null":
            return None
        return None

    def auto_cast_value(value, expected_type):
        """Convert string values into schema type when possible."""

        # Non-string values already good
        if not isinstance(value, str):
            return value

        v = value.strip()

        # Boolean
        if expected_type == "boolean":
            if v.lower() in ["true", "1"]:
                return True
            if v.lower() in ["false", "0"]:
                return False
            raise Exception(f"Cannot convert '{value}' to boolean")

        # Number
        if expected_type == "number":
            # integer
            if v.isdigit() or (v.startswith("-") and v[1:].isdigit()):
                return int(v)

            # float
            try:
                return float(v)
            except Exception:
                raise Exception(f"Cannot convert '{value}' to number")

        # Object
        if expected_type == "object":
            try:
                parsed = json.loads(v)
                if isinstance(parsed, dict):
                    return parsed
                else:
                    raise Exception("JSON is not an object")
            except Exception:
                raise Exception(f"Cannot convert '{value}' to object")

        # Array <T>
        if expected_type.startswith("array"):
            try:
                parsed = json.loads(v)
                if isinstance(parsed, list):
                    return parsed
                else:
                    raise Exception("JSON is not an array")
            except Exception:
                raise Exception(f"Cannot convert '{value}' to array")

        # String (accept original)
        if expected_type == "string":
            return value

        # File
        if expected_type == "file":
            return value
        # Default: do nothing
        return value


    def validate_type(value, t):
        """Validate value type against schema type t."""
        if t == "file":
            return isinstance(value, list)

        if t == "string":
            return isinstance(value, str)

        if t == "number":
            return isinstance(value, (int, float))

        if t == "boolean":
            return isinstance(value, bool)

        if t == "object":
            return isinstance(value, dict)

        # array<string> / array<number> / array<object>
        if t.startswith("array"):
            if not isinstance(value, list):
                return False

            if "<" in t and ">" in t:
                inner = t[t.find("<") + 1 : t.find(">")]

                # Check each element type
                for item in value:
                    if not validate_type(item, inner):
                        return False

            return True

        return True
    parsed = await parse_webhook_request(webhook_cfg.get("content_types"))
    SCHEMA = webhook_cfg.get("schema", {"query": {}, "headers": {}, "body": {}})

    # Extract strictly by schema
    try:
        query_clean  = extract_by_schema(parsed["query"],   SCHEMA.get("query", {}),  name="query")
        header_clean = extract_by_schema(parsed["headers"], SCHEMA.get("headers", {}), name="headers")
        body_clean   = extract_by_schema(parsed["body"],    SCHEMA.get("body", {}),    name="body")
    except Exception as e:
        return get_data_error_result(code=RetCode.BAD_REQUEST,message=str(e)),RetCode.BAD_REQUEST

    clean_request = {
        "query": query_clean,
        "headers": header_clean,
        "body": body_clean,
        "input": parsed
    }

    execution_mode = webhook_cfg.get("execution_mode", "Immediately")
    response_cfg = webhook_cfg.get("response", {})

    def append_webhook_trace(agent_id: str, start_ts: float,event: dict, ttl=600):
        from rag.utils.redis_conn import REDIS_CONN

        key = f"webhook-trace-{agent_id}-logs"

        raw = REDIS_CONN.get(key)
        obj = json.loads(raw) if raw else {"webhooks": {}}

        ws = obj["webhooks"].setdefault(
            str(start_ts),
            {"start_ts": start_ts, "events": []}
        )

        ws["events"].append({
            "ts": time.time(),
            **event
        })

        REDIS_CONN.set_obj(key, obj, ttl)

    if execution_mode == "Immediately":
        status = response_cfg.get("status", 200)
        try:
            status = int(status)
        except (TypeError, ValueError):
            return get_data_error_result(code=RetCode.BAD_REQUEST,message=str(f"Invalid response status code: {status}")),RetCode.BAD_REQUEST

        if not (200 <= status <= 399):
            return get_data_error_result(code=RetCode.BAD_REQUEST,message=str(f"Invalid response status code: {status}, must be between 200 and 399")),RetCode.BAD_REQUEST

        body_tpl = response_cfg.get("body_template", "")

        def parse_body(body: str):
            if not body:
                return None, "application/json"

            try:
                parsed = json.loads(body)
                return parsed, "application/json"
            except (json.JSONDecodeError, TypeError):
                return body, "text/plain"


        body, content_type = parse_body(body_tpl)
        resp = Response(
            json.dumps(body, ensure_ascii=False) if content_type == "application/json" else body,
            status=status,
            content_type=content_type,
        )

        async def background_run():
            try:
                async for ans in canvas.run(
                    query="",
                    user_id=cvs.user_id,
                    webhook_payload=clean_request
                ):
                    if is_test:
                        append_webhook_trace(agent_id, start_ts, ans)

                if is_test:
                    append_webhook_trace(
                        agent_id,
                        start_ts,
                        {
                            "event": "finished",
                            "elapsed_time": time.time() - start_ts,
                            "success": True,
                        }
                    )

                cvs.dsl = json.loads(str(canvas))
                UserCanvasService.update_by_id(cvs.user_id, cvs.to_dict())

            except Exception as e:
                logging.exception("Webhook background run failed")
                if is_test:
                    try:
                        append_webhook_trace(
                            agent_id,
                            start_ts,
                            {
                                "event": "error",
                                "message": str(e),
                                "error_type": type(e).__name__,
                            }
                        )
                        append_webhook_trace(
                            agent_id,
                            start_ts,
                            {
                                "event": "finished",
                                "elapsed_time": time.time() - start_ts,
                                "success": False,
                            }
                        )
                    except Exception:
                        logging.exception("Failed to append webhook trace")

        task = asyncio.create_task(background_run())
        if isinstance(task, asyncio.Task):
            _background_tasks.add(task)
            task.add_done_callback(_background_tasks.discard)
        return resp
    else:
        async def sse():
            nonlocal canvas
            contents: list[str] = []
            status = 200
            try:
                async for ans in canvas.run(
                    query="",
                    user_id=cvs.user_id,
                    webhook_payload=clean_request,
                ):
                    if ans["event"] == "message":
                        content = ans["data"]["content"]
                        if ans["data"].get("start_to_think", False):
                            content = "<think>"
                        elif ans["data"].get("end_to_think", False):
                            content = "</think>"
                        if content:
                            contents.append(content)
                    if ans["event"] == "message_end":
                        status = int(ans["data"].get("status", status))
                    if is_test:
                        append_webhook_trace(
                            agent_id,
                            start_ts,
                            ans
                        )
                if is_test:
                    append_webhook_trace(
                        agent_id,
                        start_ts,
                        {
                            "event": "finished",
                            "elapsed_time": time.time() - start_ts,
                            "success": True,
                        }
                    )
                final_content = "".join(contents)
                return {
                    "message": final_content,
                    "success": True,
                    "code":  status,
                }

            except Exception as e:
                if is_test:
                    append_webhook_trace(
                        agent_id,
                        start_ts,
                        {
                            "event": "error",
                            "message": str(e),
                            "error_type": type(e).__name__,
                        }
                    )
                    append_webhook_trace(
                        agent_id,
                        start_ts,
                        {
                            "event": "finished",
                            "elapsed_time": time.time() - start_ts,
                            "success": False,
                        }
                    )
                return {"code": 400, "message": str(e),"success":False}

        result = await sse()
        return Response(
            json.dumps(result),
            status=result["code"],
            mimetype="application/json",
        )


@manager.route("/agents/<agent_id>/webhook/logs", methods=["GET"])  # noqa: F821
@login_required
async def webhook_trace(agent_id: str):
    exists, cvs = UserCanvasService.get_by_id(agent_id)
    if not exists or str(cvs.user_id) != str(current_user.id):
        return get_data_error_result(
            message="Canvas not found.",
        )

    def encode_webhook_id(start_ts: str) -> str:
        WEBHOOK_ID_SECRET = "webhook_id_secret"
        sig = hmac.new(
            WEBHOOK_ID_SECRET.encode("utf-8"),
            start_ts.encode("utf-8"),
            hashlib.sha256,
        ).digest()
        return base64.urlsafe_b64encode(sig).decode("utf-8").rstrip("=")

    def decode_webhook_id(enc_id: str, webhooks: dict) -> str | None:
        for ts in webhooks.keys():
            if encode_webhook_id(ts) == enc_id:
                return ts
        return None
    since_ts = request.args.get("since_ts", type=float)
    webhook_id = request.args.get("webhook_id")

    key = f"webhook-trace-{agent_id}-logs"
    from rag.utils.redis_conn import REDIS_CONN

    raw = REDIS_CONN.get(key)

    if since_ts is None:
        now = time.time()
        return get_json_result(
            data={
                "webhook_id": None,
                "events": [],
                "next_since_ts": now,
                "finished": False,
            }
        )

    if not raw:
        return get_json_result(
            data={
                "webhook_id": None,
                "events": [],
                "next_since_ts": since_ts,
                "finished": False,
            }
        )

    obj = json.loads(raw)
    webhooks = obj.get("webhooks", {})

    if webhook_id is None:
        candidates = [
            float(k) for k in webhooks.keys() if float(k) > since_ts
        ]

        if not candidates:
            return get_json_result(
                data={
                    "webhook_id": None,
                    "events": [],
                    "next_since_ts": since_ts,
                    "finished": False,
                }
            )

        start_ts = min(candidates)
        real_id = str(start_ts)
        webhook_id = encode_webhook_id(real_id)

        return get_json_result(
            data={
                "webhook_id": webhook_id,
                "events": [],
                "next_since_ts": start_ts,
                "finished": False,
            }
        )

    real_id = decode_webhook_id(webhook_id, webhooks)

    if not real_id:
        return get_json_result(
            data={
                "webhook_id": webhook_id,
                "events": [],
                "next_since_ts": since_ts,
                "finished": True,
            }
        )

    ws = webhooks.get(str(real_id))
    events = ws.get("events", [])
    new_events = [e for e in events if e.get("ts", 0) > since_ts]

    next_ts = since_ts
    for e in new_events:
        next_ts = max(next_ts, e["ts"])

    finished = any(e.get("event") == "finished" for e in new_events)

    return get_json_result(
        data={
            "webhook_id": webhook_id,
            "events": new_events,
            "next_since_ts": next_ts,
            "finished": finished,
        }
    )

@manager.route("/agents/attachments/<attachment_id>/download", methods=["GET"])  # noqa: F821
@login_required
@add_tenant_id_to_kwargs
async def download_attachment(tenant_id=None, attachment_id=None):
    """Stream a document's underlying file to the requesting user.

    Mirrors the authorization model of the preview endpoint: the user must belong
    to the tenant that owns the document's knowledge base. A denial returns the
    same "Document not found!" response so the endpoint cannot be used to
    enumerate doc ids across tenants.
    """
    try:
        # Keep backward compatibility with older callers and unit tests that still
        # pass `attachment_id` instead of the route parameter name.
        ext = request.args.get("ext", "markdown")
        data = await thread_pool_exec(settings.STORAGE_IMPL.get, tenant_id, attachment_id)
        response = await make_response(data)
        content_type = CONTENT_TYPE_MAP.get(ext, f"application/{ext}")
        apply_safe_file_response_headers(response, content_type, ext)

        return response

    except Exception as e:
        return server_error_response(e)
