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
from copy import deepcopy
from typing import Any


SCHEMA_TYPE_ANY = "Any"
SCHEMA_TYPE_STRING = "String"
SCHEMA_TYPE_NUMBER = "Number"
SCHEMA_TYPE_BOOLEAN = "Boolean"
SCHEMA_TYPE_JSON = "JSON"
SCHEMA_TYPE_ARRAY = "Array"
SCHEMA_TYPE_FILE_ASSET = "FileAsset"
SCHEMA_TYPE_TEXT_DOCUMENT = "TextDocument"
SCHEMA_TYPE_TEXT_CHUNK = "TextChunk"
SCHEMA_TYPE_TABLE_DATA = "TableData"
SCHEMA_TYPE_SQL_RESULT = "SQLResult"
SCHEMA_TYPE_ARTIFACT = "Artifact"
SCHEMA_TYPE_AUDIO_ASSET = "AudioAsset"
SCHEMA_TYPE_VOICE_REPLY = "VoiceReply"
SCHEMA_TYPE_AGENT_RUN_REF = "AgentRunRef"
SCHEMA_TYPE_MEETING_CONTEXT = "MeetingContext"
SCHEMA_TYPE_SCORE_RUBRIC = "ScoreRubric"
SCHEMA_TYPE_SCORE_RESULT = "ScoreResult"
SCHEMA_TYPE_CHART_SPEC = "ChartSpec"

STANDARD_SCHEMA_TYPES = {
    SCHEMA_TYPE_ANY,
    SCHEMA_TYPE_STRING,
    SCHEMA_TYPE_NUMBER,
    SCHEMA_TYPE_BOOLEAN,
    SCHEMA_TYPE_JSON,
    SCHEMA_TYPE_ARRAY,
    SCHEMA_TYPE_FILE_ASSET,
    SCHEMA_TYPE_TEXT_DOCUMENT,
    SCHEMA_TYPE_TEXT_CHUNK,
    SCHEMA_TYPE_TABLE_DATA,
    SCHEMA_TYPE_SQL_RESULT,
    SCHEMA_TYPE_ARTIFACT,
    SCHEMA_TYPE_AUDIO_ASSET,
    SCHEMA_TYPE_VOICE_REPLY,
    SCHEMA_TYPE_AGENT_RUN_REF,
    SCHEMA_TYPE_MEETING_CONTEXT,
    SCHEMA_TYPE_SCORE_RUBRIC,
    SCHEMA_TYPE_SCORE_RESULT,
    SCHEMA_TYPE_CHART_SPEC,
}


_TYPE_ALIASES = {
    "any": SCHEMA_TYPE_ANY,
    "none": SCHEMA_TYPE_ANY,
    "nonetype": SCHEMA_TYPE_ANY,
    "str": SCHEMA_TYPE_STRING,
    "string": SCHEMA_TYPE_STRING,
    "text": SCHEMA_TYPE_STRING,
    "varchar": SCHEMA_TYPE_STRING,
    "int": SCHEMA_TYPE_NUMBER,
    "integer": SCHEMA_TYPE_NUMBER,
    "float": SCHEMA_TYPE_NUMBER,
    "double": SCHEMA_TYPE_NUMBER,
    "decimal": SCHEMA_TYPE_NUMBER,
    "number": SCHEMA_TYPE_NUMBER,
    "numeric": SCHEMA_TYPE_NUMBER,
    "bool": SCHEMA_TYPE_BOOLEAN,
    "boolean": SCHEMA_TYPE_BOOLEAN,
    "dict": SCHEMA_TYPE_JSON,
    "object": SCHEMA_TYPE_JSON,
    "json": SCHEMA_TYPE_JSON,
    "dataframe": SCHEMA_TYPE_JSON,
    "list": SCHEMA_TYPE_ARRAY,
    "array": SCHEMA_TYPE_ARRAY,
    "tuple": SCHEMA_TYPE_ARRAY,
    "file": SCHEMA_TYPE_FILE_ASSET,
    "upload": SCHEMA_TYPE_FILE_ASSET,
    "uploadedfile": SCHEMA_TYPE_FILE_ASSET,
    "fileasset": SCHEMA_TYPE_FILE_ASSET,
    "attachment": SCHEMA_TYPE_FILE_ASSET,
    "textdocument": SCHEMA_TYPE_TEXT_DOCUMENT,
    "document": SCHEMA_TYPE_TEXT_DOCUMENT,
    "textdoc": SCHEMA_TYPE_TEXT_DOCUMENT,
    "textchunk": SCHEMA_TYPE_TEXT_CHUNK,
    "chunk": SCHEMA_TYPE_TEXT_CHUNK,
    "tabledata": SCHEMA_TYPE_TABLE_DATA,
    "table": SCHEMA_TYPE_TABLE_DATA,
    "dataframe": SCHEMA_TYPE_TABLE_DATA,
    "sqlresult": SCHEMA_TYPE_SQL_RESULT,
    "sql_result": SCHEMA_TYPE_SQL_RESULT,
    "artifact": SCHEMA_TYPE_ARTIFACT,
    "audio": SCHEMA_TYPE_AUDIO_ASSET,
    "audioasset": SCHEMA_TYPE_AUDIO_ASSET,
    "voice": SCHEMA_TYPE_VOICE_REPLY,
    "voicereply": SCHEMA_TYPE_VOICE_REPLY,
    "agentrun": SCHEMA_TYPE_AGENT_RUN_REF,
    "agentrunref": SCHEMA_TYPE_AGENT_RUN_REF,
    "meeting": SCHEMA_TYPE_MEETING_CONTEXT,
    "meetingcontext": SCHEMA_TYPE_MEETING_CONTEXT,
    "scorerubric": SCHEMA_TYPE_SCORE_RUBRIC,
    "rubric": SCHEMA_TYPE_SCORE_RUBRIC,
    "scoreresult": SCHEMA_TYPE_SCORE_RESULT,
    "score": SCHEMA_TYPE_SCORE_RESULT,
    "chartspec": SCHEMA_TYPE_CHART_SPEC,
    "chart": SCHEMA_TYPE_CHART_SPEC,
}

_COMPONENT_CATEGORY_MAP = {
    "begin": "input",
    "userfillup": "human_review",
    "waitingdialogue": "human_review",
    "webhookinput": "human_review",
    "externalscorereceiver": "human_review",
    "humanreview": "human_review",
    "manualapprove": "human_review",
    "goalintentclassifier": "task_planning",
    "goalnormalizer": "task_planning",
    "taskcontextcollector": "task_planning",
    "recentartifactfinder": "task_planning",
    "relevantfileresolver": "task_planning",
    "taskplanner": "task_planning",
    "taskdecomposer": "task_planning",
    "atomictaskrefiner": "task_planning",
    "preconditionchecker": "task_planning",
    "dependencyresolver": "task_planning",
    "taskexecutor": "task_planning",
    "taskframecontroller": "task_planning",
    "taskresultverifier": "task_planning",
    "taskreflection": "task_planning",
    "replandecider": "task_planning",
    "taskexecutionreportcomposer": "task_planning",
    "file": "input",
    "fileparser": "file",
    "citationformatter": "file",
    "workspacefilelist": "file",
    "workspacefilesearch": "file",
    "workspacefileread": "file",
    "workspacefilewrite": "file",
    "workspacepatchapply": "file",
    "workspacetableread": "file",
    "documentnormalizer": "file",
    "documentstructureadvisor": "file",
    "contentplacementplanner": "file",
    "clauseextractor": "file",
    "obligationextractor": "file",
    "definitionextractor": "file",
    "viewpointextractor": "file",
    "riskpointextractor": "file",
    "tablefactextractor": "file",
    "documentdiff": "file",
    "tablediff": "file",
    "documentsemanticcomparer": "file",
    "documentconflictdetector": "file",
    "documentcomparereportcomposer": "file",
    "contractclauseextractor": "compliance",
    "compliancechecklistgenerator": "compliance",
    "clausematcher": "compliance",
    "complianceverifier": "compliance",
    "riskscorer": "compliance",
    "compliancereportcomposer": "compliance",
    "parser": "file",
    "tokenizer": "file",
    "tokenchunker": "file",
    "titlechunker": "file",
    "extractor": "file",
    "retrieval": "retrieval",
    "browser": "retrieval",
    "crawler": "retrieval",
    "duckduckgo": "retrieval",
    "wikipedia": "retrieval",
    "pubmed": "retrieval",
    "arxiv": "retrieval",
    "wencai": "retrieval",
    "yahoofinance": "retrieval",
    "google": "retrieval",
    "bing": "retrieval",
    "googlescholar": "retrieval",
    "searxng": "retrieval",
    "tavilysearch": "retrieval",
    "tavilyextract": "retrieval",
    "github": "retrieval",
    "excelprocessor": "table",
    "numbercalculate": "table",
    "chartspecbuilder": "table",
    "chartrenderer": "output",
    "artifactpackager": "output",
    "dataoperations": "table",
    "listoperations": "table",
    "exesql": "database",
    "scopeddbconnector": "database",
    "safetableensure": "database",
    "saferecordinsert": "database",
    "saferecordupdate": "database",
    "saferecordquery": "database",
    "llm": "llm",
    "agent": "llm",
    "agentwithtools": "llm",
    "categorize": "llm",
    "rewritequestion": "llm",
    "stringtransform": "llm",
    "prompttemplate": "llm",
    "scorerubricbuilder": "llm",
    "pronunciationjudge": "llm",
    "summarynode": "llm",
    "reportcomposer": "llm",
    "switch": "flow_control",
    "iteration": "flow_control",
    "iterationitem": "flow_control",
    "loop": "flow_control",
    "loopitem": "flow_control",
    "exitloop": "flow_control",
    "variableassigner": "flow_control",
    "variableaggregator": "flow_control",
    "message": "output",
    "docgenerator": "output",
    "codeexec": "output",
    "invoke": "output",
    "email": "output",
    "ttsgenerate": "voice_multi_agent",
    "asrtranscribe": "voice_multi_agent",
    "audioinput": "voice_multi_agent",
    "voicereplyoutput": "voice_multi_agent",
    "meetingcontextinput": "voice_multi_agent",
    "memoryinject": "voice_multi_agent",
    "agentfanout": "voice_multi_agent",
    "resultaggregator": "voice_multi_agent",
}

_COMPONENT_RISK_LEVEL_MAP = {
    "exesql": "high",
    "scopeddbconnector": "medium",
    "safetableensure": "medium",
    "saferecordinsert": "medium",
    "saferecordupdate": "medium",
    "saferecordquery": "medium",
    "codeexec": "high",
    "artifactpackager": "medium",
    "invoke": "medium",
    "email": "medium",
    "webhookinput": "medium",
    "externalscorereceiver": "medium",
    "browser": "medium",
    "crawler": "medium",
    "github": "medium",
    "wencai": "medium",
    "yahoofinance": "medium",
    "google": "medium",
    "bing": "medium",
    "googlescholar": "medium",
    "searxng": "medium",
    "tavilysearch": "medium",
    "tavilyextract": "medium",
    "ttsgenerate": "medium",
    "asrtranscribe": "medium",
    "agentfanout": "medium",
    "goalintentclassifier": "low",
    "goalnormalizer": "low",
    "taskcontextcollector": "medium",
    "recentartifactfinder": "low",
    "relevantfileresolver": "medium",
    "taskplanner": "low",
    "taskdecomposer": "low",
    "atomictaskrefiner": "low",
    "preconditionchecker": "low",
    "dependencyresolver": "low",
    "taskexecutor": "medium",
    "taskframecontroller": "low",
    "taskresultverifier": "low",
    "taskreflection": "low",
    "replandecider": "low",
    "taskexecutionreportcomposer": "low",
    "workspacefilelist": "medium",
    "workspacefilesearch": "medium",
    "workspacefileread": "medium",
    "workspacefilewrite": "high",
    "workspacepatchapply": "high",
    "workspacetableread": "medium",
    "documentnormalizer": "medium",
    "documentstructureadvisor": "low",
    "contentplacementplanner": "low",
    "clauseextractor": "medium",
    "obligationextractor": "medium",
    "definitionextractor": "medium",
    "viewpointextractor": "medium",
    "riskpointextractor": "medium",
    "tablefactextractor": "medium",
    "documentdiff": "medium",
    "tablediff": "medium",
    "documentsemanticcomparer": "medium",
    "documentconflictdetector": "medium",
    "documentcomparereportcomposer": "medium",
}

_COMPONENT_SERVICE_DEPENDENCIES = {
    "retrieval": ["ragflow_index"],
    "fileparser": ["ragflow_file_storage"],
    "workspacefilelist": ["workspace_files"],
    "workspacefilesearch": ["workspace_files"],
    "workspacefileread": ["workspace_files"],
    "workspacefilewrite": ["workspace_files"],
    "workspacepatchapply": ["workspace_files"],
    "workspacetableread": ["workspace_files"],
    "documentnormalizer": ["workspace_files"],
    "clauseextractor": ["document_normalizer"],
    "obligationextractor": ["document_normalizer"],
    "definitionextractor": ["document_normalizer"],
    "viewpointextractor": ["document_normalizer"],
    "riskpointextractor": ["document_normalizer"],
    "tablefactextractor": ["document_normalizer"],
    "documentdiff": ["document_normalizer"],
    "tablediff": ["document_normalizer"],
    "documentsemanticcomparer": ["document_normalizer"],
    "documentconflictdetector": ["document_normalizer"],
    "documentcomparereportcomposer": ["artifact_storage"],
    "taskcontextcollector": ["workspace_files"],
    "relevantfileresolver": ["workspace_files"],
    "parser": ["ragflow_file_storage"],
    "tokenizer": ["ragflow_file_storage"],
    "extractor": ["ragflow_file_storage"],
    "excelprocessor": ["ragflow_file_storage"],
    "docgenerator": ["ragflow_file_storage"],
    "chartrenderer": ["ragflow_file_storage"],
    "artifactpackager": ["ragflow_file_storage"],
    "exesql": ["database"],
    "scopeddbconnector": ["scoped_sqlite"],
    "safetableensure": ["scoped_sqlite"],
    "saferecordinsert": ["scoped_sqlite"],
    "saferecordupdate": ["scoped_sqlite"],
    "saferecordquery": ["scoped_sqlite"],
    "browser": ["network"],
    "crawler": ["network"],
    "duckduckgo": ["network"],
    "wikipedia": ["network"],
    "pubmed": ["network"],
    "arxiv": ["network"],
    "google": ["network"],
    "bing": ["network"],
    "googlescholar": ["network"],
    "searxng": ["network"],
    "tavilysearch": ["network"],
    "tavilyextract": ["network"],
    "github": ["network"],
    "wencai": ["network"],
    "yahoofinance": ["network"],
    "invoke": ["network"],
    "email": ["smtp"],
    "webhookinput": ["agent_webhook"],
    "externalscorereceiver": ["agent_webhook"],
    "ttsgenerate": ["cosyvoice3"],
    "asrtranscribe": ["qwen3_asr"],
    "voicereplyoutput": ["cosyvoice3"],
    "agentfanout": ["agent_run_queue"],
    "meetingcontextinput": ["agent_meeting_memory"],
    "memoryinject": ["agent_meeting_memory"],
}


def normalize_schema_type(type_name: Any) -> str:
    if not type_name:
        return SCHEMA_TYPE_ANY

    if isinstance(type_name, type):
        type_name = type_name.__name__

    raw = str(type_name).strip()
    match = re.match(r"<class '([^']+)'>", raw)
    if match:
        raw = match.group(1).rsplit(".", 1)[-1]

    compact = raw.replace(" ", "")
    lower = compact.lower()
    if lower.startswith("array<") and lower.endswith(">"):
        inner = normalize_schema_type(compact[6:-1])
        return f"{SCHEMA_TYPE_ARRAY}<{inner}>"
    if lower.startswith("list[") and lower.endswith("]"):
        inner = normalize_schema_type(compact[5:-1])
        return f"{SCHEMA_TYPE_ARRAY}<{inner}>"
    if lower.startswith("typing.list[") and lower.endswith("]"):
        inner = normalize_schema_type(compact[12:-1])
        return f"{SCHEMA_TYPE_ARRAY}<{inner}>"
    if lower.endswith("[]") and len(compact) > 2:
        inner = normalize_schema_type(compact[:-2])
        return f"{SCHEMA_TYPE_ARRAY}<{inner}>"

    return _TYPE_ALIASES.get(lower, raw[:1].upper() + raw[1:] if raw else SCHEMA_TYPE_ANY)


def build_field_schema(name: str, spec: Any = None, default_required: bool = False) -> dict[str, Any]:
    field = {
        "name": str(name),
        "type": SCHEMA_TYPE_ANY,
        "required": default_required,
    }

    if isinstance(spec, dict):
        source = deepcopy(spec)
        field["type"] = normalize_schema_type(source.get("type") or source.get("schema_type"))
        if source.get("name"):
            field["label"] = source.get("name")
        if source.get("label"):
            field["label"] = source.get("label")
        if source.get("description"):
            field["description"] = source.get("description")
        if source.get("required") is not None:
            field["required"] = bool(source.get("required"))
        if source.get("items"):
            field["items"] = deepcopy(source.get("items"))
        if source.get("properties"):
            field["properties"] = deepcopy(source.get("properties"))
        if source.get("source"):
            field["source"] = source.get("source")
        return field

    field["type"] = normalize_schema_type(spec)
    return field


def build_schema_from_io(fields: Any, default_required: bool = False) -> dict[str, dict[str, Any]]:
    if not isinstance(fields, dict):
        return {}
    return {
        str(name): build_field_schema(str(name), spec, default_required=default_required)
        for name, spec in fields.items()
    }


def merge_schema(base: Any, overlay: Any) -> dict[str, Any]:
    if not isinstance(base, dict):
        base = {}
    if not isinstance(overlay, dict):
        return deepcopy(base)

    result = deepcopy(base)
    for key, value in overlay.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = merge_schema(result[key], value)
        else:
            result[key] = deepcopy(value)
    return result


def normalize_service_dependencies(value: Any) -> list[str]:
    if not value:
        return []
    if isinstance(value, str):
        values = [value]
    elif isinstance(value, (list, tuple, set)):
        values = list(value)
    else:
        values = []
    result = []
    seen = set()
    for item in values:
        service = str(item or "").strip()
        if service and service not in seen:
            seen.add(service)
            result.append(service)
    return result


def infer_component_category(component_name: str, explicit: Any = None) -> str:
    if isinstance(explicit, str) and explicit.strip():
        return explicit.strip()
    return _COMPONENT_CATEGORY_MAP.get((component_name or "").lower(), "general")


def infer_component_risk_level(component_name: str, explicit: Any = None) -> str:
    if isinstance(explicit, str) and explicit.strip():
        return explicit.strip().lower()
    return _COMPONENT_RISK_LEVEL_MAP.get((component_name or "").lower(), "low")


def infer_component_services(component_name: str, explicit: Any = None) -> list[str]:
    services = _COMPONENT_SERVICE_DEPENDENCIES.get((component_name or "").lower(), [])
    merged = list(services) + normalize_service_dependencies(explicit)
    return normalize_service_dependencies(merged)


def build_runtime_capabilities(
    component_name: str,
    explicit: Any = None,
    inputs: dict[str, dict[str, Any]] | None = None,
    outputs: dict[str, dict[str, Any]] | None = None,
) -> dict[str, bool]:
    capabilities = {
        "streaming": False,
        "long_running": False,
        "produces_artifacts": False,
        "accepts_files": False,
        "uses_external_io": False,
        "supports_cancel": True,
    }

    name = (component_name or "").lower()
    if name in {"llm", "agent", "agentwithtools", "message"}:
        capabilities["streaming"] = True
        capabilities["long_running"] = True
    if name in {
        "retrieval",
        "browser",
        "codeexec",
        "exesql",
        "excelprocessor",
        "docgenerator",
        "chartrenderer",
        "artifactpackager",
        "invoke",
        "email",
        "ttsgenerate",
        "asrtranscribe",
        "agentfanout",
    }:
        capabilities["long_running"] = True
    if name in {"codeexec", "excelprocessor", "docgenerator", "chartrenderer", "artifactpackager", "ttsgenerate"}:
        capabilities["produces_artifacts"] = True
    if name in {
        "exesql",
        "retrieval",
        "browser",
        "invoke",
        "email",
        "ttsgenerate",
        "asrtranscribe",
        "agentfanout",
        "workspacefilewrite",
        "workspacepatchapply",
    }:
        capabilities["uses_external_io"] = True

    for field in list((inputs or {}).values()) + list((outputs or {}).values()):
        field_type = normalize_schema_type(field.get("type") if isinstance(field, dict) else field)
        if field_type == SCHEMA_TYPE_FILE_ASSET or field_type.startswith(f"{SCHEMA_TYPE_ARRAY}<FileAsset"):
            capabilities["accepts_files"] = True
        if field_type == SCHEMA_TYPE_ARTIFACT or field_type.startswith(f"{SCHEMA_TYPE_ARRAY}<{SCHEMA_TYPE_ARTIFACT}"):
            capabilities["produces_artifacts"] = True

    if isinstance(explicit, dict):
        for key, value in explicit.items():
            if key in capabilities:
                capabilities[key] = bool(value)

    return capabilities


def build_component_manifest(
    component_name: str,
    *,
    input_schema: dict[str, dict[str, Any]] | None = None,
    output_schema: dict[str, dict[str, Any]] | None = None,
    config_schema: dict[str, Any] | None = None,
    runtime_capabilities: dict[str, Any] | None = None,
    category: str | None = None,
    risk_level: str | None = None,
    requires_service: Any = None,
) -> dict[str, Any]:
    inputs = input_schema or {}
    outputs = output_schema or {}
    return {
        "operator": component_name,
        "component_name": component_name,
        "category": infer_component_category(component_name, category),
        "input_schema": inputs,
        "output_schema": outputs,
        "config_schema": deepcopy(config_schema or {}),
        "runtime_capabilities": build_runtime_capabilities(
            component_name,
            runtime_capabilities,
            inputs,
            outputs,
        ),
        "risk_level": infer_component_risk_level(component_name, risk_level),
        "requires_service": infer_component_services(component_name, requires_service),
    }


KNOWN_OPERATOR_NAMES = [
    "Begin",
    "UserFillUp",
    "WaitingDialogue",
    "WebhookInput",
    "ExternalScoreReceiver",
    "HumanReview",
    "ManualApprove",
    "GoalIntentClassifier",
    "GoalNormalizer",
    "TaskContextCollector",
    "RecentArtifactFinder",
    "RelevantFileResolver",
    "TaskPlanner",
    "TaskDecomposer",
    "AtomicTaskRefiner",
    "PreconditionChecker",
    "DependencyResolver",
    "TaskExecutor",
    "TaskFrameController",
    "TaskResultVerifier",
    "TaskReflection",
    "ReplanDecider",
    "TaskExecutionReportComposer",
    "Retrieval",
    "Categorize",
    "Message",
    "RewriteQuestion",
    "Agent",
    "Switch",
    "Iteration",
    "IterationItem",
    "Loop",
    "LoopItem",
    "ExitLoop",
    "VariableAssigner",
    "VariableAggregator",
    "StringTransform",
    "PromptTemplate",
    "ScoreRubricBuilder",
    "PronunciationJudge",
    "SummaryNode",
    "ReportComposer",
    "DataOperations",
    "ListOperations",
    "FileParser",
    "CitationFormatter",
    "ContractClauseExtractor",
    "ComplianceChecklistGenerator",
    "ClauseMatcher",
    "ComplianceVerifier",
    "RiskScorer",
    "ComplianceReportComposer",
    "ExcelProcessor",
    "NumberCalculate",
    "ChartSpecBuilder",
    "ChartRenderer",
    "DocGenerator",
    "ArtifactPackager",
    "ExeSQL",
    "ScopedDBConnector",
    "SafeTableEnsure",
    "SafeRecordInsert",
    "SafeRecordUpdate",
    "SafeRecordQuery",
    "CodeExec",
    "Invoke",
    "Email",
    "Browser",
    "DuckDuckGo",
    "Wikipedia",
    "PubMed",
    "ArXiv",
    "WenCai",
    "YahooFinance",
    "Google",
    "Bing",
    "GoogleScholar",
    "GitHub",
    "SearXNG",
    "TavilySearch",
    "TavilyExtract",
    "Crawler",
    "TTSGenerate",
    "ASRTranscribe",
    "AudioInput",
    "VoiceReplyOutput",
    "MeetingContextInput",
    "MemoryInject",
    "AgentFanout",
    "ResultAggregator",
    "WorkspaceFileList",
    "WorkspaceFileSearch",
    "WorkspaceFileRead",
    "WorkspaceFileWrite",
    "WorkspacePatchApply",
    "WorkspaceTableRead",
    "DocumentNormalizer",
    "DocumentStructureAdvisor",
    "ContentPlacementPlanner",
    "ClauseExtractor",
    "ObligationExtractor",
    "DefinitionExtractor",
    "ViewpointExtractor",
    "RiskPointExtractor",
    "TableFactExtractor",
    "DocumentDiff",
    "TableDiff",
    "DocumentSemanticComparer",
    "DocumentConflictDetector",
    "DocumentCompareReportComposer",
]


def list_operator_manifests() -> list[dict[str, Any]]:
    return [build_component_manifest(name) for name in KNOWN_OPERATOR_NAMES]
