from api.db.services import agent_run_executor_service
from api.db.services.agent_run_executor_service import AgentRunExecutorService


class FakeRedisMsg:
    def __init__(self, payload):
        self.payload = payload
        self.acked = False

    def get_message(self):
        return self.payload

    def ack(self):
        self.acked = True
        return True


class FakeRunService:
    marked = []
    failed = []

    @classmethod
    def mark_running(cls, tenant_id, run_id):
        cls.marked.append((tenant_id, run_id))

    @classmethod
    def fail(cls, tenant_id, run_id, error):
        cls.failed.append((tenant_id, run_id, error))


def make_payload():
    return {
        "run_id": "run-1",
        "tenant_id": "tenant-1",
        "agent_id": "agent-1",
        "session_id": "session-1",
        "message_id": "message-1",
        "query": "hello",
    }


def test_agent_run_executor_runs_payload_and_acks(monkeypatch):
    payload = make_payload()
    msg = FakeRedisMsg(payload)
    executed = []
    FakeRunService.marked = []
    FakeRunService.failed = []

    monkeypatch.setattr(agent_run_executor_service.AgentRunQueueService, "consume", lambda consumer_name=None, msg_id=b">": msg)
    monkeypatch.setattr(agent_run_executor_service, "AgentRunService", FakeRunService)

    ok = AgentRunExecutorService.run_one(lambda item: executed.append(item), consumer_name="worker-1")

    assert ok is True
    assert executed == [payload]
    assert FakeRunService.marked == [("tenant-1", "run-1")]
    assert FakeRunService.failed == []
    assert msg.acked is True


def test_agent_run_executor_marks_failed_and_acks_on_error(monkeypatch):
    payload = make_payload()
    msg = FakeRedisMsg(payload)
    FakeRunService.marked = []
    FakeRunService.failed = []

    monkeypatch.setattr(agent_run_executor_service.AgentRunQueueService, "consume", lambda consumer_name=None, msg_id=b">": msg)
    monkeypatch.setattr(agent_run_executor_service, "AgentRunService", FakeRunService)

    def fail(_):
        raise RuntimeError("boom")

    ok = AgentRunExecutorService.run_one(fail)

    assert ok is False
    assert FakeRunService.marked == [("tenant-1", "run-1")]
    assert FakeRunService.failed == [("tenant-1", "run-1", "boom")]
    assert msg.acked is True


def test_agent_run_executor_can_consume_pending_messages(monkeypatch):
    payload = make_payload()
    msg = FakeRedisMsg(payload)
    calls = []
    FakeRunService.marked = []
    FakeRunService.failed = []

    def consume(consumer_name=None, msg_id=b">"):
        calls.append((consumer_name, msg_id))
        return msg

    monkeypatch.setattr(agent_run_executor_service.AgentRunQueueService, "consume", consume)
    monkeypatch.setattr(agent_run_executor_service, "AgentRunService", FakeRunService)

    ok = AgentRunExecutorService.run_one(lambda item: None, consumer_name="worker-1", msg_id="0")

    assert ok is True
    assert calls == [("worker-1", "0")]
    assert FakeRunService.marked == [("tenant-1", "run-1")]
    assert msg.acked is True
