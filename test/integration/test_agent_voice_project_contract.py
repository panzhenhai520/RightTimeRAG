import json

from agent.tools.retrieval import Retrieval
from api.db.services import agent_document_write_coordinator_service
from api.db.services import agent_meeting_scheduler_service
from api.db.services.agent_document_write_coordinator_service import AgentDocumentWriteCoordinatorService
from api.db.services.agent_meeting_scheduler_service import AgentMeetingSchedulerService
from api.db.services.agent_public_response_service import AgentPublicResponseService
from api.db.services.agent_run_service import AgentRunStatus


class FakeRedis:
    def __init__(self):
        self.store = {}

    def get(self, key):
        return self.store.get(key)

    def set_obj(self, key, value, ttl=None):
        self.store[key] = json.dumps(value, ensure_ascii=False)
        return True


class FakeMemoryService:
    @staticmethod
    def get_context(tenant_id, meeting_id, agent_id):
        return {
            "shared": [{"turn_id": "turn-0", "content": f"shared:{meeting_id}"}],
            "agent": [{"turn_id": "turn-0", "agent_id": agent_id, "content": f"private:{agent_id}"}],
        }

    @staticmethod
    def build_injection(**kwargs):
        return {**kwargs, "prompt": f"{kwargs['meeting_id']}|{kwargs['turn_id']}|{kwargs['agent_id']}|{kwargs['role']}"}


class FakeRunService:
    started = []
    failed = []

    @classmethod
    def reset(cls):
        cls.started = []
        cls.failed = []

    @classmethod
    def start(cls, *args, **kwargs):
        cls.started.append((args, kwargs))

    @classmethod
    def fail(cls, tenant_id, run_id, error):
        cls.failed.append((tenant_id, run_id, error))


class FakeQueueService:
    enqueued = []
    fail_agent_id = ""

    @classmethod
    def reset(cls):
        cls.enqueued = []
        cls.fail_agent_id = ""

    @classmethod
    def build_payload(cls, **kwargs):
        return {"schema_version": 1, **kwargs}

    @classmethod
    def enqueue(cls, payload):
        if payload["agent_id"] == cls.fail_agent_id:
            return False
        cls.enqueued.append(payload)
        return True


def _patch_meeting_services(monkeypatch):
    FakeRunService.reset()
    FakeQueueService.reset()
    monkeypatch.setattr(agent_meeting_scheduler_service, "AgentMeetingMemoryService", FakeMemoryService)
    monkeypatch.setattr(agent_meeting_scheduler_service, "AgentRunService", FakeRunService)
    monkeypatch.setattr(agent_meeting_scheduler_service, "AgentRunQueueService", FakeQueueService)


def test_voice_project_contract_single_teacher_response_shape():
    response = AgentPublicResponseService.from_final_answer(
        agent_id="teacher-technical",
        workflow_id="workflow-classroom",
        run_id="run-1",
        session_id="session-1",
        message_id="message-1",
        final_answer={
            "event": "message_end",
            "data": {
                "content": "请先听一遍，再跟读。",
                "structured": {
                    "answer": "请先听一遍，再跟读。",
                    "intention": "teach",
                    "target": "student",
                    "confidence": 0.91,
                    "knowledge_used": [{"doc_id": "course-1", "chunk_id": "chunk-1"}],
                    "suggested_next_action": "ask_student_repeat",
                },
                "reference": {"chunks": [{"chunk_id": "chunk-1", "doc_id": "course-1", "kb_id": "kb-course", "content": "教学材料"}]},
            },
        },
        trace={
            "state": {"status": "succeeded", "metadata": {"workflow_id": "workflow-classroom"}},
            "workflow": {"status": "succeeded", "context_hash": "h" * 64, "constraint_hash": "c" * 64},
            "nodes": [{"component_id": "LLM:Answer", "component_name": "LLM", "component_type": "LLM", "status": "succeeded"}],
        },
    )

    assert response["answer"] == "请先听一遍，再跟读。"
    assert response["intention"] == "teach"
    assert response["target"] == "student"
    assert response["run_id"] == "run-1"
    assert response["session_id"] == "session-1"
    assert response["references"][0]["dataset_id"] == "kb-course"
    assert response["trace_summary"]["workflow_id"] == "workflow-classroom"
    assert "thoughts" not in json.dumps(response, ensure_ascii=False)


def test_voice_project_contract_four_teacher_fanout_isolated_and_one_failure_does_not_block(monkeypatch):
    _patch_meeting_services(monkeypatch)
    FakeQueueService.fail_agent_id = "teacher-assessment"
    ids = iter([f"id-{idx}" for idx in range(1, 30)])

    result = AgentMeetingSchedulerService.start_parallel_runs(
        tenant_id="tenant-1",
        meeting_id="meeting-1",
        turn_id="turn-1",
        query="给学生讲一句英文",
        agents=[
            {"agent_id": "teacher-technical", "workflow_id": "workflow-technical", "role": "technical_teacher"},
            {"agent_id": "teacher-pronunciation", "workflow_id": "workflow-pronunciation", "role": "pronunciation_teacher"},
            {"agent_id": "teacher-curriculum", "workflow_id": "workflow-curriculum", "role": "curriculum_teacher"},
            {"agent_id": "teacher-assessment", "workflow_id": "workflow-assessment", "role": "assessment_teacher"},
        ],
        shared_context="学生刚读完一句英文",
        base_inputs={"meeting_topic": "English speaking lesson", "target_audience": "adult beginner student"},
        uuid_factory=lambda: next(ids),
    )

    assert len(result["runs"]) == 4
    assert sum(1 for item in result["runs"] if item["status"] == AgentRunStatus.QUEUED) == 3
    assert sum(1 for item in result["runs"] if item["status"] == AgentRunStatus.FAILED) == 1
    assert len(FakeQueueService.enqueued) == 3
    assert len(FakeRunService.failed) == 1
    run_ids = {item["run_id"] for item in result["runs"]}
    session_ids = {item["session_id"] for item in result["runs"]}
    assert len(run_ids) == 4
    assert len(session_ids) == 4
    for payload in FakeQueueService.enqueued:
        assert payload["inputs"]["meeting_id"] == "meeting-1"
        assert payload["inputs"]["meeting_context"] == "学生刚读完一句英文"
        assert payload["inputs"]["target_audience"] == "adult beginner student"
        assert payload["metadata"]["memory_namespace"]["agent"].endswith(payload["agent_id"])


def test_voice_project_contract_dataset_scope_and_error_degrade():
    assert Retrieval._apply_request_dataset_scope(["kb-private-a"], ["kb-private-b"]) == []
    chunk = Retrieval._enrich_standard_metadata(
        {
            "content": "课程标准要求先听辨，再跟读。",
            "document_metadata": {"standard_type": "course_standard", "version": "2026", "effective_from": "2026-01-01"},
        }
    )
    timeout_error = AgentPublicResponseService.normalize_error("AGENT_TIMEOUT", "deadline exceeded", retryable=True)

    assert chunk["standard_metadata"]["version"] == "2026"
    assert chunk["metadata_incomplete"] is False
    assert timeout_error["retryable"] is True
    assert timeout_error["code"] == "AGENT_TIMEOUT"


def test_voice_project_contract_patch_proposal_write_and_rollback(monkeypatch):
    monkeypatch.setattr(agent_document_write_coordinator_service, "REDIS_CONN", FakeRedis())
    AgentDocumentWriteCoordinatorService.publish_snapshot(
        tenant_id="tenant-1",
        document_id="shared-lesson-plan",
        version=1,
        content="第一步：听辨。\n",
        audit={"operator": "voice-project"},
    )
    proposal = AgentDocumentWriteCoordinatorService.build_patch_proposal(
        proposal_id="proposal-1",
        base_document_id="shared-lesson-plan",
        base_version=1,
        agent_id="teacher-pronunciation",
        run_id="run-pronunciation-1",
        summary="增加跟读练习",
        patches=[{"operation": "append", "text": "第二步：分块跟读。\n"}],
        references=[{"doc_id": "course-1", "chunk_id": "chunk-12"}],
    )
    AgentDocumentWriteCoordinatorService.submit_patch_proposal(
        tenant_id="tenant-1",
        proposal=proposal,
        authorized_agent_ids=["teacher-pronunciation"],
    )
    write_result = AgentDocumentWriteCoordinatorService.apply_write_request(
        tenant_id="tenant-1",
        document_id="shared-lesson-plan",
        expected_version=1,
        selected_proposals=["proposal-1"],
        audit={"operator": "god-coordinator", "meeting_id": "meeting-1", "turn_id": "turn-1"},
        authorized_agent_ids=["teacher-pronunciation"],
    )
    rollback = AgentDocumentWriteCoordinatorService.rollback(
        tenant_id="tenant-1",
        document_id="shared-lesson-plan",
        target_version=1,
        expected_version=2,
        audit={"operator": "god-coordinator"},
    )
    audit = AgentDocumentWriteCoordinatorService.list_audit(tenant_id="tenant-1", document_id="shared-lesson-plan")

    assert write_result["new_version"] == 2
    assert rollback["new_version"] == 3
    assert [item["event"] for item in audit] == ["snapshot_published", "proposal_submitted", "write_applied", "rollback_applied"]
