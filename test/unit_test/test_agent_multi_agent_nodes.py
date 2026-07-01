import pytest

from agent.component.multi_agent import (
    AgentFanout,
    MeetingContextInput,
    MemoryInject,
    ResultAggregator,
)


class FakeMemoryService:
    shared = []
    agent = []

    @classmethod
    def reset(cls):
        cls.shared = []
        cls.agent = []

    @staticmethod
    def get_context(tenant_id, meeting_id, agent_id):
        return {
            "shared": [{"turn_id": "old", "content": f"shared:{meeting_id}"}],
            "agent": [{"turn_id": "old", "content": f"private:{agent_id}"}],
        }

    @staticmethod
    def build_injection(**kwargs):
        return {
            **kwargs,
            "prompt": f"{kwargs['meeting_id']}|{kwargs['turn_id']}|{kwargs['agent_id']}|{kwargs['role']}",
        }

    @classmethod
    def append_shared(cls, tenant_id, meeting_id, turn_id, content, source="system", metadata=None):
        cls.shared.append(
            {
                "tenant_id": tenant_id,
                "meeting_id": meeting_id,
                "turn_id": turn_id,
                "content": content,
                "source": source,
                "metadata": metadata or {},
            }
        )

    @classmethod
    def append_agent(cls, tenant_id, meeting_id, agent_id, turn_id, content, run_id=None, role="", metadata=None):
        cls.agent.append(
            {
                "tenant_id": tenant_id,
                "meeting_id": meeting_id,
                "agent_id": agent_id,
                "turn_id": turn_id,
                "content": content,
                "run_id": run_id,
                "role": role,
                "metadata": metadata or {},
            }
        )


class FakeScheduler:
    last = None

    @classmethod
    def start_parallel_runs(cls, **kwargs):
        cls.last = kwargs
        return {
            "meeting_id": kwargs["meeting_id"],
            "turn_id": kwargs["turn_id"],
            "runs": [
                {
                    "run_id": f"run-{idx}",
                    "agent_id": spec["agent_id"],
                    "session_id": f"session-{idx}",
                    "message_id": f"message-{idx}",
                    "status": "queued",
                    "queued": kwargs["enqueue"],
                    "metadata": {
                        "meeting_id": kwargs["meeting_id"],
                        "turn_id": kwargs["turn_id"],
                        "agent_id": spec["agent_id"],
                        "role": spec.get("role", ""),
                    },
                }
                for idx, spec in enumerate(kwargs["agents"], start=1)
            ],
        }


def test_meeting_context_input_keeps_agent_memory_isolated():
    context_a = MeetingContextInput.build_context(
        tenant_id="tenant-1",
        meeting_id="meeting-1",
        turn_id="turn-1",
        agent_id="teacher",
        role="英语老师",
        query="教学生读一句英文",
        shared_memory=[{"content": "本节课练习发音"}],
        memory_service=FakeMemoryService,
    )
    context_b = MeetingContextInput.build_context(
        tenant_id="tenant-1",
        meeting_id="meeting-1",
        turn_id="turn-1",
        agent_id="judge",
        role="发音评分",
        query="教学生读一句英文",
        memory_service=FakeMemoryService,
    )

    assert context_a["memory_namespace"]["agent"] == "tenant-1:meeting-1:teacher"
    assert context_b["memory_namespace"]["agent"] == "tenant-1:meeting-1:judge"
    assert context_a["agent_memory"][0]["content"] == "private:teacher"
    assert context_b["agent_memory"][0]["content"] == "private:judge"
    assert "private:judge" not in context_a["prompt"]


def test_memory_inject_appends_to_selected_namespace_only():
    FakeMemoryService.reset()
    context = {
        "tenant_id": "tenant-1",
        "meeting_id": "meeting-1",
        "turn_id": "turn-2",
        "agent_id": "teacher",
        "role": "英语老师",
    }

    shared_delta = MemoryInject.build_memory_delta(context, "学生需要练习 th 音", scope="shared", source="voice")
    agent_delta = MemoryInject.build_memory_delta(context, "老师下一轮先慢读", scope="agent", run_id="run-1")
    MemoryInject.append_memory(shared_delta, memory_service=FakeMemoryService)
    MemoryInject.append_memory(agent_delta, memory_service=FakeMemoryService)

    assert len(FakeMemoryService.shared) == 1
    assert len(FakeMemoryService.agent) == 1
    assert FakeMemoryService.shared[0]["content"] == "学生需要练习 th 音"
    assert FakeMemoryService.agent[0]["agent_id"] == "teacher"
    updated = MemoryInject.apply_delta_to_context(context, agent_delta)
    assert updated["agent_memory"][0]["content"] == "老师下一轮先慢读"


def test_memory_inject_rejects_missing_agent_namespace_for_agent_scope():
    delta = MemoryInject.build_memory_delta(
        {"tenant_id": "tenant-1", "meeting_id": "meeting-1", "turn_id": "turn-1"},
        "no agent",
    )

    with pytest.raises(ValueError, match="agent scope requires agent_id"):
        MemoryInject.append_memory(delta, memory_service=FakeMemoryService)


def test_agent_fanout_returns_independent_run_refs_without_touching_chat_events():
    context = {
        "tenant_id": "tenant-1",
        "meeting_id": "meeting-1",
        "turn_id": "turn-1",
        "query": "教会学生念一段英文",
        "shared_memory": [{"content": "学生是初学者"}],
    }
    dispatch = AgentFanout.start_fanout(
        tenant_id="tenant-1",
        meeting_context=context,
        content="本轮教学",
        agents=[
            {"agent_id": "teacher", "role": "英语老师"},
            {"agent_id": "judge", "role": "发音专家"},
            {"agent_id": "analyst", "role": "学习分析"},
        ],
        enqueue=False,
        scheduler=FakeScheduler,
    )
    refs = AgentFanout.normalize_run_refs(dispatch)

    assert FakeScheduler.last["meeting_id"] == "meeting-1"
    assert FakeScheduler.last["turn_id"] == "turn-1"
    assert FakeScheduler.last["shared_memory"] == [{"content": "学生是初学者"}]
    assert [ref["agent_id"] for ref in refs] == ["teacher", "judge", "analyst"]
    assert all(ref["meeting_id"] == "meeting-1" and ref["turn_id"] == "turn-1" for ref in refs)
    refs[0]["metadata"]["role"] = "mutated"
    assert refs[1]["metadata"]["role"] == "发音专家"


def test_result_aggregator_outputs_unified_shape_and_deduped_citations():
    aggregated = ResultAggregator.aggregate_results(
        runs=[{"run_id": "run-1"}, {"run_id": "run-2"}],
        results=[
            {
                "agent_id": "teacher",
                "reply_text": "先示范，再让学生跟读。",
                "score_result": {"self_score": 86, "rubric_scores": {"fluency": 82}},
                "citations": [{"source_ref": "Fig. 1", "file_id": "doc-1", "chunk_id": "c1"}],
            },
            {
                "agent_id": "judge",
                "content": "学生 th 音需要纠正。",
                "score": 90,
                "rubric_scores": {"fluency": 88},
                "citations": [{"source_ref": "Fig. 1", "file_id": "doc-1", "chunk_id": "c1"}],
            },
        ],
        memory_delta={"content": "本轮已完成"},
    )

    assert aggregated["run_id"] == "run-1,run-2"
    assert aggregated["run_ids"] == ["run-1", "run-2"]
    assert "teacher: 先示范" in aggregated["reply_text"]
    assert "judge: 学生 th 音需要纠正" in aggregated["reply_text"]
    assert aggregated["memory_delta"]["content"] == "本轮已完成"
    assert aggregated["score_result"]["score"] == 88.0
    assert aggregated["score_result"]["rubric_scores"]["fluency"] == 85.0
    assert len(aggregated["citations"]) == 1
