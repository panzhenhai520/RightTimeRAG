import json

from api.db.services import agent_meeting_memory_service
from api.db.services.agent_meeting_memory_service import AgentMeetingMemoryService


class FakeRedis:
    def __init__(self):
        self.data = {}

    def get(self, key):
        return self.data.get(key)

    def set_obj(self, key, obj, exp=3600):
        self.data[key] = json.dumps(obj, ensure_ascii=False)
        return True


def test_meeting_memory_keeps_shared_and_agent_namespaces_separate(monkeypatch):
    redis = FakeRedis()
    monkeypatch.setattr(agent_meeting_memory_service, "REDIS_CONN", redis)

    AgentMeetingMemoryService.append_shared(
        "tenant-1",
        "meeting-1",
        turn_id="turn-1",
        content="用户想讨论续租策略",
        source="voice",
    )
    AgentMeetingMemoryService.append_agent(
        "tenant-1",
        "meeting-1",
        "agent-a",
        turn_id="turn-1",
        content="关注法律风险",
        role="legal",
        run_id="run-a",
    )
    AgentMeetingMemoryService.append_agent(
        "tenant-1",
        "meeting-1",
        "agent-b",
        turn_id="turn-1",
        content="关注财务测算",
        role="finance",
        run_id="run-b",
    )

    context_a = AgentMeetingMemoryService.get_context("tenant-1", "meeting-1", "agent-a")
    context_b = AgentMeetingMemoryService.get_context("tenant-1", "meeting-1", "agent-b")

    assert context_a["shared"][0]["content"] == "用户想讨论续租策略"
    assert context_b["shared"][0]["content"] == "用户想讨论续租策略"
    assert context_a["agent"][0]["content"] == "关注法律风险"
    assert context_b["agent"][0]["content"] == "关注财务测算"
    assert "关注财务测算" not in AgentMeetingMemoryService.build_injection(
        meeting_id="meeting-1",
        turn_id="turn-2",
        agent_id="agent-a",
        role="legal",
        query="下一轮怎么说",
        shared_memory=context_a["shared"],
        agent_memory=context_a["agent"],
    )["prompt"]
