from api.db.services.agent_goal_intent_service import AgentGoalIntentService


def test_goal_intent_service_classifies_document_edit_with_missing_context():
    intent = AgentGoalIntentService.classify("把最近上次写的某文档找出来，我要新增任务分解能力")

    assert intent["goal_type"] == "edit_document"
    assert intent["expected_outcome"] == "revision_plan"
    assert intent["risk_level"] == "medium"
    assert intent["missing_inputs"] == []
    assert intent["confidence"] > 0.7


def test_goal_intent_service_classifies_compare_and_missing_pair():
    intent = AgentGoalIntentService.classify("帮我比对合同条款和法律条款有没有冲突")

    assert intent["goal_type"] == "compare_documents"
    assert intent["missing_inputs"] == ["document_a", "document_b"]
    assert intent["expected_outcome"] == "comparison_report"


def test_goal_intent_service_marks_code_or_command_as_high_risk():
    intent = AgentGoalIntentService.classify("执行脚本跑测试并修改代码")

    assert intent["goal_type"] == "run_workflow"
    assert intent["risk_level"] == "high"
    assert intent["requires_user_confirmation"] is True


def test_goal_intent_service_normalizes_invalid_payload():
    normalized = AgentGoalIntentService.normalize(
        {
            "goal_type": "not_real",
            "confidence": 3,
            "risk_level": "danger",
            "missing_inputs": "target_document",
        }
    )

    assert normalized["goal_type"] == "needs_clarification"
    assert normalized["confidence"] == 1.0
    assert normalized["risk_level"] == "low"
    assert normalized["missing_inputs"] == ["target_document"]
