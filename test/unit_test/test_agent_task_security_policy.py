from api.db.services.agent_task_approval_service import AgentTaskSecurityPolicy


def test_task_security_policy_auto_allows_low_risk_read_task():
    result = AgentTaskSecurityPolicy.assess({"task_id": "task-read", "task_type": "read_file", "risk_level": "low"})

    assert result["allowed"] is True
    assert result["requires_confirmation"] is False
    assert result["denied"] is False


def test_task_security_policy_requires_confirmation_before_write():
    result = AgentTaskSecurityPolicy.assess({"task_id": "task-write", "task_type": "apply_patch", "risk_level": "high"})

    assert result["allowed"] is False
    assert result["requires_confirmation"] is True
    assert "write_requires_confirmation" in result["reasons"]


def test_task_security_policy_can_disable_auto_allow_low_risk():
    result = AgentTaskSecurityPolicy.assess(
        {"task_id": "task-read", "task_type": "read_file", "risk_level": "low"},
        policy={"auto_allow_low_risk": False},
    )

    assert result["allowed"] is False
    assert result["requires_confirmation"] is False
