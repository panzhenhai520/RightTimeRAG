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

import json
import os
from abc import ABC
from copy import deepcopy
from typing import Any

from agent.component.base import ComponentBase, ComponentParamBase
from api.db.services.agent_meeting_memory_service import AgentMeetingMemoryService
from api.db.services.agent_meeting_scheduler_service import AgentMeetingSchedulerService
from api.utils.api_utils import timeout
from common.misc_utils import get_uuid


def _parse_json_like(value: Any, default: Any = None) -> Any:
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return default
        try:
            return json.loads(text)
        except Exception:
            return default
    return value if value is not None else default


def _as_list(value: Any) -> list[Any]:
    value = _parse_json_like(value, value)
    if value is None or value == "":
        return []
    if isinstance(value, list):
        return deepcopy(value)
    return [deepcopy(value)]


def _as_dict(value: Any) -> dict[str, Any]:
    value = _parse_json_like(value, value)
    return deepcopy(value) if isinstance(value, dict) else {}


def _text(value: Any) -> str:
    return str(value or "").strip()


class MeetingContextInputParam(ComponentParamBase):
    def __init__(self):
        super().__init__()
        self.tenant_id = ""
        self.meeting_id = ""
        self.turn_id = ""
        self.agent_id = ""
        self.role = ""
        self.query = ""
        self.shared_memory = []
        self.agent_memory = []
        self.load_persisted_memory = True
        self.outputs = {
            "meeting_context": {"value": {}, "type": "MeetingContext"},
            "prompt": {"value": "", "type": "string"},
        }
        self.input_schema = {
            "query": {"type": "string", "required": False},
            "shared_memory": {"type": "Array<JSON>", "required": False},
            "agent_memory": {"type": "Array<JSON>", "required": False},
        }

    def check(self):
        return True


class MeetingContextInput(ComponentBase, ABC):
    component_name = "MeetingContextInput"

    @staticmethod
    def build_context(
        *,
        tenant_id: str = "",
        meeting_id: str = "",
        turn_id: str = "",
        agent_id: str = "",
        role: str = "",
        query: str = "",
        shared_memory: list[dict[str, Any]] | None = None,
        agent_memory: list[dict[str, Any]] | None = None,
        load_persisted_memory: bool = True,
        memory_service=AgentMeetingMemoryService,
        uuid_factory=get_uuid,
    ) -> dict[str, Any]:
        tenant_id = _text(tenant_id)
        meeting_id = _text(meeting_id) or uuid_factory()
        turn_id = _text(turn_id) or uuid_factory()
        agent_id = _text(agent_id)
        role = _text(role)
        query = str(query or "")

        provided_shared = _as_list(shared_memory)
        provided_agent = _as_list(agent_memory)
        persisted = {"shared": [], "agent": []}
        if load_persisted_memory and tenant_id and meeting_id and agent_id:
            persisted = memory_service.get_context(tenant_id, meeting_id, agent_id)

        merged_shared = [*persisted.get("shared", []), *provided_shared]
        merged_agent = [*persisted.get("agent", []), *provided_agent]
        injection = memory_service.build_injection(
            meeting_id=meeting_id,
            turn_id=turn_id,
            agent_id=agent_id,
            role=role,
            query=query,
            shared_memory=merged_shared,
            agent_memory=merged_agent,
        )
        return {
            "schema_version": 1,
            "tenant_id": tenant_id,
            "meeting_id": meeting_id,
            "turn_id": turn_id,
            "agent_id": agent_id,
            "role": role,
            "query": query,
            "shared_memory": deepcopy(merged_shared),
            "agent_memory": deepcopy(merged_agent),
            "prompt": injection["prompt"],
            "memory_namespace": {
                "shared": f"{tenant_id}:{meeting_id}:shared",
                "agent": f"{tenant_id}:{meeting_id}:{agent_id}",
            },
        }

    def _resolve(self, value: Any) -> Any:
        if isinstance(value, str) and self._canvas.is_reff(value):
            return self._canvas.get_variable_value(value)
        return value

    @timeout(int(os.environ.get("COMPONENT_EXEC_TIMEOUT", 10 * 60)))
    def _invoke(self, **kwargs):
        tenant_id = self._param.tenant_id or self._canvas.get_tenant_id()
        query = self._resolve(self._param.query)
        shared_memory = self._resolve(self._param.shared_memory)
        agent_memory = self._resolve(self._param.agent_memory)
        context = self.build_context(
            tenant_id=tenant_id,
            meeting_id=self._param.meeting_id,
            turn_id=self._param.turn_id,
            agent_id=self._param.agent_id,
            role=self._param.role,
            query=query,
            shared_memory=shared_memory,
            agent_memory=agent_memory,
            load_persisted_memory=bool(self._param.load_persisted_memory),
        )
        self.set_output("meeting_context", context)
        self.set_output("prompt", context["prompt"])


class MemoryInjectParam(ComponentParamBase):
    def __init__(self):
        super().__init__()
        self.meeting_context = {}
        self.content = ""
        self.scope = "agent"
        self.source = "agent"
        self.run_id = ""
        self.role = ""
        self.metadata = {}
        self.outputs = {
            "meeting_context": {"value": {}, "type": "MeetingContext"},
            "content": {"value": "", "type": "string"},
            "memory_delta": {"value": {}, "type": "JSON"},
        }
        self.input_schema = {
            "meeting_context": {"type": "MeetingContext", "required": True},
            "content": {"type": "string", "required": True},
        }

    def check(self):
        self.check_valid_value(self.scope, "[MemoryInject] Scope", ["shared", "agent"])


class MemoryInject(ComponentBase, ABC):
    component_name = "MemoryInject"

    @staticmethod
    def build_memory_delta(
        meeting_context: dict[str, Any],
        content: str,
        *,
        scope: str = "agent",
        source: str = "agent",
        run_id: str = "",
        role: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        context = _as_dict(meeting_context)
        return {
            "schema_version": 1,
            "tenant_id": _text(context.get("tenant_id")),
            "meeting_id": _text(context.get("meeting_id")),
            "turn_id": _text(context.get("turn_id")),
            "agent_id": _text(context.get("agent_id")),
            "role": _text(role or context.get("role")),
            "scope": scope,
            "source": _text(source),
            "run_id": _text(run_id),
            "content": str(content or ""),
            "metadata": _as_dict(metadata),
        }

    @staticmethod
    def append_memory(delta: dict[str, Any], memory_service=AgentMeetingMemoryService) -> dict[str, Any]:
        if not delta.get("tenant_id") or not delta.get("meeting_id") or not delta.get("turn_id"):
            raise ValueError("MemoryInject requires tenant_id, meeting_id, and turn_id in meeting_context")
        if not delta.get("content"):
            raise ValueError("MemoryInject requires non-empty content")
        if delta.get("scope") == "shared":
            memory_service.append_shared(
                delta["tenant_id"],
                delta["meeting_id"],
                turn_id=delta["turn_id"],
                content=delta["content"],
                source=delta["source"] or "agent",
                metadata=delta.get("metadata") or {},
            )
        else:
            if not delta.get("agent_id"):
                raise ValueError("MemoryInject agent scope requires agent_id in meeting_context")
            memory_service.append_agent(
                delta["tenant_id"],
                delta["meeting_id"],
                delta["agent_id"],
                turn_id=delta["turn_id"],
                content=delta["content"],
                role=delta.get("role") or "",
                run_id=delta.get("run_id") or "",
                metadata=delta.get("metadata") or {},
            )
        return deepcopy(delta)

    @staticmethod
    def apply_delta_to_context(meeting_context: dict[str, Any], delta: dict[str, Any]) -> dict[str, Any]:
        context = _as_dict(meeting_context)
        key = "shared_memory" if delta.get("scope") == "shared" else "agent_memory"
        context.setdefault(key, [])
        context[key].append(deepcopy(delta))
        return context

    def _resolve(self, value: Any) -> Any:
        if isinstance(value, str) and self._canvas.is_reff(value):
            return self._canvas.get_variable_value(value)
        return value

    @timeout(int(os.environ.get("COMPONENT_EXEC_TIMEOUT", 10 * 60)))
    def _invoke(self, **kwargs):
        context = self._resolve(self._param.meeting_context)
        content = self._resolve(self._param.content)
        delta = self.build_memory_delta(
            context if isinstance(context, dict) else {},
            str(content or ""),
            scope=self._param.scope,
            source=self._param.source,
            run_id=self._param.run_id,
            role=self._param.role,
            metadata=self._param.metadata,
        )
        self.append_memory(delta)
        updated_context = self.apply_delta_to_context(context if isinstance(context, dict) else {}, delta)
        self.set_output("meeting_context", updated_context)
        self.set_output("content", delta["content"])
        self.set_output("memory_delta", delta)


class AgentFanoutParam(ComponentParamBase):
    def __init__(self):
        super().__init__()
        self.meeting_context = {}
        self.content = ""
        self.agents = []
        self.files = []
        self.shared_context = ""
        self.base_inputs = {}
        self.user_id = ""
        self.release = True
        self.return_trace = True
        self.enqueue = True
        self.outputs = {
            "runs": {"value": [], "type": "Array<AgentRunRef>"},
            "dispatch": {"value": {}, "type": "JSON"},
            "meeting_context": {"value": {}, "type": "MeetingContext"},
        }
        self.input_schema = {
            "meeting_context": {"type": "MeetingContext", "required": True},
            "content": {"type": "string", "required": True},
            "agents": {"type": "Array<JSON>", "required": True},
            "files": {"type": "Array<FileAsset>", "required": False},
            "base_inputs": {"type": "JSON", "required": False},
        }
        self.runtime_capabilities = {"long_running": True, "uses_external_io": True}

    def check(self):
        self.check_boolean(bool(self.release), "[AgentFanout] Release")
        self.check_boolean(bool(self.return_trace), "[AgentFanout] Return trace")
        self.check_boolean(bool(self.enqueue), "[AgentFanout] Enqueue")


class AgentFanout(ComponentBase, ABC):
    component_name = "AgentFanout"

    @staticmethod
    def normalize_run_refs(dispatch_result: dict[str, Any]) -> list[dict[str, Any]]:
        result = _as_dict(dispatch_result)
        meeting_id = _text(result.get("meeting_id"))
        turn_id = _text(result.get("turn_id"))
        refs = []
        for item in _as_list(result.get("runs")):
            if not isinstance(item, dict):
                continue
            metadata = _as_dict(item.get("metadata"))
            refs.append(
                {
                    "schema_version": 1,
                    "run_id": _text(item.get("run_id")),
                    "agent_id": _text(item.get("agent_id") or metadata.get("agent_id")),
                    "session_id": _text(item.get("session_id")),
                    "message_id": _text(item.get("message_id")),
                    "status": _text(item.get("status")),
                    "queued": bool(item.get("queued")),
                    "meeting_id": _text(metadata.get("meeting_id") or meeting_id),
                    "turn_id": _text(metadata.get("turn_id") or turn_id),
                    "role": _text(metadata.get("role")),
                    "metadata": metadata,
                }
            )
        return refs

    @staticmethod
    def start_fanout(
        *,
        tenant_id: str,
        meeting_context: dict[str, Any],
        content: str,
        agents: list[dict[str, Any]],
        files: list[dict[str, Any]] | None = None,
        shared_context: str = "",
        base_inputs: dict[str, Any] | None = None,
        user_id: str = "",
        release: bool = True,
        return_trace: bool = True,
        enqueue: bool = True,
        scheduler=AgentMeetingSchedulerService,
    ) -> dict[str, Any]:
        context = _as_dict(meeting_context)
        tenant_id = _text(tenant_id or context.get("tenant_id"))
        if not tenant_id:
            raise ValueError("AgentFanout requires tenant_id")
        query = str(content or context.get("query") or "")
        if not query:
            raise ValueError("AgentFanout requires non-empty content")
        result = scheduler.start_parallel_runs(
            tenant_id=tenant_id,
            meeting_id=_text(context.get("meeting_id")),
            turn_id=_text(context.get("turn_id")),
            query=query,
            agents=agents,
            files=files or [],
            shared_context=shared_context,
            shared_memory=_as_list(context.get("shared_memory")),
            base_inputs=base_inputs or {},
            user_id=user_id or tenant_id,
            release=release,
            return_trace=return_trace,
            enqueue=enqueue,
        )
        return deepcopy(result)

    def _resolve(self, value: Any) -> Any:
        if isinstance(value, str) and self._canvas.is_reff(value):
            return self._canvas.get_variable_value(value)
        return value

    @timeout(int(os.environ.get("COMPONENT_EXEC_TIMEOUT", 10 * 60)))
    def _invoke(self, **kwargs):
        context = self._resolve(self._param.meeting_context)
        content = self._resolve(self._param.content)
        agents = _as_list(self._resolve(self._param.agents))
        files = _as_list(self._resolve(self._param.files))
        base_inputs = _as_dict(self._resolve(self._param.base_inputs))
        dispatch = self.start_fanout(
            tenant_id=self._canvas.get_tenant_id(),
            meeting_context=context if isinstance(context, dict) else {},
            content=str(content or ""),
            agents=agents,
            files=files,
            shared_context=self._param.shared_context,
            base_inputs=base_inputs,
            user_id=self._param.user_id,
            release=bool(self._param.release),
            return_trace=bool(self._param.return_trace),
            enqueue=bool(self._param.enqueue),
        )
        run_refs = self.normalize_run_refs(dispatch)
        updated_context = _as_dict(context)
        updated_context["meeting_id"] = dispatch.get("meeting_id", updated_context.get("meeting_id"))
        updated_context["turn_id"] = dispatch.get("turn_id", updated_context.get("turn_id"))
        self.set_output("runs", run_refs)
        self.set_output("dispatch", dispatch)
        self.set_output("meeting_context", updated_context)


class ResultAggregatorParam(ComponentParamBase):
    def __init__(self):
        super().__init__()
        self.runs = []
        self.results = []
        self.scores = []
        self.citations = []
        self.memory_delta = {}
        self.outputs = {
            "reply_text": {"value": "", "type": "string"},
            "memory_delta": {"value": {}, "type": "JSON"},
            "citations": {"value": [], "type": "Array<JSON>"},
            "score_result": {"value": {}, "type": "ScoreResult"},
            "run_id": {"value": "", "type": "string"},
            "report": {"value": "", "type": "string"},
        }
        self.input_schema = {
            "runs": {"type": "Array<AgentRunRef>", "required": False},
            "results": {"type": "Array<JSON>", "required": False},
            "scores": {"type": "Array<ScoreResult>", "required": False},
            "citations": {"type": "Array<JSON>", "required": False},
            "memory_delta": {"type": "JSON", "required": False},
        }

    def check(self):
        return True


class ResultAggregator(ComponentBase, ABC):
    component_name = "ResultAggregator"

    @staticmethod
    def _extract_reply(item: dict[str, Any]) -> str:
        for key in ("reply_text", "content", "answer", "report", "message"):
            value = item.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        messages = item.get("messages")
        if isinstance(messages, list):
            texts = []
            for message in messages:
                if isinstance(message, dict):
                    text = message.get("content") or message.get("answer")
                    if text:
                        texts.append(str(text))
            return "\n".join(texts).strip()
        return ""

    @staticmethod
    def _extract_score(item: dict[str, Any]) -> dict[str, Any] | None:
        nested = item.get("score_result")
        if isinstance(nested, dict):
            return nested
        if any(key in item for key in ("score", "self_score", "rubric_scores")):
            return item
        return None

    @staticmethod
    def _score_value(score: dict[str, Any]) -> float | None:
        for key in ("score", "self_score", "result"):
            try:
                if score.get(key) is not None:
                    return float(score.get(key))
            except Exception:
                continue
        return None

    @classmethod
    def merge_scores(cls, scores: list[dict[str, Any]]) -> dict[str, Any]:
        cleaned = [score for score in scores if isinstance(score, dict)]
        values = [value for value in (cls._score_value(score) for score in cleaned) if value is not None]
        rubric_buckets: dict[str, list[float]] = {}
        for score in cleaned:
            rubric = score.get("rubric_scores") or {}
            if not isinstance(rubric, dict):
                continue
            for key, value in rubric.items():
                try:
                    rubric_buckets.setdefault(str(key), []).append(float(value))
                except Exception:
                    continue
        rubric_scores = {
            key: round(sum(values) / len(values), 2)
            for key, values in rubric_buckets.items()
            if values
        }
        aggregate = round(sum(values) / len(values), 2) if values else 0
        return {
            "schema_version": 1,
            "source": "result_aggregator",
            "score": aggregate,
            "self_score": aggregate,
            "rubric_scores": rubric_scores,
            "items": deepcopy(cleaned),
        }

    @staticmethod
    def dedupe_citations(citations: list[Any]) -> list[dict[str, Any]]:
        def stable_key(value: Any) -> str:
            if isinstance(value, (dict, list, tuple)):
                return json.dumps(value, ensure_ascii=False, sort_keys=True)
            return str(value or "")

        seen = set()
        result = []
        for item in citations:
            if not isinstance(item, dict):
                continue
            key = (
                stable_key(item.get("source_ref")),
                stable_key(item.get("file_id") or item.get("document_id")),
                stable_key(item.get("chunk_id")),
                stable_key(item.get("page") if item.get("page") is not None else item.get("page_num_int")),
            )
            if key in seen:
                continue
            seen.add(key)
            result.append(deepcopy(item))
        return result

    @classmethod
    def aggregate_results(
        cls,
        *,
        runs: list[dict[str, Any]] | None = None,
        results: list[dict[str, Any]] | None = None,
        scores: list[dict[str, Any]] | None = None,
        citations: list[dict[str, Any]] | None = None,
        memory_delta: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        runs = [item for item in _as_list(runs) if isinstance(item, dict)]
        results = [item for item in _as_list(results) if isinstance(item, dict)]
        explicit_scores = [item for item in _as_list(scores) if isinstance(item, dict)]
        extracted_scores = []
        reply_parts = []
        all_citations = _as_list(citations)

        for item in results:
            reply = cls._extract_reply(item)
            if reply:
                role = item.get("role") or item.get("agent_id")
                reply_parts.append(f"{role}: {reply}" if role else reply)
            score = cls._extract_score(item)
            if score:
                extracted_scores.append(score)
            if isinstance(item.get("citations"), list):
                all_citations.extend(item["citations"])

        run_ids = [_text(item.get("run_id")) for item in runs if item.get("run_id")]
        if not run_ids:
            run_ids = [_text(item.get("run_id")) for item in results if item.get("run_id")]
        reply_text = "\n".join(reply_parts).strip()
        score_result = cls.merge_scores([*explicit_scores, *extracted_scores])
        citations_result = cls.dedupe_citations(all_citations)
        return {
            "schema_version": 1,
            "reply_text": reply_text,
            "memory_delta": _as_dict(memory_delta),
            "citations": citations_result,
            "score_result": score_result,
            "run_id": ",".join(run_ids),
            "run_ids": run_ids,
            "report": reply_text,
        }

    def _resolve(self, value: Any) -> Any:
        if isinstance(value, str) and self._canvas.is_reff(value):
            return self._canvas.get_variable_value(value)
        return value

    @timeout(int(os.environ.get("COMPONENT_EXEC_TIMEOUT", 10 * 60)))
    def _invoke(self, **kwargs):
        aggregated = self.aggregate_results(
            runs=_as_list(self._resolve(self._param.runs)),
            results=_as_list(self._resolve(self._param.results)),
            scores=_as_list(self._resolve(self._param.scores)),
            citations=_as_list(self._resolve(self._param.citations)),
            memory_delta=_as_dict(self._resolve(self._param.memory_delta)),
        )
        self.set_output("reply_text", aggregated["reply_text"])
        self.set_output("memory_delta", aggregated["memory_delta"])
        self.set_output("citations", aggregated["citations"])
        self.set_output("score_result", aggregated["score_result"])
        self.set_output("run_id", aggregated["run_id"])
        self.set_output("report", aggregated["report"])
