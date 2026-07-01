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

import re
from typing import Any

from agent.component.schema import (
    SCHEMA_TYPE_ANY,
    SCHEMA_TYPE_ARRAY,
    SCHEMA_TYPE_ARTIFACT,
    SCHEMA_TYPE_AUDIO_ASSET,
    SCHEMA_TYPE_AGENT_RUN_REF,
    SCHEMA_TYPE_BOOLEAN,
    SCHEMA_TYPE_CHART_SPEC,
    SCHEMA_TYPE_FILE_ASSET,
    SCHEMA_TYPE_JSON,
    SCHEMA_TYPE_MEETING_CONTEXT,
    SCHEMA_TYPE_NUMBER,
    SCHEMA_TYPE_SCORE_RESULT,
    SCHEMA_TYPE_SCORE_RUBRIC,
    SCHEMA_TYPE_SQL_RESULT,
    SCHEMA_TYPE_STRING,
    SCHEMA_TYPE_TABLE_DATA,
    SCHEMA_TYPE_TEXT_CHUNK,
    SCHEMA_TYPE_TEXT_DOCUMENT,
    normalize_schema_type,
)
from agent.sql_guard import prepare_readonly_sqls


class AgentValidationIssue:
    ERROR = "error"
    WARNING = "warning"

    def __init__(self, severity: str, code: str, message: str, component_id: str = "", component_name: str = ""):
        self.severity = severity
        self.code = code
        self.message = message
        self.component_id = component_id
        self.component_name = component_name

    def to_dict(self) -> dict[str, Any]:
        return {
            "severity": self.severity,
            "code": self.code,
            "message": self.message,
            "component_id": self.component_id,
            "component_name": self.component_name,
        }


class AgentValidationService:
    VARIABLE_REF_RE = re.compile(
        r"\{+ *([A-Za-z0-9:_-]+@[A-Za-z0-9_.-]+|sys\.[A-Za-z0-9_.]+|env\.[A-Za-z0-9_.]+) *\}+"
    )
    LLM_COMPONENTS = {"agent", "categorize", "browser", "rewritequestion", "agentwithtools"}
    OUTPUT_COMPONENTS = {"message", "agent", "docgenerator", "excelprocessor", "codeexec"}
    ARTIFACT_COMPONENTS = {"docgenerator", "codeexec", "chartrenderer", "artifactpackager"}
    FILE_PROCESSORS = {"fileparser", "excelprocessor", "parser", "tokenizer", "extractor", "docgenerator"}
    LLM_PROMPT_PARAMS = {"sys_prompt", "prompts", "prompt", "user_prompt", "context", "reasoning"}
    TEXT_INPUT_COMPONENTS = {
        "agent",
        "agentwithtools",
        "llm",
        "categorize",
        "rewritequestion",
        "docgenerator",
        "retrieval",
        "exesql",
    }
    NON_TEXT_PROMPT_TYPES = {
        SCHEMA_TYPE_ARTIFACT,
        SCHEMA_TYPE_FILE_ASSET,
        SCHEMA_TYPE_AUDIO_ASSET,
        "VoiceReply",
        "AgentRunRef",
        "MeetingContext",
    }
    DEFAULT_INPUT_SCHEMAS = {
        "agent": {
            "sys_prompt": SCHEMA_TYPE_STRING,
            "prompts": SCHEMA_TYPE_STRING,
            "user_prompt": SCHEMA_TYPE_STRING,
            "context": SCHEMA_TYPE_STRING,
            "reasoning": SCHEMA_TYPE_STRING,
            "visual_files_var": f"{SCHEMA_TYPE_ARRAY}<{SCHEMA_TYPE_FILE_ASSET}>",
        },
        "agentwithtools": {
            "sys_prompt": SCHEMA_TYPE_STRING,
            "prompts": SCHEMA_TYPE_STRING,
            "user_prompt": SCHEMA_TYPE_STRING,
            "context": SCHEMA_TYPE_STRING,
            "reasoning": SCHEMA_TYPE_STRING,
            "visual_files_var": f"{SCHEMA_TYPE_ARRAY}<{SCHEMA_TYPE_FILE_ASSET}>",
        },
        "llm": {
            "sys_prompt": SCHEMA_TYPE_STRING,
            "prompts": SCHEMA_TYPE_STRING,
            "visual_files_var": f"{SCHEMA_TYPE_ARRAY}<{SCHEMA_TYPE_FILE_ASSET}>",
        },
        "message": {"content": SCHEMA_TYPE_ANY},
        "goalintentclassifier": {"request": SCHEMA_TYPE_STRING, "context": SCHEMA_TYPE_JSON},
        "goalnormalizer": {"goal_intent": SCHEMA_TYPE_JSON},
        "taskcontextcollector": {
            "goal_intent": SCHEMA_TYPE_JSON,
            "root": SCHEMA_TYPE_STRING,
            "path": SCHEMA_TYPE_STRING,
            "query": SCHEMA_TYPE_STRING,
        },
        "recentartifactfinder": {
            "artifacts": f"{SCHEMA_TYPE_ARRAY}<{SCHEMA_TYPE_JSON}>",
            "query": SCHEMA_TYPE_STRING,
        },
        "relevantfileresolver": {
            "goal_intent": SCHEMA_TYPE_JSON,
            "root": SCHEMA_TYPE_STRING,
            "path": SCHEMA_TYPE_STRING,
            "query": SCHEMA_TYPE_STRING,
        },
        "taskplanner": {
            "goal_intent": SCHEMA_TYPE_JSON,
            "context_bundle": SCHEMA_TYPE_JSON,
        },
        "taskdecomposer": {
            "goal_intent": SCHEMA_TYPE_JSON,
            "context_bundle": SCHEMA_TYPE_JSON,
        },
        "atomictaskrefiner": {"task_plan": SCHEMA_TYPE_JSON},
        "preconditionchecker": {
            "task": SCHEMA_TYPE_JSON,
            "runtime_context": SCHEMA_TYPE_JSON,
            "root": SCHEMA_TYPE_STRING,
        },
        "dependencyresolver": {
            "task": SCHEMA_TYPE_JSON,
            "tasks": f"{SCHEMA_TYPE_ARRAY}<{SCHEMA_TYPE_JSON}>",
            "runtime_context": SCHEMA_TYPE_JSON,
        },
        "taskexecutor": {
            "task_id": SCHEMA_TYPE_STRING,
            "frame_id": SCHEMA_TYPE_STRING,
            "parent_frame_id": SCHEMA_TYPE_STRING,
            "runtime_context": SCHEMA_TYPE_JSON,
        },
        "taskframecontroller": {
            "action": SCHEMA_TYPE_STRING,
            "task_id": SCHEMA_TYPE_STRING,
            "child_task_id": SCHEMA_TYPE_STRING,
            "frame_id": SCHEMA_TYPE_STRING,
            "parent_frame_id": SCHEMA_TYPE_STRING,
            "local_context": SCHEMA_TYPE_JSON,
        },
        "taskresultverifier": {
            "task": SCHEMA_TYPE_JSON,
            "result": SCHEMA_TYPE_JSON,
            "runtime_context": SCHEMA_TYPE_JSON,
        },
        "taskreflection": {
            "task": SCHEMA_TYPE_JSON,
            "result": SCHEMA_TYPE_JSON,
            "verification": SCHEMA_TYPE_JSON,
        },
        "replandecider": {
            "task": SCHEMA_TYPE_JSON,
            "verification": SCHEMA_TYPE_JSON,
            "reflection": SCHEMA_TYPE_JSON,
        },
        "taskexecutionreportcomposer": {
            "goal_intent": SCHEMA_TYPE_JSON,
            "context_bundle": SCHEMA_TYPE_JSON,
            "task_plan": SCHEMA_TYPE_JSON,
            "precondition_result": SCHEMA_TYPE_JSON,
            "execution_result": SCHEMA_TYPE_JSON,
            "verification": SCHEMA_TYPE_JSON,
            "decision": SCHEMA_TYPE_JSON,
            "structure_advice": SCHEMA_TYPE_JSON,
        },
        "retrieval": {"query": SCHEMA_TYPE_STRING},
        "categorize": {"query": SCHEMA_TYPE_STRING, "category_description": SCHEMA_TYPE_STRING},
        "rewritequestion": {"query": SCHEMA_TYPE_STRING},
        "docgenerator": {"content": SCHEMA_TYPE_STRING},
        "fileparser": {
            "input_files": f"{SCHEMA_TYPE_ARRAY}<{SCHEMA_TYPE_FILE_ASSET}>",
            "query": SCHEMA_TYPE_STRING,
        },
        "workspacefilelist": {
            "root": SCHEMA_TYPE_STRING,
            "path": SCHEMA_TYPE_STRING,
            "extensions": f"{SCHEMA_TYPE_ARRAY}<{SCHEMA_TYPE_STRING}>",
            "pattern": SCHEMA_TYPE_STRING,
            "regex": SCHEMA_TYPE_STRING,
        },
        "workspacefilesearch": {
            "query": SCHEMA_TYPE_STRING,
            "root": SCHEMA_TYPE_STRING,
            "path": SCHEMA_TYPE_STRING,
            "extensions": f"{SCHEMA_TYPE_ARRAY}<{SCHEMA_TYPE_STRING}>",
            "pattern": SCHEMA_TYPE_STRING,
            "regex": SCHEMA_TYPE_STRING,
        },
        "workspacefileread": {
            "root": SCHEMA_TYPE_STRING,
            "path": SCHEMA_TYPE_STRING,
            "start_line": SCHEMA_TYPE_NUMBER,
            "end_line": SCHEMA_TYPE_NUMBER,
        },
        "workspacefilewrite": {
            "root": SCHEMA_TYPE_STRING,
            "path": SCHEMA_TYPE_STRING,
            "content": SCHEMA_TYPE_STRING,
            "mode": SCHEMA_TYPE_STRING,
            "expected_hash": SCHEMA_TYPE_STRING,
            "dry_run": SCHEMA_TYPE_BOOLEAN,
            "require_approval": SCHEMA_TYPE_BOOLEAN,
            "approval_id": SCHEMA_TYPE_STRING,
            "approved": SCHEMA_TYPE_BOOLEAN,
            "task_id": SCHEMA_TYPE_STRING,
            "reason": SCHEMA_TYPE_STRING,
        },
        "workspacepatchapply": {
            "root": SCHEMA_TYPE_STRING,
            "patch": SCHEMA_TYPE_ANY,
            "patch_format": SCHEMA_TYPE_STRING,
            "expected_hashes": SCHEMA_TYPE_JSON,
            "dry_run": SCHEMA_TYPE_BOOLEAN,
            "require_approval": SCHEMA_TYPE_BOOLEAN,
            "approval_id": SCHEMA_TYPE_STRING,
            "approved": SCHEMA_TYPE_BOOLEAN,
            "task_id": SCHEMA_TYPE_STRING,
            "reason": SCHEMA_TYPE_STRING,
        },
        "workspacetableread": {
            "root": SCHEMA_TYPE_STRING,
            "path": SCHEMA_TYPE_STRING,
            "sheet_name": SCHEMA_TYPE_STRING,
            "header_row": SCHEMA_TYPE_NUMBER,
            "start_row": SCHEMA_TYPE_NUMBER,
        },
        "documentnormalizer": {
            "root": SCHEMA_TYPE_STRING,
            "path": SCHEMA_TYPE_STRING,
            "max_bytes": SCHEMA_TYPE_NUMBER,
            "chunk_chars": SCHEMA_TYPE_NUMBER,
        },
        "documentstructureadvisor": {
            "outline": SCHEMA_TYPE_JSON,
            "paragraphs": f"{SCHEMA_TYPE_ARRAY}<{SCHEMA_TYPE_JSON}>",
            "new_content": SCHEMA_TYPE_STRING,
            "user_goal": SCHEMA_TYPE_STRING,
        },
        "contentplacementplanner": {
            "outline": SCHEMA_TYPE_JSON,
            "paragraphs": f"{SCHEMA_TYPE_ARRAY}<{SCHEMA_TYPE_JSON}>",
            "new_content": SCHEMA_TYPE_STRING,
            "user_goal": SCHEMA_TYPE_STRING,
        },
        "clauseextractor": {"document": SCHEMA_TYPE_TEXT_DOCUMENT, "content": SCHEMA_TYPE_STRING},
        "obligationextractor": {"document": SCHEMA_TYPE_TEXT_DOCUMENT, "content": SCHEMA_TYPE_STRING},
        "definitionextractor": {"document": SCHEMA_TYPE_TEXT_DOCUMENT, "content": SCHEMA_TYPE_STRING},
        "viewpointextractor": {"document": SCHEMA_TYPE_TEXT_DOCUMENT, "content": SCHEMA_TYPE_STRING},
        "riskpointextractor": {"document": SCHEMA_TYPE_TEXT_DOCUMENT, "content": SCHEMA_TYPE_STRING},
        "tablefactextractor": {"document": SCHEMA_TYPE_TEXT_DOCUMENT, "content": SCHEMA_TYPE_STRING},
        "documentdiff": {
            "left_document": SCHEMA_TYPE_TEXT_DOCUMENT,
            "right_document": SCHEMA_TYPE_TEXT_DOCUMENT,
        },
        "tablediff": {
            "left_document": SCHEMA_TYPE_TEXT_DOCUMENT,
            "right_document": SCHEMA_TYPE_TEXT_DOCUMENT,
        },
        "documentsemanticcomparer": {
            "left_items": f"{SCHEMA_TYPE_ARRAY}<{SCHEMA_TYPE_JSON}>",
            "right_items": f"{SCHEMA_TYPE_ARRAY}<{SCHEMA_TYPE_JSON}>",
        },
        "documentconflictdetector": {
            "standard_items": f"{SCHEMA_TYPE_ARRAY}<{SCHEMA_TYPE_JSON}>",
            "target_items": f"{SCHEMA_TYPE_ARRAY}<{SCHEMA_TYPE_JSON}>",
        },
        "documentcomparereportcomposer": {
            "title": SCHEMA_TYPE_STRING,
            "filename": SCHEMA_TYPE_STRING,
            "output_formats": SCHEMA_TYPE_ANY,
            "files": f"{SCHEMA_TYPE_ARRAY}<{SCHEMA_TYPE_JSON}>",
            "documents": SCHEMA_TYPE_ANY,
            "diff": SCHEMA_TYPE_JSON,
            "table_diff": SCHEMA_TYPE_JSON,
            "matches": f"{SCHEMA_TYPE_ARRAY}<{SCHEMA_TYPE_JSON}>",
            "conflicts": f"{SCHEMA_TYPE_ARRAY}<{SCHEMA_TYPE_JSON}>",
            "missing_requirements": f"{SCHEMA_TYPE_ARRAY}<{SCHEMA_TYPE_JSON}>",
            "risk_points": f"{SCHEMA_TYPE_ARRAY}<{SCHEMA_TYPE_JSON}>",
            "audit": SCHEMA_TYPE_JSON,
        },
        "citationformatter": {
            "references": f"{SCHEMA_TYPE_ARRAY}<{SCHEMA_TYPE_JSON}>",
            "content": SCHEMA_TYPE_STRING,
        },
        "contractclauseextractor": {
            "chunks": f"{SCHEMA_TYPE_ARRAY}<{SCHEMA_TYPE_TEXT_CHUNK}>",
            "content": SCHEMA_TYPE_STRING,
            "references": f"{SCHEMA_TYPE_ARRAY}<{SCHEMA_TYPE_JSON}>",
        },
        "compliancechecklistgenerator": {
            "standards": f"{SCHEMA_TYPE_ARRAY}<{SCHEMA_TYPE_JSON}>",
            "focus": SCHEMA_TYPE_STRING,
        },
        "clausematcher": {
            "checklist": f"{SCHEMA_TYPE_ARRAY}<{SCHEMA_TYPE_JSON}>",
            "clauses": f"{SCHEMA_TYPE_ARRAY}<{SCHEMA_TYPE_JSON}>",
        },
        "complianceverifier": {
            "checklist": f"{SCHEMA_TYPE_ARRAY}<{SCHEMA_TYPE_JSON}>",
            "matches": f"{SCHEMA_TYPE_ARRAY}<{SCHEMA_TYPE_JSON}>",
            "clauses": f"{SCHEMA_TYPE_ARRAY}<{SCHEMA_TYPE_JSON}>",
        },
        "riskscorer": {"verification_results": f"{SCHEMA_TYPE_ARRAY}<{SCHEMA_TYPE_JSON}>"},
        "compliancereportcomposer": {
            "scope": SCHEMA_TYPE_STRING,
            "verification_results": f"{SCHEMA_TYPE_ARRAY}<{SCHEMA_TYPE_JSON}>",
            "risk_summary": SCHEMA_TYPE_JSON,
            "references": f"{SCHEMA_TYPE_ARRAY}<{SCHEMA_TYPE_JSON}>",
        },
        "excelprocessor": {
            "input_files": f"{SCHEMA_TYPE_ARRAY}<{SCHEMA_TYPE_FILE_ASSET}>",
            "transform_data": SCHEMA_TYPE_TABLE_DATA,
            "aggregate_coefficient": SCHEMA_TYPE_NUMBER,
            "calculation_value": SCHEMA_TYPE_NUMBER,
            "calculation_coefficient": SCHEMA_TYPE_NUMBER,
        },
        "numbercalculate": {
            "value": SCHEMA_TYPE_NUMBER,
            "coefficient": SCHEMA_TYPE_NUMBER,
            "self_score": SCHEMA_TYPE_NUMBER,
            "self_weight": SCHEMA_TYPE_NUMBER,
            "external_score": SCHEMA_TYPE_NUMBER,
            "external_weight": SCHEMA_TYPE_NUMBER,
        },
        "chartspecbuilder": {"data": SCHEMA_TYPE_ANY},
        "chartrenderer": {
            "chart_spec": SCHEMA_TYPE_CHART_SPEC,
            "charts": f"{SCHEMA_TYPE_ARRAY}<{SCHEMA_TYPE_CHART_SPEC}>",
        },
        "artifactpackager": {
            "artifacts": f"{SCHEMA_TYPE_ARRAY}<{SCHEMA_TYPE_ARTIFACT}>",
            "manifest": SCHEMA_TYPE_JSON,
        },
        "prompttemplate": {"template": SCHEMA_TYPE_STRING, "variables": SCHEMA_TYPE_JSON},
        "pronunciationjudge": {"structured_result": SCHEMA_TYPE_JSON, "rubric": SCHEMA_TYPE_SCORE_RUBRIC},
        "summarynode": {"content": SCHEMA_TYPE_ANY},
        "reportcomposer": {"sections": SCHEMA_TYPE_JSON},
        "webhookinput": {"payload": SCHEMA_TYPE_JSON, "token": SCHEMA_TYPE_STRING},
        "externalscorereceiver": {"score_payload": SCHEMA_TYPE_JSON, "self_score": SCHEMA_TYPE_NUMBER},
        "humanreview": {"review_data": SCHEMA_TYPE_JSON},
        "manualapprove": {
            "task": SCHEMA_TYPE_JSON,
            "policy": SCHEMA_TYPE_JSON,
            "approved": SCHEMA_TYPE_BOOLEAN,
            "comment": SCHEMA_TYPE_STRING,
        },
        "exesql": {"sql": SCHEMA_TYPE_STRING},
        "scopeddbconnector": {},
        "safetableensure": {"db_ref": SCHEMA_TYPE_JSON},
        "saferecordinsert": {"table_ref": SCHEMA_TYPE_JSON, "record": SCHEMA_TYPE_JSON},
        "saferecordupdate": {"table_ref": SCHEMA_TYPE_JSON, "values": SCHEMA_TYPE_JSON, "filters": SCHEMA_TYPE_JSON},
        "saferecordquery": {"table_ref": SCHEMA_TYPE_JSON, "filters": SCHEMA_TYPE_JSON},
        "codeexec": {"script": SCHEMA_TYPE_STRING, "arguments": SCHEMA_TYPE_JSON},
        "ttsgenerate": {"text": SCHEMA_TYPE_STRING},
        "asrtranscribe": {"audio": SCHEMA_TYPE_AUDIO_ASSET},
        "voicereplyoutput": {"voice": "VoiceReply", "audio": SCHEMA_TYPE_AUDIO_ASSET},
        "meetingcontextinput": {
            "query": SCHEMA_TYPE_STRING,
            "shared_memory": f"{SCHEMA_TYPE_ARRAY}<{SCHEMA_TYPE_JSON}>",
            "agent_memory": f"{SCHEMA_TYPE_ARRAY}<{SCHEMA_TYPE_JSON}>",
        },
        "memoryinject": {"meeting_context": SCHEMA_TYPE_MEETING_CONTEXT, "content": SCHEMA_TYPE_STRING},
        "agentfanout": {
            "meeting_context": SCHEMA_TYPE_MEETING_CONTEXT,
            "content": SCHEMA_TYPE_STRING,
            "agents": f"{SCHEMA_TYPE_ARRAY}<{SCHEMA_TYPE_JSON}>",
            "files": f"{SCHEMA_TYPE_ARRAY}<{SCHEMA_TYPE_FILE_ASSET}>",
            "base_inputs": SCHEMA_TYPE_JSON,
        },
        "resultaggregator": {
            "runs": f"{SCHEMA_TYPE_ARRAY}<{SCHEMA_TYPE_AGENT_RUN_REF}>",
            "results": f"{SCHEMA_TYPE_ARRAY}<{SCHEMA_TYPE_JSON}>",
            "scores": f"{SCHEMA_TYPE_ARRAY}<{SCHEMA_TYPE_SCORE_RESULT}>",
            "citations": f"{SCHEMA_TYPE_ARRAY}<{SCHEMA_TYPE_JSON}>",
            "memory_delta": SCHEMA_TYPE_JSON,
        },
    }
    DEFAULT_OUTPUT_SCHEMAS = {
        "agent": {"content": SCHEMA_TYPE_STRING, "answer": SCHEMA_TYPE_STRING, "structured": SCHEMA_TYPE_JSON},
        "agentwithtools": {"content": SCHEMA_TYPE_STRING, "answer": SCHEMA_TYPE_STRING, "structured": SCHEMA_TYPE_JSON},
        "llm": {"content": SCHEMA_TYPE_STRING, "answer": SCHEMA_TYPE_STRING, "structured": SCHEMA_TYPE_JSON},
        "message": {"content": SCHEMA_TYPE_STRING, "downloads": f"{SCHEMA_TYPE_ARRAY}<{SCHEMA_TYPE_ARTIFACT}>"},
        "goalintentclassifier": {
            "goal_intent": SCHEMA_TYPE_JSON,
            "goal_type": SCHEMA_TYPE_STRING,
            "missing_inputs": f"{SCHEMA_TYPE_ARRAY}<{SCHEMA_TYPE_STRING}>",
            "requires_user_confirmation": SCHEMA_TYPE_BOOLEAN,
            "confidence": SCHEMA_TYPE_NUMBER,
        },
        "goalnormalizer": {
            "goal_intent": SCHEMA_TYPE_JSON,
            "goal_type": SCHEMA_TYPE_STRING,
            "unresolved": SCHEMA_TYPE_BOOLEAN,
        },
        "taskcontextcollector": {
            "context_bundle": SCHEMA_TYPE_JSON,
            "candidate_files": f"{SCHEMA_TYPE_ARRAY}<{SCHEMA_TYPE_JSON}>",
            "document_outlines": f"{SCHEMA_TYPE_ARRAY}<{SCHEMA_TYPE_JSON}>",
            "unresolved_context": f"{SCHEMA_TYPE_ARRAY}<{SCHEMA_TYPE_JSON}>",
            "summary": SCHEMA_TYPE_JSON,
        },
        "recentartifactfinder": {"candidate_artifacts": f"{SCHEMA_TYPE_ARRAY}<{SCHEMA_TYPE_JSON}>"},
        "relevantfileresolver": {
            "candidate_files": f"{SCHEMA_TYPE_ARRAY}<{SCHEMA_TYPE_JSON}>",
            "query_terms": f"{SCHEMA_TYPE_ARRAY}<{SCHEMA_TYPE_STRING}>",
            "unresolved_context": f"{SCHEMA_TYPE_ARRAY}<{SCHEMA_TYPE_JSON}>",
        },
        "taskplanner": {
            "task_plan": SCHEMA_TYPE_JSON,
            "tasks": f"{SCHEMA_TYPE_ARRAY}<{SCHEMA_TYPE_JSON}>",
            "relations": f"{SCHEMA_TYPE_ARRAY}<{SCHEMA_TYPE_JSON}>",
            "validation": SCHEMA_TYPE_JSON,
            "atomic_tasks": f"{SCHEMA_TYPE_ARRAY}<{SCHEMA_TYPE_JSON}>",
        },
        "taskdecomposer": {
            "root_task": SCHEMA_TYPE_JSON,
            "tasks": f"{SCHEMA_TYPE_ARRAY}<{SCHEMA_TYPE_JSON}>",
            "relations": f"{SCHEMA_TYPE_ARRAY}<{SCHEMA_TYPE_JSON}>",
            "tree": SCHEMA_TYPE_JSON,
            "parallel_groups": f"{SCHEMA_TYPE_ARRAY}<{SCHEMA_TYPE_JSON}>",
        },
        "atomictaskrefiner": {
            "task_plan": SCHEMA_TYPE_JSON,
            "atomic_tasks": f"{SCHEMA_TYPE_ARRAY}<{SCHEMA_TYPE_JSON}>",
            "validation": SCHEMA_TYPE_JSON,
        },
        "preconditionchecker": {
            "precondition_result": SCHEMA_TYPE_JSON,
            "ready": SCHEMA_TYPE_BOOLEAN,
            "next_status": SCHEMA_TYPE_STRING,
            "condition_results": f"{SCHEMA_TYPE_ARRAY}<{SCHEMA_TYPE_JSON}>",
            "repair_tasks": f"{SCHEMA_TYPE_ARRAY}<{SCHEMA_TYPE_JSON}>",
        },
        "dependencyresolver": {
            "dependency_result": SCHEMA_TYPE_JSON,
            "ready": SCHEMA_TYPE_BOOLEAN,
            "dependencies": f"{SCHEMA_TYPE_ARRAY}<{SCHEMA_TYPE_JSON}>",
            "blocked_by": f"{SCHEMA_TYPE_ARRAY}<{SCHEMA_TYPE_JSON}>",
            "repair_tasks": f"{SCHEMA_TYPE_ARRAY}<{SCHEMA_TYPE_JSON}>",
        },
        "taskexecutor": {
            "execution_result": SCHEMA_TYPE_JSON,
            "result": SCHEMA_TYPE_JSON,
            "status": SCHEMA_TYPE_STRING,
            "ok": SCHEMA_TYPE_BOOLEAN,
        },
        "taskframecontroller": {
            "frame_result": SCHEMA_TYPE_JSON,
            "frame": SCHEMA_TYPE_JSON,
            "status": SCHEMA_TYPE_STRING,
            "continuation_pointer": SCHEMA_TYPE_STRING,
            "local_context": SCHEMA_TYPE_JSON,
        },
        "taskresultverifier": {
            "verification": SCHEMA_TYPE_JSON,
            "ok": SCHEMA_TYPE_BOOLEAN,
            "failed_checks": f"{SCHEMA_TYPE_ARRAY}<{SCHEMA_TYPE_JSON}>",
            "next_action": SCHEMA_TYPE_STRING,
            "repair_tasks": f"{SCHEMA_TYPE_ARRAY}<{SCHEMA_TYPE_JSON}>",
        },
        "taskreflection": {
            "reflection": SCHEMA_TYPE_JSON,
            "root_causes": f"{SCHEMA_TYPE_ARRAY}<{SCHEMA_TYPE_STRING}>",
            "retryable": SCHEMA_TYPE_BOOLEAN,
        },
        "replandecider": {
            "decision": SCHEMA_TYPE_JSON,
            "next_action": SCHEMA_TYPE_STRING,
            "repair_tasks": f"{SCHEMA_TYPE_ARRAY}<{SCHEMA_TYPE_JSON}>",
        },
        "taskexecutionreportcomposer": {
            "report": SCHEMA_TYPE_JSON,
            "markdown": SCHEMA_TYPE_STRING,
            "audit": SCHEMA_TYPE_JSON,
        },
        "retrieval": {"formalized_content": SCHEMA_TYPE_STRING, "json": f"{SCHEMA_TYPE_ARRAY}<{SCHEMA_TYPE_JSON}>"},
        "categorize": {"category_name": SCHEMA_TYPE_STRING},
        "rewritequestion": {"question": SCHEMA_TYPE_STRING, "content": SCHEMA_TYPE_STRING},
        "docgenerator": {
            "doc_id": SCHEMA_TYPE_STRING,
            "filename": SCHEMA_TYPE_STRING,
            "mime_type": SCHEMA_TYPE_STRING,
            "size": SCHEMA_TYPE_NUMBER,
            "download": SCHEMA_TYPE_STRING,
            "downloads": f"{SCHEMA_TYPE_ARRAY}<{SCHEMA_TYPE_ARTIFACT}>",
            "attachment": SCHEMA_TYPE_ARTIFACT,
        },
        "fileparser": {
            "chunks": f"{SCHEMA_TYPE_ARRAY}<{SCHEMA_TYPE_TEXT_CHUNK}>",
            "matches": f"{SCHEMA_TYPE_ARRAY}<{SCHEMA_TYPE_TEXT_CHUNK}>",
            "references": f"{SCHEMA_TYPE_ARRAY}<{SCHEMA_TYPE_JSON}>",
            "file_info": f"{SCHEMA_TYPE_ARRAY}<{SCHEMA_TYPE_JSON}>",
            "content": SCHEMA_TYPE_STRING,
            "summary": SCHEMA_TYPE_STRING,
        },
        "workspacefilelist": {
            "files": f"{SCHEMA_TYPE_ARRAY}<{SCHEMA_TYPE_JSON}>",
            "count": SCHEMA_TYPE_NUMBER,
            "truncated": SCHEMA_TYPE_BOOLEAN,
            "audit": SCHEMA_TYPE_JSON,
        },
        "workspacefilesearch": {
            "files": f"{SCHEMA_TYPE_ARRAY}<{SCHEMA_TYPE_JSON}>",
            "count": SCHEMA_TYPE_NUMBER,
            "truncated": SCHEMA_TYPE_BOOLEAN,
            "audit": SCHEMA_TYPE_JSON,
        },
        "workspacefileread": {
            "file": SCHEMA_TYPE_JSON,
            "content": SCHEMA_TYPE_STRING,
            "lines": f"{SCHEMA_TYPE_ARRAY}<{SCHEMA_TYPE_JSON}>",
            "line_count": SCHEMA_TYPE_NUMBER,
            "truncated": SCHEMA_TYPE_BOOLEAN,
            "source_ref": SCHEMA_TYPE_STRING,
            "audit": SCHEMA_TYPE_JSON,
        },
        "workspacefilewrite": {
            "write": SCHEMA_TYPE_JSON,
            "file": SCHEMA_TYPE_JSON,
            "diff": SCHEMA_TYPE_STRING,
            "changed": SCHEMA_TYPE_BOOLEAN,
            "dry_run": SCHEMA_TYPE_BOOLEAN,
            "approval": SCHEMA_TYPE_JSON,
            "audit": SCHEMA_TYPE_JSON,
        },
        "workspacepatchapply": {
            "patch_result": SCHEMA_TYPE_JSON,
            "affected_files": f"{SCHEMA_TYPE_ARRAY}<{SCHEMA_TYPE_JSON}>",
            "diff": SCHEMA_TYPE_STRING,
            "conflicts": f"{SCHEMA_TYPE_ARRAY}<{SCHEMA_TYPE_JSON}>",
            "can_apply": SCHEMA_TYPE_BOOLEAN,
            "rollback_token": SCHEMA_TYPE_STRING,
            "dry_run": SCHEMA_TYPE_BOOLEAN,
            "approval": SCHEMA_TYPE_JSON,
            "audit": SCHEMA_TYPE_JSON,
        },
        "workspacetableread": {
            "table": SCHEMA_TYPE_TABLE_DATA,
            "headers": f"{SCHEMA_TYPE_ARRAY}<{SCHEMA_TYPE_STRING}>",
            "rows": f"{SCHEMA_TYPE_ARRAY}<{SCHEMA_TYPE_JSON}>",
            "file": SCHEMA_TYPE_JSON,
            "truncated": SCHEMA_TYPE_BOOLEAN,
            "source_ref": SCHEMA_TYPE_STRING,
            "audit": SCHEMA_TYPE_JSON,
        },
        "documentnormalizer": {
            "document": SCHEMA_TYPE_TEXT_DOCUMENT,
            "lines": f"{SCHEMA_TYPE_ARRAY}<{SCHEMA_TYPE_JSON}>",
            "paragraphs": f"{SCHEMA_TYPE_ARRAY}<{SCHEMA_TYPE_JSON}>",
            "sections": f"{SCHEMA_TYPE_ARRAY}<{SCHEMA_TYPE_JSON}>",
            "tables": f"{SCHEMA_TYPE_ARRAY}<{SCHEMA_TYPE_JSON}>",
            "chunks": f"{SCHEMA_TYPE_ARRAY}<{SCHEMA_TYPE_TEXT_CHUNK}>",
            "metadata": SCHEMA_TYPE_JSON,
            "audit": SCHEMA_TYPE_JSON,
        },
        "documentstructureadvisor": {
            "structure_advice": SCHEMA_TYPE_JSON,
            "content_categories": f"{SCHEMA_TYPE_ARRAY}<{SCHEMA_TYPE_JSON}>",
            "proposed_outline": f"{SCHEMA_TYPE_ARRAY}<{SCHEMA_TYPE_JSON}>",
            "insertion_points": f"{SCHEMA_TYPE_ARRAY}<{SCHEMA_TYPE_JSON}>",
            "modification_plan": f"{SCHEMA_TYPE_ARRAY}<{SCHEMA_TYPE_JSON}>",
            "user_review_needed": SCHEMA_TYPE_BOOLEAN,
        },
        "contentplacementplanner": {
            "placement_plan": SCHEMA_TYPE_JSON,
            "content_categories": f"{SCHEMA_TYPE_ARRAY}<{SCHEMA_TYPE_JSON}>",
            "insertion_points": f"{SCHEMA_TYPE_ARRAY}<{SCHEMA_TYPE_JSON}>",
            "merge_strategy": SCHEMA_TYPE_JSON,
            "risk_notes": f"{SCHEMA_TYPE_ARRAY}<{SCHEMA_TYPE_JSON}>",
        },
        "clauseextractor": {
            "items": f"{SCHEMA_TYPE_ARRAY}<{SCHEMA_TYPE_JSON}>",
            "clauses": f"{SCHEMA_TYPE_ARRAY}<{SCHEMA_TYPE_JSON}>",
            "references": f"{SCHEMA_TYPE_ARRAY}<{SCHEMA_TYPE_JSON}>",
            "summary": SCHEMA_TYPE_STRING,
        },
        "obligationextractor": {
            "items": f"{SCHEMA_TYPE_ARRAY}<{SCHEMA_TYPE_JSON}>",
            "obligations": f"{SCHEMA_TYPE_ARRAY}<{SCHEMA_TYPE_JSON}>",
            "references": f"{SCHEMA_TYPE_ARRAY}<{SCHEMA_TYPE_JSON}>",
            "summary": SCHEMA_TYPE_STRING,
        },
        "definitionextractor": {
            "items": f"{SCHEMA_TYPE_ARRAY}<{SCHEMA_TYPE_JSON}>",
            "definitions": f"{SCHEMA_TYPE_ARRAY}<{SCHEMA_TYPE_JSON}>",
            "references": f"{SCHEMA_TYPE_ARRAY}<{SCHEMA_TYPE_JSON}>",
            "summary": SCHEMA_TYPE_STRING,
        },
        "viewpointextractor": {
            "items": f"{SCHEMA_TYPE_ARRAY}<{SCHEMA_TYPE_JSON}>",
            "viewpoints": f"{SCHEMA_TYPE_ARRAY}<{SCHEMA_TYPE_JSON}>",
            "references": f"{SCHEMA_TYPE_ARRAY}<{SCHEMA_TYPE_JSON}>",
            "summary": SCHEMA_TYPE_STRING,
        },
        "riskpointextractor": {
            "items": f"{SCHEMA_TYPE_ARRAY}<{SCHEMA_TYPE_JSON}>",
            "risk_points": f"{SCHEMA_TYPE_ARRAY}<{SCHEMA_TYPE_JSON}>",
            "references": f"{SCHEMA_TYPE_ARRAY}<{SCHEMA_TYPE_JSON}>",
            "summary": SCHEMA_TYPE_STRING,
        },
        "tablefactextractor": {
            "items": f"{SCHEMA_TYPE_ARRAY}<{SCHEMA_TYPE_JSON}>",
            "table_facts": f"{SCHEMA_TYPE_ARRAY}<{SCHEMA_TYPE_JSON}>",
            "references": f"{SCHEMA_TYPE_ARRAY}<{SCHEMA_TYPE_JSON}>",
            "summary": SCHEMA_TYPE_STRING,
        },
        "documentdiff": {
            "diff": SCHEMA_TYPE_JSON,
            "hunks": f"{SCHEMA_TYPE_ARRAY}<{SCHEMA_TYPE_JSON}>",
            "summary": SCHEMA_TYPE_JSON,
        },
        "tablediff": {
            "table_diff": SCHEMA_TYPE_JSON,
            "hunks": f"{SCHEMA_TYPE_ARRAY}<{SCHEMA_TYPE_JSON}>",
            "schema_changes": SCHEMA_TYPE_JSON,
            "summary": SCHEMA_TYPE_JSON,
        },
        "documentsemanticcomparer": {
            "matches": f"{SCHEMA_TYPE_ARRAY}<{SCHEMA_TYPE_JSON}>",
            "missing_in_left": f"{SCHEMA_TYPE_ARRAY}<{SCHEMA_TYPE_JSON}>",
            "missing_in_right": f"{SCHEMA_TYPE_ARRAY}<{SCHEMA_TYPE_JSON}>",
            "summary": SCHEMA_TYPE_JSON,
        },
        "documentconflictdetector": {
            "conflicts": f"{SCHEMA_TYPE_ARRAY}<{SCHEMA_TYPE_JSON}>",
            "missing_requirements": f"{SCHEMA_TYPE_ARRAY}<{SCHEMA_TYPE_JSON}>",
            "matches": f"{SCHEMA_TYPE_ARRAY}<{SCHEMA_TYPE_JSON}>",
            "summary": SCHEMA_TYPE_JSON,
        },
        "documentcomparereportcomposer": {
            "report": SCHEMA_TYPE_JSON,
            "markdown": SCHEMA_TYPE_STRING,
            "json": SCHEMA_TYPE_JSON,
            "downloads": f"{SCHEMA_TYPE_ARRAY}<{SCHEMA_TYPE_ARTIFACT}>",
            "attachments": f"{SCHEMA_TYPE_ARRAY}<{SCHEMA_TYPE_ARTIFACT}>",
            "audit": SCHEMA_TYPE_JSON,
            "summary": SCHEMA_TYPE_STRING,
        },
        "citationformatter": {
            "citations": f"{SCHEMA_TYPE_ARRAY}<{SCHEMA_TYPE_JSON}>",
            "references": f"{SCHEMA_TYPE_ARRAY}<{SCHEMA_TYPE_JSON}>",
            "markdown": SCHEMA_TYPE_STRING,
            "content": SCHEMA_TYPE_STRING,
        },
        "contractclauseextractor": {
            "clause_tree": SCHEMA_TYPE_JSON,
            "clauses": f"{SCHEMA_TYPE_ARRAY}<{SCHEMA_TYPE_JSON}>",
            "entities": SCHEMA_TYPE_JSON,
            "references": f"{SCHEMA_TYPE_ARRAY}<{SCHEMA_TYPE_JSON}>",
            "summary": SCHEMA_TYPE_STRING,
        },
        "compliancechecklistgenerator": {
            "checklist": f"{SCHEMA_TYPE_ARRAY}<{SCHEMA_TYPE_JSON}>",
            "references": f"{SCHEMA_TYPE_ARRAY}<{SCHEMA_TYPE_JSON}>",
            "summary": SCHEMA_TYPE_STRING,
        },
        "clausematcher": {
            "matches": f"{SCHEMA_TYPE_ARRAY}<{SCHEMA_TYPE_JSON}>",
            "summary": SCHEMA_TYPE_STRING,
        },
        "complianceverifier": {
            "verification_results": f"{SCHEMA_TYPE_ARRAY}<{SCHEMA_TYPE_JSON}>",
            "summary": SCHEMA_TYPE_STRING,
            "references": f"{SCHEMA_TYPE_ARRAY}<{SCHEMA_TYPE_JSON}>",
        },
        "riskscorer": {
            "risk_items": f"{SCHEMA_TYPE_ARRAY}<{SCHEMA_TYPE_JSON}>",
            "risk_summary": SCHEMA_TYPE_JSON,
            "overall_risk_level": SCHEMA_TYPE_STRING,
        },
        "compliancereportcomposer": {
            "markdown": SCHEMA_TYPE_STRING,
            "summary": SCHEMA_TYPE_STRING,
            "tables": SCHEMA_TYPE_JSON,
            "references": f"{SCHEMA_TYPE_ARRAY}<{SCHEMA_TYPE_JSON}>",
        },
        "excelprocessor": {
            "data": SCHEMA_TYPE_TABLE_DATA,
            "summary": SCHEMA_TYPE_STRING,
            "markdown": SCHEMA_TYPE_STRING,
            "aggregate": SCHEMA_TYPE_JSON,
            "result": SCHEMA_TYPE_NUMBER,
            "downloads": f"{SCHEMA_TYPE_ARRAY}<{SCHEMA_TYPE_ARTIFACT}>",
            "attachment": SCHEMA_TYPE_ARTIFACT,
        },
        "numbercalculate": {
            "result": SCHEMA_TYPE_NUMBER,
            "breakdown": SCHEMA_TYPE_JSON,
            "summary": SCHEMA_TYPE_STRING,
        },
        "chartspecbuilder": {
            "chart_spec": SCHEMA_TYPE_CHART_SPEC,
            "charts": f"{SCHEMA_TYPE_ARRAY}<{SCHEMA_TYPE_CHART_SPEC}>",
            "summary": SCHEMA_TYPE_STRING,
        },
        "chartrenderer": {
            "chart_artifact": SCHEMA_TYPE_ARTIFACT,
            "downloads": f"{SCHEMA_TYPE_ARRAY}<{SCHEMA_TYPE_ARTIFACT}>",
            "markdown": SCHEMA_TYPE_STRING,
            "html": SCHEMA_TYPE_STRING,
        },
        "artifactpackager": {
            "package": SCHEMA_TYPE_ARTIFACT,
            "downloads": f"{SCHEMA_TYPE_ARRAY}<{SCHEMA_TYPE_ARTIFACT}>",
            "manifest": SCHEMA_TYPE_JSON,
            "markdown": SCHEMA_TYPE_STRING,
        },
        "prompttemplate": {"prompt": SCHEMA_TYPE_STRING},
        "scorerubricbuilder": {
            "rubric": SCHEMA_TYPE_SCORE_RUBRIC,
            "dimensions": f"{SCHEMA_TYPE_ARRAY}<{SCHEMA_TYPE_JSON}>",
            "summary": SCHEMA_TYPE_STRING,
        },
        "pronunciationjudge": {
            "score_result": SCHEMA_TYPE_SCORE_RESULT,
            "self_score": SCHEMA_TYPE_NUMBER,
            "rubric_scores": SCHEMA_TYPE_JSON,
            "feedback": SCHEMA_TYPE_STRING,
            "valid": SCHEMA_TYPE_BOOLEAN,
        },
        "summarynode": {"summary": SCHEMA_TYPE_STRING},
        "reportcomposer": {"markdown": SCHEMA_TYPE_STRING},
        "webhookinput": {"event": SCHEMA_TYPE_JSON, "verified": SCHEMA_TYPE_BOOLEAN},
        "externalscorereceiver": {
            "score_result": SCHEMA_TYPE_SCORE_RESULT,
            "external_score": SCHEMA_TYPE_NUMBER,
            "rubric_scores": SCHEMA_TYPE_JSON,
            "source": SCHEMA_TYPE_STRING,
        },
        "humanreview": {"review": SCHEMA_TYPE_JSON},
        "manualapprove": {"approved": SCHEMA_TYPE_BOOLEAN, "review": SCHEMA_TYPE_JSON},
        "exesql": {
            "formalized_content": SCHEMA_TYPE_STRING,
            "json": f"{SCHEMA_TYPE_ARRAY}<{SCHEMA_TYPE_JSON}>",
            "sql_result": SCHEMA_TYPE_SQL_RESULT,
            "row_count": SCHEMA_TYPE_NUMBER,
            "truncated": SCHEMA_TYPE_BOOLEAN,
        },
        "scopeddbconnector": {"db_ref": SCHEMA_TYPE_JSON},
        "safetableensure": {"table_ref": SCHEMA_TYPE_JSON, "table_name": SCHEMA_TYPE_STRING},
        "saferecordinsert": {"row": SCHEMA_TYPE_JSON, "row_count": SCHEMA_TYPE_NUMBER},
        "saferecordupdate": {"row_count": SCHEMA_TYPE_NUMBER},
        "saferecordquery": {
            "sql_result": SCHEMA_TYPE_SQL_RESULT,
            "data": SCHEMA_TYPE_TABLE_DATA,
            "row_count": SCHEMA_TYPE_NUMBER,
        },
        "codeexec": {
            "result": SCHEMA_TYPE_JSON,
            "content": SCHEMA_TYPE_STRING,
            "attachments": f"{SCHEMA_TYPE_ARRAY}<{SCHEMA_TYPE_STRING}>",
        },
        "ttsgenerate": {"audio": SCHEMA_TYPE_AUDIO_ASSET, "voice": "VoiceReply", "duration": SCHEMA_TYPE_NUMBER, "engine": SCHEMA_TYPE_STRING},
        "asrtranscribe": {
            "text": SCHEMA_TYPE_STRING,
            "transcript": SCHEMA_TYPE_STRING,
            "confidence": SCHEMA_TYPE_NUMBER,
            "language": SCHEMA_TYPE_STRING,
            "duration": SCHEMA_TYPE_NUMBER,
            "engine": SCHEMA_TYPE_STRING,
        },
        "audioinput": {"audio": SCHEMA_TYPE_AUDIO_ASSET},
        "voicereplyoutput": {"voice": "VoiceReply", "audio": SCHEMA_TYPE_AUDIO_ASSET},
        "meetingcontextinput": {"meeting_context": SCHEMA_TYPE_MEETING_CONTEXT, "prompt": SCHEMA_TYPE_STRING},
        "memoryinject": {
            "meeting_context": SCHEMA_TYPE_MEETING_CONTEXT,
            "content": SCHEMA_TYPE_STRING,
            "memory_delta": SCHEMA_TYPE_JSON,
        },
        "agentfanout": {
            "runs": f"{SCHEMA_TYPE_ARRAY}<{SCHEMA_TYPE_AGENT_RUN_REF}>",
            "dispatch": SCHEMA_TYPE_JSON,
            "meeting_context": SCHEMA_TYPE_MEETING_CONTEXT,
        },
        "resultaggregator": {
            "reply_text": SCHEMA_TYPE_STRING,
            "memory_delta": SCHEMA_TYPE_JSON,
            "citations": f"{SCHEMA_TYPE_ARRAY}<{SCHEMA_TYPE_JSON}>",
            "score_result": SCHEMA_TYPE_SCORE_RESULT,
            "run_id": SCHEMA_TYPE_STRING,
            "report": SCHEMA_TYPE_STRING,
        },
    }

    @classmethod
    def validate_for_publish(cls, dsl: dict[str, Any] | None) -> dict[str, Any]:
        issues = cls.validate(dsl)
        return {
            "ok": not any(item["severity"] == AgentValidationIssue.ERROR for item in issues),
            "errors": [item for item in issues if item["severity"] == AgentValidationIssue.ERROR],
            "warnings": [item for item in issues if item["severity"] == AgentValidationIssue.WARNING],
            "issues": issues,
        }

    @classmethod
    def validate(cls, dsl: dict[str, Any] | None) -> list[dict[str, Any]]:
        validator = cls(dsl)
        return validator.run()

    def __init__(self, dsl: dict[str, Any] | None):
        self.dsl = dsl if isinstance(dsl, dict) else {}
        self.components = self.dsl.get("components") if isinstance(self.dsl.get("components"), dict) else {}
        self.issues: list[AgentValidationIssue] = []

    def run(self) -> list[dict[str, Any]]:
        self._validate_shape()
        if not self.components:
            return [item.to_dict() for item in self.issues]

        self._validate_begin()
        self._validate_edges()
        self._validate_connectivity()
        self._validate_required_params()
        self._validate_variable_refs()
        self._validate_type_compatibility()
        self._validate_sql()
        self._validate_file_flow()
        self._validate_artifact_visibility()
        return [item.to_dict() for item in self.issues]

    def _component_name(self, component_id: str) -> str:
        component = self.components.get(component_id) or {}
        obj = component.get("obj") or {}
        return str(obj.get("component_name") or "")

    def _params(self, component_id: str) -> dict[str, Any]:
        component = self.components.get(component_id) or {}
        obj = component.get("obj") or {}
        params = obj.get("params")
        return params if isinstance(params, dict) else {}

    def _add(self, severity: str, code: str, message: str, component_id: str = "") -> None:
        self.issues.append(
            AgentValidationIssue(
                severity=severity,
                code=code,
                message=message,
                component_id=component_id,
                component_name=self._component_name(component_id) if component_id else "",
            )
        )

    def _validate_shape(self) -> None:
        if not isinstance(self.dsl, dict):
            self._add(AgentValidationIssue.ERROR, "invalid_dsl", "Agent DSL must be an object.")
            return
        if not self.components:
            self._add(AgentValidationIssue.ERROR, "empty_components", "Agent workflow must contain at least one node.")

    def _validate_begin(self) -> None:
        begins = [component_id for component_id in self.components if self._component_name(component_id).lower() == "begin"]
        if not begins:
            self._add(AgentValidationIssue.ERROR, "missing_begin", "Agent workflow must contain a Begin node.")
        elif len(begins) > 1:
            self._add(AgentValidationIssue.WARNING, "multiple_begin", "Agent workflow contains multiple Begin nodes.")

    @staticmethod
    def _as_id_list(value: Any) -> list[str]:
        if isinstance(value, list):
            return [str(item) for item in value if item]
        if isinstance(value, str) and value:
            return [value]
        return []

    def _validate_edges(self) -> None:
        known = set(self.components.keys())
        for component_id, component in self.components.items():
            downstream = self._as_id_list(component.get("downstream"))
            upstream = self._as_id_list(component.get("upstream"))
            for target in downstream:
                if target not in known:
                    self._add(
                        AgentValidationIssue.ERROR,
                        "broken_downstream",
                        f"Node references missing downstream node `{target}`.",
                        component_id,
                    )
            for source in upstream:
                if source not in known:
                    self._add(
                        AgentValidationIssue.ERROR,
                        "broken_upstream",
                        f"Node references missing upstream node `{source}`.",
                        component_id,
                    )

    def _validate_connectivity(self) -> None:
        if len(self.components) <= 1:
            return
        for component_id, component in self.components.items():
            name = self._component_name(component_id).lower()
            if name in {"note"}:
                continue
            downstream = self._as_id_list(component.get("downstream"))
            upstream = self._as_id_list(component.get("upstream"))
            if name == "begin" and not downstream:
                self._add(
                    AgentValidationIssue.WARNING,
                    "begin_without_downstream",
                    "Begin node has no downstream node.",
                    component_id,
                )
            elif name != "begin" and not upstream and not downstream:
                self._add(
                    AgentValidationIssue.WARNING,
                    "isolated_node",
                    "Node is isolated and will not run in the workflow.",
                    component_id,
                )
            elif name != "begin" and not upstream:
                self._add(
                    AgentValidationIssue.WARNING,
                    "node_without_upstream",
                    "Node has no upstream input and may not run.",
                    component_id,
                )

        if not any(
            self._component_name(component_id).lower() in self.OUTPUT_COMPONENTS
            for component_id in self.components
        ):
            self._add(
                AgentValidationIssue.WARNING,
                "missing_output_node",
                "Workflow has no obvious answer or artifact output node.",
            )

    def _validate_required_params(self) -> None:
        for component_id in self.components:
            name = self._component_name(component_id).lower()
            params = self._params(component_id)
            if name in self.LLM_COMPONENTS and not str(params.get("llm_id") or "").strip():
                self._add(
                    AgentValidationIssue.ERROR,
                    "missing_llm",
                    "LLM node must configure a model before publishing.",
                    component_id,
                )
            if name == "docgenerator" and not str(params.get("content") or "").strip():
                self._add(
                    AgentValidationIssue.ERROR,
                    "missing_doc_content",
                    "DocGenerator must configure content before publishing.",
                    component_id,
                )
            if name == "excelprocessor":
                input_files = params.get("input_files")
                operation = str(params.get("operation") or "").lower()
                if operation in {"read", "aggregate"} and not input_files:
                    self._add(
                        AgentValidationIssue.WARNING,
                        "missing_excel_input",
                        "ExcelProcessor has no file input configured.",
                        component_id,
                    )
                if operation in {"output", "export"} and not str(params.get("transform_data") or "").strip():
                    self._add(
                        AgentValidationIssue.ERROR,
                        "missing_excel_output_data",
                        "ExcelProcessor export must configure a data variable reference.",
                        component_id,
                    )
                if operation == "calculate" and str(params.get("calculation_value") or "").strip() == "":
                    self._add(
                        AgentValidationIssue.ERROR,
                        "missing_excel_calculation_value",
                        "ExcelProcessor calculate must configure a source value.",
                        component_id,
                    )
            if name == "fileparser":
                input_files = params.get("input_files")
                if not input_files:
                    self._add(
                        AgentValidationIssue.ERROR,
                        "missing_file_parser_input",
                        "FileParser must configure an uploaded file input.",
                        component_id,
                    )

    def _walk_strings(self, value: Any) -> list[str]:
        if isinstance(value, str):
            return [value]
        if isinstance(value, list):
            result = []
            for item in value:
                result.extend(self._walk_strings(item))
            return result
        if isinstance(value, dict):
            result = []
            for item in value.values():
                result.extend(self._walk_strings(item))
            return result
        return []

    def _validate_variable_refs(self) -> None:
        known = set(self.components.keys())
        for component_id in self.components:
            params = self._params(component_id)
            for text in self._walk_strings(params):
                for ref in self.VARIABLE_REF_RE.findall(text):
                    if "@" not in ref:
                        continue
                    source_id, var_name = ref.split("@", 1)
                    if source_id in {"sys", "item", "index"}:
                        continue
                    if source_id not in known:
                        self._add(
                            AgentValidationIssue.ERROR,
                            "missing_variable_source",
                            f"Variable reference `{source_id}@{var_name}` points to a missing node.",
                            component_id,
                        )

    def _walk_string_paths(self, value: Any, path: str = "") -> list[tuple[str, str]]:
        if isinstance(value, str):
            return [(path, value)]
        if isinstance(value, list):
            result = []
            for index, item in enumerate(value):
                child_path = f"{path}[{index}]" if path else f"[{index}]"
                result.extend(self._walk_string_paths(item, child_path))
            return result
        if isinstance(value, dict):
            result = []
            for key, item in value.items():
                child_path = f"{path}.{key}" if path else str(key)
                result.extend(self._walk_string_paths(item, child_path))
            return result
        return []

    @staticmethod
    def _schema_type_map(schema: dict[str, Any] | None) -> dict[str, str]:
        result = {}
        if not isinstance(schema, dict):
            return result
        for key, value in schema.items():
            if isinstance(value, dict):
                result[str(key)] = normalize_schema_type(value.get("type") or value.get("schema_type"))
            else:
                result[str(key)] = normalize_schema_type(value)
        return result

    @staticmethod
    def _normalize_declared_schema(schema: dict[str, Any] | None) -> dict[str, str]:
        return AgentValidationService._schema_type_map(schema)

    def _begin_output_schema(self, component_id: str) -> dict[str, str]:
        params = self._params(component_id)
        inputs = params.get("inputs") or {}
        if isinstance(inputs, dict):
            items = [
                {"key": key, **(value if isinstance(value, dict) else {"type": value})}
                for key, value in inputs.items()
            ]
        elif isinstance(inputs, list):
            items = [item for item in inputs if isinstance(item, dict)]
        else:
            items = []

        schema = {}
        for item in items:
            key = str(item.get("key") or item.get("name") or "").strip()
            if not key:
                continue
            input_type = normalize_schema_type(item.get("type"))
            lower_type = str(item.get("type") or "").lower()
            if "file" in lower_type or input_type == SCHEMA_TYPE_FILE_ASSET:
                schema[key] = SCHEMA_TYPE_STRING
                schema[f"{key}_text"] = SCHEMA_TYPE_STRING
                schema[f"{key}_files"] = f"{SCHEMA_TYPE_ARRAY}<{SCHEMA_TYPE_FILE_ASSET}>"
                schema[f"{key}_file_assets"] = f"{SCHEMA_TYPE_ARRAY}<{SCHEMA_TYPE_FILE_ASSET}>"
                schema[f"{key}_file_texts"] = f"{SCHEMA_TYPE_ARRAY}<{SCHEMA_TYPE_TEXT_DOCUMENT}>"
                schema[f"{key}_file_chunks"] = f"{SCHEMA_TYPE_ARRAY}<{SCHEMA_TYPE_TEXT_CHUNK}>"
            else:
                schema[key] = input_type
        return schema

    def _component_input_schema(self, component_id: str) -> dict[str, str]:
        name = self._component_name(component_id).lower()
        schema = dict(self.DEFAULT_INPUT_SCHEMAS.get(name, {}))
        params = self._params(component_id)
        declared = params.get("input_schema")
        schema.update(self._normalize_declared_schema(declared))
        return {key: normalize_schema_type(value) for key, value in schema.items()}

    def _component_output_schema(self, component_id: str) -> dict[str, str]:
        name = self._component_name(component_id).lower()
        schema = dict(self.DEFAULT_OUTPUT_SCHEMAS.get(name, {}))
        if name in {"begin", "userfillup"}:
            schema.update(self._begin_output_schema(component_id))
        params = self._params(component_id)
        declared = params.get("output_schema")
        outputs = params.get("outputs")
        schema.update(self._normalize_declared_schema(declared))
        schema.update(self._schema_type_map(outputs))
        return {key: normalize_schema_type(value) for key, value in schema.items()}

    @staticmethod
    def _root_path_name(path: str) -> str:
        return re.split(r"[.\[]", path or "", maxsplit=1)[0]

    def _target_input_name(self, component_id: str, path: str) -> str:
        root = self._root_path_name(path)
        if root == "prompts":
            return "prompts"
        if root == "tools":
            return "tools"
        if root == "outputs":
            return ""
        if root == "content":
            return "content"
        if root == "input_files":
            return "input_files"
        if root == "arguments":
            return "arguments"
        if root:
            return root
        name = self._component_name(component_id).lower()
        if name in self.TEXT_INPUT_COMPONENTS:
            return "content"
        return ""

    @staticmethod
    def _array_inner(type_name: str) -> str:
        normalized = normalize_schema_type(type_name)
        prefix = f"{SCHEMA_TYPE_ARRAY}<"
        if normalized.startswith(prefix) and normalized.endswith(">"):
            return normalized[len(prefix):-1]
        return ""

    @classmethod
    def _type_base(cls, type_name: str) -> str:
        normalized = normalize_schema_type(type_name)
        return cls._array_inner(normalized) or normalized

    @classmethod
    def _is_array_type(cls, type_name: str) -> bool:
        return normalize_schema_type(type_name).startswith(f"{SCHEMA_TYPE_ARRAY}<")

    @classmethod
    def _is_text_prompt_blocked(cls, source_type: str) -> bool:
        source_base = cls._type_base(source_type)
        return source_base in cls.NON_TEXT_PROMPT_TYPES

    @classmethod
    def _types_compatible(cls, source_type: str, target_type: str, target_component: str, target_input: str) -> tuple[bool, str]:
        source_type = normalize_schema_type(source_type)
        target_type = normalize_schema_type(target_type)
        source_base = cls._type_base(source_type)
        target_base = cls._type_base(target_type)
        target_component = (target_component or "").lower()

        if target_type == SCHEMA_TYPE_ANY or source_type == SCHEMA_TYPE_ANY:
            return True, ""
        if source_type == target_type:
            return True, ""

        if target_component in {"agent", "agentwithtools", "llm", "categorize", "rewritequestion"} and target_input in cls.LLM_PROMPT_PARAMS:
            if cls._is_text_prompt_blocked(source_type):
                return False, "Artifact/File/Audio/AgentRun data cannot be injected directly into an LLM prompt. Parse or summarize it into text first."

        if target_type == SCHEMA_TYPE_STRING:
            if cls._is_text_prompt_blocked(source_type):
                return False, "This target expects text. Parse the file/artifact/audio into text before connecting it."
            return True, ""

        if target_base == SCHEMA_TYPE_FILE_ASSET:
            if source_base == SCHEMA_TYPE_FILE_ASSET:
                return True, ""
            return False, "This input expects uploaded file assets. Use Begin file assets or an upstream file-producing node."

        if target_base in {SCHEMA_TYPE_TEXT_DOCUMENT, SCHEMA_TYPE_TEXT_CHUNK}:
            if source_base == target_base:
                return True, ""
            if source_base == SCHEMA_TYPE_FILE_ASSET:
                return False, "FileAsset cannot be used as parsed text. Insert FileParser before this node."
            return False, "This input expects parsed document text or chunks. Use a parser node first."

        if target_base == SCHEMA_TYPE_AUDIO_ASSET:
            if source_base == SCHEMA_TYPE_AUDIO_ASSET:
                return True, ""
            return False, "This input expects audio. Use an audio input or TTS node output."

        if target_base == SCHEMA_TYPE_NUMBER:
            if source_base == SCHEMA_TYPE_NUMBER:
                return True, ""
            return False, "This input expects a numeric value. Add an explicit calculation or parsing node before connecting."

        if target_base == SCHEMA_TYPE_BOOLEAN:
            if source_base == SCHEMA_TYPE_BOOLEAN:
                return True, ""
            return False, "This input expects a boolean value. Add an explicit conversion node before connecting."

        if target_base in {SCHEMA_TYPE_JSON, SCHEMA_TYPE_TABLE_DATA, SCHEMA_TYPE_SQL_RESULT, SCHEMA_TYPE_ARTIFACT}:
            if source_base == target_base:
                return True, ""
            return False, f"This input expects {target_type}. Add a node that outputs {target_type} before connecting."

        if cls._is_array_type(target_type):
            if cls._is_array_type(source_type) and source_base == target_base:
                return True, ""
            return False, f"This input expects {target_type}, but the source outputs {source_type}."

        return source_base == target_base, ""

    def _validate_type_compatibility(self) -> None:
        known = set(self.components.keys())
        warned_missing_schema: set[tuple[str, str, str]] = set()

        for target_id in self.components:
            target_params = self._params(target_id)
            target_name = self._component_name(target_id)
            target_schema = self._component_input_schema(target_id)
            for path, text in self._walk_string_paths(target_params):
                for ref in self.VARIABLE_REF_RE.findall(text):
                    if "@" not in ref:
                        continue
                    source_id, source_output = ref.split("@", 1)
                    if source_id in {"sys", "item", "index"} or source_id not in known:
                        continue

                    target_input = self._target_input_name(target_id, path)
                    if not target_input:
                        continue

                    source_schema = self._component_output_schema(source_id)
                    source_type = source_schema.get(source_output)
                    target_type = target_schema.get(target_input)

                    if not source_type or not target_type:
                        key = (target_id, source_id, source_output)
                        if key not in warned_missing_schema:
                            warned_missing_schema.add(key)
                            missing = []
                            if not source_type:
                                missing.append(f"source output `{source_id}@{source_output}`")
                            if not target_type:
                                missing.append(f"target input `{target_id}.{target_input}`")
                            self._add(
                                AgentValidationIssue.WARNING,
                                "missing_port_schema",
                                "Cannot validate type compatibility because schema is missing for "
                                + " and ".join(missing)
                                + ". Existing workflow is kept compatible.",
                                target_id,
                            )
                        continue

                    compatible, suggestion = self._types_compatible(
                        source_type,
                        target_type,
                        target_name,
                        target_input,
                    )
                    if compatible:
                        continue
                    self._add(
                        AgentValidationIssue.ERROR,
                        "incompatible_connection_type",
                        (
                            f"Incompatible variable connection: source `{source_id}@{source_output}` "
                            f"({source_type}) -> target `{target_id}.{target_input}` ({target_type}). "
                            f"{suggestion}"
                        ).strip(),
                        target_id,
                    )

    def _validate_sql(self) -> None:
        for component_id in self.components:
            if self._component_name(component_id).lower() != "exesql":
                continue
            sql = self._params(component_id).get("sql") or ""
            if not str(sql).strip():
                self._add(AgentValidationIssue.ERROR, "missing_sql", "ExeSQL must configure SQL.", component_id)
                continue
            try:
                prepare_readonly_sqls(str(sql))
            except Exception as exc:
                if self.VARIABLE_REF_RE.fullmatch(str(sql).strip()):
                    self._add(
                        AgentValidationIssue.WARNING,
                        "dynamic_sql_runtime_validation",
                        "ExeSQL SQL is provided by a variable and will be validated as read-only at runtime.",
                        component_id,
                    )
                    continue
                self._add(
                    AgentValidationIssue.ERROR,
                    "unsafe_sql",
                    str(exc),
                    component_id,
                )

    def _validate_file_flow(self) -> None:
        begin_has_file_input = False
        for component_id in self.components:
            if self._component_name(component_id).lower() != "begin":
                continue
            params = self._params(component_id)
            inputs = params.get("inputs") or []
            if isinstance(inputs, dict):
                inputs = inputs.values()
            for item in inputs:
                if isinstance(item, dict) and str(item.get("type") or "").lower() == "file":
                    begin_has_file_input = True
                    break

        if not begin_has_file_input:
            return

        has_file_processor = any(
            self._component_name(component_id).lower() in self.FILE_PROCESSORS
            for component_id in self.components
        )
        if not has_file_processor:
            self._add(
                AgentValidationIssue.WARNING,
                "file_input_without_processor",
                "Workflow accepts uploaded files but has no file parsing, Excel, or document output node.",
            )

    def _is_artifact_component(self, component_id: str) -> bool:
        name = self._component_name(component_id).lower()
        if name in self.ARTIFACT_COMPONENTS:
            return True
        if name == "excelprocessor":
            return str(self._params(component_id).get("operation") or "").lower() in {"output", "export"}
        return False

    def _can_reach_message(self, component_id: str) -> bool:
        visited = set()
        queue = self._as_id_list((self.components.get(component_id) or {}).get("downstream"))
        while queue:
            current = queue.pop(0)
            if current in visited:
                continue
            visited.add(current)
            if self._component_name(current).lower() == "message":
                return True
            queue.extend(self._as_id_list((self.components.get(current) or {}).get("downstream")))
        return False

    def _validate_artifact_visibility(self) -> None:
        for component_id in self.components:
            if not self._is_artifact_component(component_id):
                continue
            if not self._can_reach_message(component_id):
                self._add(
                    AgentValidationIssue.WARNING,
                    "artifact_without_message_output",
                    "This node can generate downloadable artifacts, but no downstream Message node will expose them in the answer.",
                    component_id,
                )
