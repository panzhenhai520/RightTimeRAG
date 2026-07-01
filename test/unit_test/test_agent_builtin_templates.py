import importlib.util
import json
from pathlib import Path


def load_validation_service():
    path = Path(__file__).resolve().parents[2] / "api/db/services/agent_validation_service.py"
    spec = importlib.util.spec_from_file_location("agent_validation_service_for_template_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.AgentValidationService


def test_new_business_templates_are_valid_for_publish():
    AgentValidationService = load_validation_service()
    root = Path(__file__).resolve().parents[2]
    templates = [
        root / "agent/templates/legal_document_report_agent.json",
        root / "agent/templates/excel_sql_analysis_agent.json",
        root / "agent/templates/compliance_verification_agent.json",
        root / "agent/templates/ai_teacher_pre_class_workflow.json",
        root / "agent/templates/ai_teacher_classroom_workflow.json",
        root / "agent/templates/ai_teacher_post_class_workflow.json",
        root / "agent/templates/document_compare_agent.json",
        root / "agent/templates/contract_law_conflict_agent.json",
        root / "agent/templates/policy_version_diff_agent.json",
        root / "agent/templates/table_compare_agent.json",
        root / "agent/templates/codex_like_document_edit_agent.json",
        root / "agent/templates/task_planning_assistant.json",
        root / "agent/templates/document_revision_advisor_agent.json",
    ]

    for path in templates:
        payload = json.loads(path.read_text(encoding="utf-8"))
        result = AgentValidationService.validate_for_publish(payload["dsl"])
        assert result["ok"] is True, (path.name, result)
        assert result["errors"] == []


def test_excel_sql_template_uses_explicit_calculation_step():
    root = Path(__file__).resolve().parents[2]
    payload = json.loads((root / "agent/templates/excel_sql_analysis_agent.json").read_text(encoding="utf-8"))
    components = payload["dsl"]["components"]

    aggregate = components["ExcelProcessor:Aggregate"]["obj"]["params"]
    calculate = components["ExcelProcessor:CalculateB"]["obj"]["params"]
    sql = components["ExeSQL:QueryRecords"]["obj"]["params"]["sql"]
    prompt = components["Agent:ExplainData"]["obj"]["params"]["prompts"][0]["content"]

    assert aggregate["operation"] == "aggregate"
    assert aggregate["aggregate_coefficient"] == 1
    assert calculate["operation"] == "calculate"
    assert calculate["calculation_value"] == "{ExcelProcessor:Aggregate@result}"
    assert calculate["calculation_coefficient"] == "{begin@coefficient}"
    assert "{ExcelProcessor:CalculateB@result}" in sql
    assert "{ExcelProcessor:CalculateB@markdown}" in prompt

    edges = {(edge["source"], edge["target"]) for edge in payload["dsl"]["graph"]["edges"]}
    assert ("ExcelProcessor:Aggregate", "ExcelProcessor:CalculateB") in edges
    assert ("ExcelProcessor:CalculateB", "ExeSQL:QueryRecords") in edges


def test_legal_template_exposes_parser_references_to_report_agent():
    root = Path(__file__).resolve().parents[2]
    payload = json.loads((root / "agent/templates/legal_document_report_agent.json").read_text(encoding="utf-8"))
    components = payload["dsl"]["components"]

    outputs = components["FileParser:LegalDocument"]["obj"]["params"]["outputs"]
    prompt = components["Agent:LegalReport"]["obj"]["params"]["prompts"][0]["content"]

    assert outputs["references"]["type"] == "Array<Object>"
    assert "{FileParser:LegalDocument@references}" in prompt


def test_compliance_template_uses_dedicated_verification_nodes():
    root = Path(__file__).resolve().parents[2]
    payload = json.loads((root / "agent/templates/compliance_verification_agent.json").read_text(encoding="utf-8"))
    components = payload["dsl"]["components"]

    required = {
        "ContractClauseExtractor:Clauses": "ContractClauseExtractor",
        "ComplianceChecklistGenerator:Checklist": "ComplianceChecklistGenerator",
        "ClauseMatcher:Match": "ClauseMatcher",
        "ComplianceVerifier:Verify": "ComplianceVerifier",
        "RiskScorer:Risk": "RiskScorer",
        "ComplianceReportComposer:Report": "ComplianceReportComposer",
    }
    for component_id, component_name in required.items():
        assert components[component_id]["obj"]["component_name"] == component_name

    assert components["Retrieval:Standards"]["obj"]["params"]["dataset_ids"] == []
    assert (
        components["ComplianceVerifier:Verify"]["obj"]["params"]["checklist"]
        == "{ComplianceChecklistGenerator:Checklist@checklist}"
    )
    assert components["FileParser:ContractDocument"]["obj"]["params"]["outputs"]["file_info"]["type"] == "Array<Object>"
    assert (
        components["DocGenerator:ComplianceReportDoc"]["obj"]["params"]["content"]
        == "{ComplianceReportComposer:Report@markdown}"
    )


def test_document_compare_templates_use_dedicated_file_compare_nodes():
    root = Path(__file__).resolve().parents[2]
    template_names = [
        "document_compare_agent.json",
        "contract_law_conflict_agent.json",
        "policy_version_diff_agent.json",
        "table_compare_agent.json",
    ]

    for template_name in template_names:
        payload = json.loads((root / f"agent/templates/{template_name}").read_text(encoding="utf-8"))
        component_names = {
            component["obj"]["component_name"]
            for component in payload["dsl"]["components"].values()
        }
        assert "DocumentNormalizer" in component_names, template_name
        assert "DocumentSemanticComparer" in component_names, template_name
        assert "DocumentCompareReportComposer" in component_names, template_name
        assert "Message" in component_names, template_name

    contract = json.loads((root / "agent/templates/contract_law_conflict_agent.json").read_text(encoding="utf-8"))
    contract_components = contract["dsl"]["components"]
    assert contract_components["DocumentConflictDetector:Conflict"]["obj"]["component_name"] == "DocumentConflictDetector"
    assert contract_components["DocumentCompareReportComposer:Report"]["obj"]["params"]["conflicts"] == "{DocumentConflictDetector:Conflict@conflicts}"

    table = json.loads((root / "agent/templates/table_compare_agent.json").read_text(encoding="utf-8"))
    table_components = table["dsl"]["components"]
    assert table_components["TableDiff:Rows"]["obj"]["component_name"] == "TableDiff"
    assert table_components["DocumentCompareReportComposer:Report"]["obj"]["params"]["table_diff"] == "{TableDiff:Rows@table_diff}"


def test_task_planning_templates_use_required_v4_nodes():
    AgentValidationService = load_validation_service()
    root = Path(__file__).resolve().parents[2]
    template_names = [
        "codex_like_document_edit_agent.json",
        "task_planning_assistant.json",
        "document_revision_advisor_agent.json",
    ]
    required = {
        "GoalIntentClassifier",
        "TaskContextCollector",
        "TaskPlanner",
        "PreconditionChecker",
        "TaskExecutor",
        "TaskResultVerifier",
        "ReplanDecider",
        "TaskExecutionReportComposer",
        "Message",
    }

    for template_name in template_names:
        payload = json.loads((root / f"agent/templates/{template_name}").read_text(encoding="utf-8"))
        component_names = {
            component["obj"]["component_name"]
            for component in payload["dsl"]["components"].values()
        }
        result = AgentValidationService.validate_for_publish(payload["dsl"])

        assert required.issubset(component_names), template_name
        assert result["ok"] is True, (template_name, result)
        assert result["errors"] == []

    revision = json.loads((root / "agent/templates/document_revision_advisor_agent.json").read_text(encoding="utf-8"))
    assert any(
        component["obj"]["component_name"] == "DocumentStructureAdvisor"
        for component in revision["dsl"]["components"].values()
    )


def test_ai_teacher_templates_expose_standard_structured_output():
    root = Path(__file__).resolve().parents[2]
    template_names = [
        "ai_teacher_pre_class_workflow.json",
        "ai_teacher_classroom_workflow.json",
        "ai_teacher_post_class_workflow.json",
    ]
    required_fields = {
        "answer",
        "intention",
        "target",
        "confidence",
        "knowledge_used",
        "suggested_next_action",
        "trace_summary",
    }

    for template_name in template_names:
        payload = json.loads((root / f"agent/templates/{template_name}").read_text(encoding="utf-8"))
        components = payload["dsl"]["components"]
        agent_nodes = [
            component
            for component in components.values()
            if component["obj"]["component_name"] == "Agent"
        ]
        assert agent_nodes, template_name
        final_agent = agent_nodes[-1]
        structured = final_agent["obj"]["params"]["outputs"]["structured"]
        assert required_fields.issubset(set(structured["properties"])), template_name
        assert "{sys.external_context}" in json.dumps(final_agent["obj"]["params"], ensure_ascii=False)


def test_ai_teacher_classroom_template_has_context_retrieval_and_quality_gate():
    root = Path(__file__).resolve().parents[2]
    payload = json.loads((root / "agent/templates/ai_teacher_classroom_workflow.json").read_text(encoding="utf-8"))
    components = payload["dsl"]["components"]

    assert components["begin"]["obj"]["component_name"] == "Begin"
    assert components["Retrieval:TeacherAndCourseKnowledge"]["obj"]["component_name"] == "Retrieval"
    assert components["Agent:DraftTurn"]["obj"]["component_name"] == "Agent"
    assert components["Agent:QualityCheck"]["obj"]["component_name"] == "Agent"

    quality_prompt = components["Agent:QualityCheck"]["obj"]["params"]["prompts"][0]["content"]
    system_prompt = components["Agent:DraftTurn"]["obj"]["params"]["sys_prompt"]
    assert "AITeacherTurnContext" in json.dumps(components, ensure_ascii=False)
    assert "target_listener" in system_prompt
    assert "reply_to" in system_prompt
    assert "forbidden_content" in system_prompt
    assert "{Agent:DraftTurn@content}" in quality_prompt
