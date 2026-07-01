from api.db.services.agent_task_model_service import AgentTaskStatus
from api.db.services.agent_task_precondition_service import DependencyResolver


def test_dependency_resolver_blocks_on_incomplete_upstream_task():
    upstream = {"node_id": "task-001", "task_type": "find_file", "status": AgentTaskStatus.PENDING.value}
    task = {"node_id": "task-002", "task_type": "read_document", "depends_on": ["task-001"]}

    result = DependencyResolver.resolve(task, tasks=[upstream])

    assert result["ok"] is False
    assert result["blocked_by"] == [{"task_id": "task-001", "status": "pending", "reason": "upstream_not_completed"}]
    assert result["repair_tasks"][0]["task_type"] == "wait_for_upstream"


def test_dependency_resolver_allows_completed_upstream_task():
    upstream = {"node_id": "task-001", "task_type": "find_file", "status": AgentTaskStatus.COMPLETED.value}
    task = {
        "node_id": "task-002",
        "task_type": "read_document",
        "preconditions": [{"kind": "upstream_task_completed", "task_id": "task-001"}],
    }

    result = DependencyResolver.resolve(task, tasks=[upstream])

    assert result["ok"] is True
    assert result["blocked_by"] == []
    assert result["dependencies"][0]["task_id"] == "task-001"


def test_dependency_resolver_reports_missing_dependency():
    task = {"node_id": "task-002", "task_type": "read_document", "depends_on": ["missing"]}

    result = DependencyResolver.resolve(task, tasks=[])

    assert result["ok"] is False
    assert result["missing_dependencies"] == ["missing"]
    assert result["blocked_by"][0]["reason"] == "missing_dependency"
