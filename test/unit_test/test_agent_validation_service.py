import importlib.util
from pathlib import Path


def load_validation_service():
    path = Path(__file__).resolve().parents[2] / "api/db/services/agent_validation_service.py"
    spec = importlib.util.spec_from_file_location("agent_validation_service_for_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.AgentValidationService


def component(name, params=None, downstream=None, upstream=None):
    return {
        "obj": {
            "component_name": name,
            "params": params or {},
        },
        "downstream": downstream or [],
        "upstream": upstream or [],
    }


def test_publish_validation_allows_basic_agent_flow():
    AgentValidationService = load_validation_service()
    dsl = {
        "components": {
            "begin": component("Begin", downstream=["agent_0"]),
            "agent_0": component(
                "Agent",
                params={"llm_id": "deepseek@test", "prompts": [{"role": "user", "content": "{sys.query}"}]},
                downstream=["message_0"],
                upstream=["begin"],
            ),
            "message_0": component("Message", params={"content": ["{agent_0@answer}"]}, upstream=["agent_0"]),
        }
    }

    result = AgentValidationService.validate_for_publish(dsl)

    assert result["ok"] is True
    assert result["errors"] == []


def test_publish_validation_blocks_missing_llm_and_broken_reference():
    AgentValidationService = load_validation_service()
    dsl = {
        "components": {
            "begin": component("Begin", downstream=["agent_0"]),
            "agent_0": component(
                "Agent",
                params={"llm_id": "", "prompts": [{"role": "user", "content": "{ghost@answer}"}]},
                upstream=["begin"],
            ),
        }
    }

    result = AgentValidationService.validate_for_publish(dsl)
    codes = {item["code"] for item in result["errors"]}

    assert result["ok"] is False
    assert "missing_llm" in codes
    assert "missing_variable_source" in codes


def test_publish_validation_detects_missing_variable_source_with_underscore_id():
    AgentValidationService = load_validation_service()
    dsl = {
        "components": {
            "begin": component("Begin", downstream=["message_0"]),
            "message_0": component(
                "Message",
                params={"content": ["{agent_missing@answer}"]},
                upstream=["begin"],
            ),
        }
    }

    result = AgentValidationService.validate_for_publish(dsl)

    assert any(item["code"] == "missing_variable_source" for item in result["errors"])


def test_publish_validation_handles_colon_component_references():
    AgentValidationService = load_validation_service()
    dsl = {
        "components": {
            "begin": component("Begin", downstream=["Agent:Writer"]),
            "Agent:Writer": component(
                "Agent",
                params={
                    "llm_id": "deepseek@test",
                    "prompts": [{"role": "user", "content": "{Ghost:Missing@content}"}],
                },
                upstream=["begin"],
            ),
        }
    }

    result = AgentValidationService.validate_for_publish(dsl)

    assert result["ok"] is False
    assert any(item["code"] == "missing_variable_source" for item in result["errors"])


def test_publish_validation_blocks_unsafe_sql():
    AgentValidationService = load_validation_service()
    dsl = {
        "components": {
            "begin": component("Begin", downstream=["sql_0"]),
            "sql_0": component(
                "ExeSQL",
                params={"sql": "SELECT * FROM orders; DELETE FROM orders"},
                upstream=["begin"],
            ),
        }
    }

    result = AgentValidationService.validate_for_publish(dsl)

    assert result["ok"] is False
    assert any(item["code"] == "unsafe_sql" for item in result["errors"])


def test_publish_validation_warns_file_input_without_processor():
    AgentValidationService = load_validation_service()
    dsl = {
        "components": {
            "begin": component(
                "Begin",
                params={"inputs": [{"key": "file", "type": "file"}]},
                downstream=["message_0"],
            ),
            "message_0": component("Message", params={"content": ["ok"]}, upstream=["begin"]),
        }
    }

    result = AgentValidationService.validate_for_publish(dsl)

    assert result["ok"] is True
    assert any(item["code"] == "file_input_without_processor" for item in result["warnings"])


def test_publish_validation_warns_artifact_without_downstream_message():
    AgentValidationService = load_validation_service()
    dsl = {
        "components": {
            "begin": component("Begin", downstream=["doc_0"]),
            "doc_0": component(
                "DocGenerator",
                params={"content": "{sys.query}", "output_format": "docx"},
                upstream=["begin"],
            ),
        }
    }

    result = AgentValidationService.validate_for_publish(dsl)

    assert result["ok"] is True
    assert any(item["code"] == "artifact_without_message_output" for item in result["warnings"])


def test_publish_validation_allows_artifact_with_downstream_message():
    AgentValidationService = load_validation_service()
    dsl = {
        "components": {
            "begin": component("Begin", downstream=["doc_0"]),
            "doc_0": component(
                "DocGenerator",
                params={"content": "{sys.query}", "output_format": "docx"},
                downstream=["message_0"],
                upstream=["begin"],
            ),
            "message_0": component("Message", params={"content": ["{doc_0@download}"]}, upstream=["doc_0"]),
        }
    }

    result = AgentValidationService.validate_for_publish(dsl)

    assert not any(item["code"] == "artifact_without_message_output" for item in result["warnings"])


def test_publish_validation_blocks_excel_export_without_data_reference():
    AgentValidationService = load_validation_service()
    dsl = {
        "components": {
            "begin": component("Begin", downstream=["excel_0"]),
            "excel_0": component(
                "ExcelProcessor",
                params={"operation": "export", "transform_data": ""},
                upstream=["begin"],
            ),
        }
    }

    result = AgentValidationService.validate_for_publish(dsl)

    assert result["ok"] is False
    assert any(item["code"] == "missing_excel_output_data" for item in result["errors"])
    assert any(item["code"] == "artifact_without_message_output" for item in result["warnings"])


def test_publish_validation_blocks_excel_calculate_without_source_value():
    AgentValidationService = load_validation_service()
    dsl = {
        "components": {
            "begin": component("Begin", downstream=["excel_0"]),
            "excel_0": component(
                "ExcelProcessor",
                params={"operation": "calculate", "calculation_value": ""},
                upstream=["begin"],
            ),
        }
    }

    result = AgentValidationService.validate_for_publish(dsl)

    assert result["ok"] is False
    assert any(item["code"] == "missing_excel_calculation_value" for item in result["errors"])
