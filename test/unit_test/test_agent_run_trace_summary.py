import importlib.util
import sys
import types
from pathlib import Path


def load_agent_run_service():
    storage = {}

    class FakeRedis:
        def get(self, key):
            return storage.get(key)

        def set_obj(self, key, value, ttl=None):
            import json

            storage[key] = json.dumps(value)

        def set(self, key, value, ttl=None):
            storage[key] = value

        def sadd(self, key, member):
            storage.setdefault(key, set()).add(member)

        def srem(self, key, member):
            if key in storage and isinstance(storage[key], set):
                storage[key].discard(member)

        def smembers(self, key):
            return storage.get(key, set())

    fake_redis_module = types.ModuleType("rag.utils.redis_conn")
    fake_redis_module.REDIS_CONN = FakeRedis()
    sys.modules["rag.utils.redis_conn"] = fake_redis_module
    path = Path(__file__).resolve().parents[2] / "api/db/services/agent_run_service.py"
    spec = importlib.util.spec_from_file_location("agent_run_service_for_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.AgentRunService, module.AgentRunStatus


def test_agent_run_trace_summary_redacts_and_collects_downloads():
    AgentRunService, _ = load_agent_run_service()
    state = {"run_id": "run1", "status": "succeeded"}
    events = [
        {
            "seq": 0,
            "event": {
                "event": "node_started",
                "data": {
                    "component_id": "n1",
                    "component_name": "ExeSQL",
                    "component_type": "ExeSQL",
                    "thoughts": "running",
                },
            },
        },
        {
            "seq": 1,
            "event": {
                "event": "node_finished",
                "data": {
                    "component_id": "n1",
                    "component_name": "ExeSQL",
                    "component_type": "ExeSQL",
                    "inputs": {"password": "secret", "sql": "SELECT 1"},
                    "outputs": {
                        "content": "x" * 800,
                        "downloads": [{"doc_id": "d1", "filename": "a.xlsx"}],
                    },
                    "error": None,
                    "elapsed_time": 1.2,
                },
            },
        },
    ]

    summary = AgentRunService.summarize_events(state, events)

    assert summary["state"] == state
    assert summary["nodes"][0]["status"] == "succeeded"
    assert summary["nodes"][0]["inputs"]["password"] == "***"
    assert summary["nodes"][0]["outputs"]["content"]["length"] == 800
    assert summary["downloads"] == [{"artifact_id": "d1", "doc_id": "d1", "filename": "a.xlsx"}]


def test_agent_run_service_persists_state_and_incremental_events():
    AgentRunService, AgentRunStatus = load_agent_run_service()

    state = AgentRunService.start(
        "tenant-1",
        "run-1",
        "agent-1",
        "session-1",
        "message-1",
        "task-1",
        "hello",
    )
    AgentRunService.append_event("tenant-1", "run-1", {"event": "message", "data": {"content": "a"}})
    AgentRunService.append_event("tenant-1", "run-1", {"event": "workflow_finished", "data": {"outputs": {}}})
    AgentRunService.finish("tenant-1", "run-1")

    stored_state = AgentRunService.get_state("tenant-1", "run-1")
    events = AgentRunService.get_events("tenant-1", "run-1", after_seq=0)

    assert state["status"] == AgentRunStatus.RUNNING
    assert stored_state["status"] == AgentRunStatus.SUCCEEDED
    assert stored_state["event_count"] == 2
    assert len(events) == 1
    assert events[0]["seq"] == 1


def test_agent_run_service_lists_active_runs_by_agent_and_session():
    AgentRunService, AgentRunStatus = load_agent_run_service()

    AgentRunService.start(
        "tenant-1",
        "run-a",
        "agent-1",
        "session-a",
        "message-1",
        "task-1",
        "hello",
        status=AgentRunStatus.QUEUED,
    )
    AgentRunService.start(
        "tenant-1",
        "run-b",
        "agent-1",
        "session-b",
        "message-2",
        "task-2",
        "hello",
    )

    active_for_agent = AgentRunService.list_active("tenant-1", "agent-1")
    active_for_session = AgentRunService.list_active("tenant-1", "agent-1", session_id="session-a")
    AgentRunService.finish("tenant-1", "run-a")
    active_after_finish = AgentRunService.list_active("tenant-1", "agent-1")

    assert {item["run_id"] for item in active_for_agent} == {"run-a", "run-b"}
    assert [item["run_id"] for item in active_for_session] == ["run-a"]
    assert [item["run_id"] for item in active_after_finish] == ["run-b"]


def test_agent_run_finish_after_cancel_request_marks_canceled():
    AgentRunService, AgentRunStatus = load_agent_run_service()

    AgentRunService.start(
        "tenant-1",
        "run-cancel",
        "agent-1",
        "session-1",
        "message-1",
        "task-1",
        "hello",
    )
    assert AgentRunService.request_cancel("tenant-1", "run-cancel") is True

    AgentRunService.finish("tenant-1", "run-cancel")

    assert AgentRunService.get_state("tenant-1", "run-cancel")["status"] == AgentRunStatus.CANCELED


def test_agent_run_artifacts_are_extracted_from_events():
    AgentRunService, _ = load_agent_run_service()

    AgentRunService.start(
        "tenant-1",
        "run-artifacts",
        "agent-1",
        "session-1",
        "message-1",
        "task-1",
        "hello",
    )
    AgentRunService.append_event(
        "tenant-1",
        "run-artifacts",
        {
            "event": "message_end",
            "data": {
                "downloads": [
                    {
                        "doc_id": "doc-1",
                        "filename": "report.docx",
                        "mime_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                        "size": 256,
                    }
                ]
            },
        },
    )

    assert AgentRunService.get_artifacts("tenant-1", "run-artifacts") == [
        {
            "artifact_id": "doc-1",
            "doc_id": "doc-1",
            "filename": "report.docx",
            "mime_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "size": 256,
        }
    ]


def test_agent_run_artifacts_keep_run_and_node_metadata():
    AgentRunService, _ = load_agent_run_service()

    events = [
        {
            "seq": 0,
            "event": {
                "event": "node_finished",
                "data": {
                    "component_id": "DocGenerator:Report",
                    "outputs": {
                        "downloads": [
                            {
                                "artifact_id": "artifact-1",
                                "doc_id": "doc-1",
                                "filename": "report.docx",
                                "download_url": "/v1/agents/download?id=doc-1",
                                "metadata": {
                                    "run_id": "run-1",
                                    "node_id": "DocGenerator:Report",
                                },
                            }
                        ]
                    },
                },
            },
        }
    ]

    summary = AgentRunService.summarize_events({"run_id": "run-1"}, events)

    assert summary["downloads"] == [
        {
            "artifact_id": "artifact-1",
            "doc_id": "doc-1",
            "filename": "report.docx",
            "download_url": "/v1/agents/download?id=doc-1",
            "metadata": {
                "run_id": "run-1",
                "node_id": "DocGenerator:Report",
            },
            "run_id": "run-1",
            "node_id": "DocGenerator:Report",
        }
    ]


def test_agent_run_trace_summarizes_workflow_lifecycle_events():
    AgentRunService, _ = load_agent_run_service()
    state = {"run_id": "run-workflow", "status": "failed"}
    events = [
        {
            "seq": 0,
            "event": {
                "event": "workflow_started",
                "data": {"inputs": {"query": "hello"}, "created_at": 1.0},
            },
        },
        {
            "seq": 1,
            "event": {
                "event": "workflow_failed",
                "data": {"error": "boom", "created_at": 2.0},
            },
        },
    ]

    summary = AgentRunService.summarize_events(state, events)

    assert summary["workflow"]["status"] == "failed"
    assert summary["workflow"]["inputs"] == {"query": "hello"}
    assert summary["workflow"]["error"] == "boom"
    assert summary["errors"] == [{"component_id": None, "component_name": "workflow", "error": "boom"}]


def test_agent_run_state_keeps_progress_snapshot():
    AgentRunService, AgentRunStatus = load_agent_run_service()

    AgentRunService.start(
        "tenant-1",
        "run-progress",
        "agent-1",
        "session-1",
        "message-1",
        "task-1",
        "hello",
        status=AgentRunStatus.QUEUED,
    )
    AgentRunService.append_event(
        "tenant-1",
        "run-progress",
        {
            "event": "workflow_started",
            "data": {"inputs": {"query": "hello"}},
        },
    )
    AgentRunService.append_event(
        "tenant-1",
        "run-progress",
        {
            "event": "node_started",
            "data": {
                "component_id": "n1",
                "component_name": "LLM",
                "component_type": "Generate",
            },
        },
    )

    running_state = AgentRunService.get_state("tenant-1", "run-progress")

    assert running_state["progress"]["percent"] == 0
    assert running_state["progress"]["running_nodes"] == 1
    assert running_state["progress"]["current_nodes"] == [
        {
            "component_id": "n1",
            "component_name": "LLM",
            "component_type": "Generate",
            "thoughts": None,
        }
    ]

    AgentRunService.append_event(
        "tenant-1",
        "run-progress",
        {
            "event": "node_finished",
            "data": {
                "component_id": "n1",
                "component_name": "LLM",
                "component_type": "Generate",
                "outputs": {},
                "error": None,
            },
        },
    )
    AgentRunService.append_event(
        "tenant-1",
        "run-progress",
        {
            "event": "workflow_finished",
            "data": {"outputs": {}},
        },
    )
    AgentRunService.finish("tenant-1", "run-progress")

    finished_state = AgentRunService.get_state("tenant-1", "run-progress")

    assert finished_state["status"] == AgentRunStatus.SUCCEEDED
    assert finished_state["progress"]["percent"] == 1.0
    assert finished_state["progress"]["succeeded_nodes"] == 1
    assert finished_state["progress"]["running_nodes"] == 0


def test_agent_run_trace_handles_node_progress_output_and_failed_events():
    AgentRunService, _ = load_agent_run_service()

    events = [
        {
            "seq": 0,
            "event": {
                "event": "node_started",
                "data": {
                    "component_id": "n1",
                    "component_name": "ExcelProcessor",
                    "component_type": "Process",
                },
            },
        },
        {
            "seq": 1,
            "event": {
                "event": "node_progress",
                "data": {
                    "component_id": "n1",
                    "component_name": "ExcelProcessor",
                    "progress": 0.5,
                    "message": "Reading workbook",
                },
            },
        },
        {
            "seq": 2,
            "event": {
                "event": "node_output",
                "data": {
                    "component_id": "n1",
                    "output": {
                        "download": {
                            "doc_id": "doc-1",
                            "filename": "table.xlsx",
                            "mime_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        }
                    },
                },
            },
        },
        {
            "seq": 3,
            "event": {
                "event": "node_failed",
                "data": {
                    "component_id": "n1",
                    "component_name": "ExcelProcessor",
                    "component_type": "Process",
                    "error": "bad workbook",
                    "inputs": {"file": "input.xlsx"},
                    "outputs": {},
                },
            },
        },
        {
            "seq": 4,
            "event": {
                "event": "node_finished",
                "data": {
                    "component_id": "n1",
                    "component_name": "ExcelProcessor",
                    "component_type": "Process",
                    "error": "bad workbook",
                    "outputs": {},
                },
            },
        },
    ]

    summary = AgentRunService.summarize_events({"run_id": "run-1"}, events)

    assert summary["nodes"][0]["status"] == "failed"
    assert summary["nodes"][0]["progress"] == 0.5
    assert summary["nodes"][0]["message"] == "Reading workbook"
    assert summary["errors"] == [
        {
            "component_id": "n1",
            "component_name": "ExcelProcessor",
            "error": "bad workbook",
        }
    ]
    assert summary["downloads"] == [
        {
            "artifact_id": "doc-1",
            "doc_id": "doc-1",
            "filename": "table.xlsx",
            "mime_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        }
    ]


def test_agent_run_trace_handles_workflow_canceled_as_terminal_state():
    AgentRunService, _ = load_agent_run_service()
    events = [
        {
            "seq": 0,
            "event": {
                "event": "workflow_started",
                "data": {"inputs": {"query": "stop"}},
            },
        },
        {
            "seq": 1,
            "event": {
                "event": "workflow_canceled",
                "data": {"error": "Task has been canceled", "created_at": 2.0},
            },
        },
    ]

    summary = AgentRunService.summarize_events({"run_id": "run-cancel"}, events)

    assert summary["workflow"]["status"] == "canceled"
    assert summary["workflow"]["error"] == "Task has been canceled"
    assert summary["progress"]["percent"] == 1.0
    assert summary["errors"] == []


def test_agent_run_trace_includes_timeline_and_duration():
    AgentRunService, _ = load_agent_run_service()
    state = {"run_id": "run-timeline", "created_at": 10.0, "finished_at": 15.5}
    events = [
        {
            "seq": 0,
            "stored_at": 11.0,
            "event": {
                "event": "workflow_started",
                "data": {"created_at": 10.0},
            },
        },
        {
            "seq": 1,
            "stored_at": 12.0,
            "event": {
                "event": "node_started",
                "data": {
                    "component_id": "n1",
                    "component_name": "LLM",
                    "component_type": "Agent",
                    "created_at": 12.0,
                },
            },
        },
        {
            "seq": 2,
            "stored_at": 15.0,
            "event": {
                "event": "workflow_finished",
                "data": {"created_at": 15.0},
            },
        },
    ]

    summary = AgentRunService.summarize_events(state, events)

    assert summary["duration"] == 5.5
    assert summary["timeline"] == [
        {
            "seq": 0,
            "event_type": "workflow_started",
            "component_id": None,
            "component_name": None,
            "component_type": None,
            "status": "running",
            "stored_at": 11.0,
            "created_at": 10.0,
            "message": None,
            "error": None,
        },
        {
            "seq": 1,
            "event_type": "node_started",
            "component_id": "n1",
            "component_name": "LLM",
            "component_type": "Agent",
            "status": "running",
            "stored_at": 12.0,
            "created_at": 12.0,
            "message": None,
            "error": None,
        },
        {
            "seq": 2,
            "event_type": "workflow_finished",
            "component_id": None,
            "component_name": None,
            "component_type": None,
            "status": "succeeded",
            "stored_at": 15.0,
            "created_at": 15.0,
            "message": None,
            "error": None,
        },
    ]
