from api.db.services import agent_meeting_scheduler_service
from api.db.services.agent_meeting_scheduler_service import AgentMeetingSchedulerService
from api.db.services.agent_run_service import AgentRunStatus


class FakeMemoryService:
    @staticmethod
    def get_context(tenant_id, meeting_id, agent_id):
        return {
            "shared": [{"turn_id": "old", "source": "summary", "content": f"shared for {meeting_id}"}],
            "agent": [{"turn_id": "old", "agent_id": agent_id, "content": f"private for {agent_id}"}],
        }

    @staticmethod
    def build_injection(**kwargs):
        return {
            **kwargs,
            "prompt": f"{kwargs['meeting_id']}|{kwargs['turn_id']}|{kwargs['agent_id']}|{kwargs['role']}",
        }


class FakeRunService:
    started = []
    failed = []

    @classmethod
    def start(cls, *args, **kwargs):
        cls.started.append((args, kwargs))

    @classmethod
    def fail(cls, tenant_id, run_id, error):
        cls.failed.append((tenant_id, run_id, error))


class FakeQueueService:
    enqueued = []

    @classmethod
    def build_payload(cls, **kwargs):
        return {"schema_version": 1, **kwargs}

    @classmethod
    def enqueue(cls, payload):
        cls.enqueued.append(payload)
        return True


def test_meeting_scheduler_fans_out_four_independent_agent_runs(monkeypatch):
    FakeRunService.started = []
    FakeRunService.failed = []
    FakeQueueService.enqueued = []
    ids = iter([f"id-{idx}" for idx in range(1, 20)])

    monkeypatch.setattr(agent_meeting_scheduler_service, "AgentMeetingMemoryService", FakeMemoryService)
    monkeypatch.setattr(agent_meeting_scheduler_service, "AgentRunService", FakeRunService)
    monkeypatch.setattr(agent_meeting_scheduler_service, "AgentRunQueueService", FakeQueueService)

    result = AgentMeetingSchedulerService.start_parallel_runs(
        tenant_id="tenant-1",
        meeting_id="meeting-1",
        turn_id="turn-1",
        query="请四个角色分别给出会议话术",
        agents=[
            {"agent_id": "agent-legal", "role": "法律"},
            {"agent_id": "agent-finance", "role": "财务"},
            {"agent_id": "agent-sales", "role": "销售"},
            {"agent_id": "agent-service", "role": "客服"},
        ],
        shared_context="本轮会议上下文",
        shared_memory=[{"turn_id": "turn-0", "content": "上一轮用户关注预算"}],
        uuid_factory=lambda: next(ids),
    )

    assert result["meeting_id"] == "meeting-1"
    assert result["turn_id"] == "turn-1"
    assert len(result["runs"]) == 4
    assert len(FakeQueueService.enqueued) == 4
    assert len(FakeRunService.started) == 4
    assert FakeRunService.failed == []

    payloads = FakeQueueService.enqueued
    assert len({payload["run_id"] for payload in payloads}) == 4
    assert len({payload["session_id"] for payload in payloads}) == 4
    assert len({payload["message_id"] for payload in payloads}) == 4
    assert {payload["agent_id"] for payload in payloads} == {
        "agent-legal",
        "agent-finance",
        "agent-sales",
        "agent-service",
    }

    namespaces = [payload["metadata"]["memory_namespace"]["agent"] for payload in payloads]
    assert len(set(namespaces)) == 4
    for payload in payloads:
        assert payload["inputs"]["meeting_id"] == "meeting-1"
        assert payload["inputs"]["meeting_turn_id"] == "turn-1"
        assert payload["inputs"]["meeting_context"] == "本轮会议上下文"
        assert payload["inputs"]["meeting_memory"]["prompt"].startswith("meeting-1|turn-1|")
        assert payload["metadata"]["meeting_id"] == "meeting-1"
        assert payload["metadata"]["turn_id"] == "turn-1"

    for args, kwargs in FakeRunService.started:
        assert args[0] == "tenant-1"
        assert args[6] == "请四个角色分别给出会议话术"
        assert kwargs["status"] == AgentRunStatus.QUEUED
        assert kwargs["mode"] == "meeting_queue"
        assert kwargs["metadata"]["meeting_id"] == "meeting-1"


def test_meeting_scheduler_rejects_duplicate_agents():
    try:
        AgentMeetingSchedulerService.normalize_agents(
            [{"agent_id": "agent-a"}, {"agent_id": "agent-a"}]
        )
    except ValueError as exc:
        assert "duplicate agent_id" in str(exc)
    else:
        raise AssertionError("duplicate agents should be rejected")
