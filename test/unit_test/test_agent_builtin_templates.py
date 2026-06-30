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
