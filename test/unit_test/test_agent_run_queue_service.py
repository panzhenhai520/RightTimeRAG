import pytest

from api.db.services import agent_run_queue_service
from api.db.services.agent_run_queue_service import AgentRunQueueService


class FakeRedisQueue:
    def __init__(self):
        self.produced = []
        self.consumed = []

    def queue_product(self, queue, message):
        self.produced.append((queue, message))
        return True

    def queue_consumer(self, queue_name, group_name, consumer_name, msg_id=b">"):
        self.consumed.append((queue_name, group_name, consumer_name, msg_id))
        return {"queue": queue_name, "group": group_name, "consumer": consumer_name, "msg_id": msg_id}


def make_payload(**overrides):
    payload = AgentRunQueueService.build_payload(
        run_id="run-1",
        tenant_id="tenant-1",
        agent_id="agent-1",
        workflow_id="workflow-1",
        session_id="session-1",
        message_id="message-1",
        query="hello",
        files=[{"id": "file-1"}],
        inputs={"focus": "law"},
        user_id="user-1",
        release=True,
        return_trace=True,
        custom_header="x-test",
        chat_template_kwargs={"temperature": 0},
        deadline_ms=3000,
        metadata={"meeting_id": "meeting-1"},
    )
    payload.update(overrides)
    return payload


def test_agent_run_queue_payload_is_stable_and_serializable():
    payload = make_payload()

    AgentRunQueueService.validate_payload(payload)

    assert payload["schema_version"] == 1
    assert payload["run_id"] == "run-1"
    assert payload["tenant_id"] == "tenant-1"
    assert payload["agent_id"] == "agent-1"
    assert payload["workflow_id"] == "workflow-1"
    assert payload["files"] == [{"id": "file-1"}]
    assert payload["inputs"] == {"focus": "law"}
    assert payload["release"] is True
    assert payload["return_trace"] is True
    assert payload["deadline_ms"] == 3000
    assert payload["metadata"] == {"meeting_id": "meeting-1"}


def test_agent_run_queue_defaults_workflow_id_to_agent_id():
    payload = AgentRunQueueService.build_payload(
        run_id="run-1",
        tenant_id="tenant-1",
        agent_id="agent-1",
        session_id="session-1",
        message_id="message-1",
        query="hello",
    )

    assert payload["workflow_id"] == "agent-1"


def test_agent_run_queue_rejects_missing_required_fields():
    payload = make_payload(run_id="")

    with pytest.raises(ValueError, match="run_id"):
        AgentRunQueueService.validate_payload(payload)


def test_agent_run_queue_rejects_non_json_payload():
    payload = make_payload(inputs={"bad": object()})

    with pytest.raises(ValueError, match="JSON serializable"):
        AgentRunQueueService.validate_payload(payload)


def test_agent_run_queue_enqueue_and_consume_use_redis_stream_boundary(monkeypatch):
    redis = FakeRedisQueue()
    monkeypatch.setattr(agent_run_queue_service, "REDIS_CONN", redis)

    payload = make_payload()
    assert AgentRunQueueService.enqueue(payload) is True
    msg = AgentRunQueueService.consume("worker-1", msg_id="0")

    assert redis.produced == [(AgentRunQueueService.QUEUE_NAME, payload)]
    assert redis.consumed == [(AgentRunQueueService.QUEUE_NAME, AgentRunQueueService.GROUP_NAME, "worker-1", "0")]
    assert msg["consumer"] == "worker-1"
