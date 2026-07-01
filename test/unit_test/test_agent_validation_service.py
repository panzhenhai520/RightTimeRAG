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


def test_publish_validation_defers_dynamic_sql_reference_to_runtime_guard():
    AgentValidationService = load_validation_service()
    dsl = {
        "components": {
            "begin": component("Begin", downstream=["agent_0"]),
            "agent_0": component(
                "Agent",
                params={"llm_id": "deepseek@test", "prompts": [{"role": "user", "content": "{sys.query}"}]},
                downstream=["sql_0"],
                upstream=["begin"],
            ),
            "sql_0": component(
                "ExeSQL",
                params={"sql": "{agent_0@answer}"},
                upstream=["agent_0"],
            ),
        }
    }

    result = AgentValidationService.validate_for_publish(dsl)

    assert result["ok"] is True
    assert result["errors"] == []
    assert any(item["code"] == "dynamic_sql_runtime_validation" for item in result["warnings"])


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


def test_publish_validation_allows_parser_text_into_agent_prompt():
    AgentValidationService = load_validation_service()
    dsl = {
        "components": {
            "begin": component(
                "Begin",
                params={"inputs": {"law_file": {"name": "法律文件", "type": "file"}}},
                downstream=["parser"],
            ),
            "parser": component(
                "FileParser",
                params={"input_files": ["begin@law_file_file_assets"], "query": "{sys.query}"},
                downstream=["agent_0"],
                upstream=["begin"],
            ),
            "agent_0": component(
                "Agent",
                params={
                    "llm_id": "deepseek@test",
                    "prompts": [{"role": "user", "content": "请分析：{parser@content}"}],
                },
                downstream=["message_0"],
                upstream=["parser"],
            ),
            "message_0": component("Message", params={"content": ["{agent_0@content}"]}, upstream=["agent_0"]),
        }
    }

    result = AgentValidationService.validate_for_publish(dsl)

    assert result["ok"] is True
    assert not any(item["code"] == "incompatible_connection_type" for item in result["errors"])


def test_publish_validation_allows_parser_references_into_citation_formatter():
    AgentValidationService = load_validation_service()
    dsl = {
        "components": {
            "begin": component(
                "Begin",
                params={"inputs": {"law_file": {"name": "法律文件", "type": "file"}}},
                downstream=["parser"],
            ),
            "parser": component(
                "FileParser",
                params={"input_files": ["begin@law_file_file_assets"], "query": "{sys.query}"},
                downstream=["cite_0"],
                upstream=["begin"],
            ),
            "cite_0": component(
                "CitationFormatter",
                params={"references": "{parser@references}"},
                downstream=["message_0"],
                upstream=["parser"],
            ),
            "message_0": component("Message", params={"content": ["{cite_0@markdown}"]}, upstream=["cite_0"]),
        }
    }

    result = AgentValidationService.validate_for_publish(dsl)

    assert result["ok"] is True
    assert not any(item["code"] == "incompatible_connection_type" for item in result["errors"])


def test_publish_validation_allows_number_calculate_result_into_chart_spec_builder():
    AgentValidationService = load_validation_service()
    dsl = {
        "components": {
            "begin": component("Begin", downstream=["calc_0"]),
            "calc_0": component(
                "NumberCalculate",
                params={
                    "operation": "weighted_score",
                    "self_score": "86",
                    "self_weight": "0.6",
                    "external_score": "92",
                    "external_weight": "0.4",
                },
                downstream=["chart_0"],
                upstream=["begin"],
            ),
            "chart_0": component(
                "ChartSpecBuilder",
                params={
                    "chart_type": "bar",
                    "data": "[{\"activity\":\"lesson-1\",\"score\":{calc_0@result}}]",
                    "x_field": "activity",
                    "y_field": "score",
                },
                downstream=["message_0"],
                upstream=["calc_0"],
            ),
            "message_0": component("Message", params={"content": ["{chart_0@summary}"]}, upstream=["chart_0"]),
        }
    }

    result = AgentValidationService.validate_for_publish(dsl)

    assert result["ok"] is True
    assert not any(item["code"] == "incompatible_connection_type" for item in result["errors"])


def test_publish_validation_allows_chart_render_and_artifact_packaging_flow():
    AgentValidationService = load_validation_service()
    dsl = {
        "components": {
            "begin": component("Begin", downstream=["chart_0"]),
            "chart_0": component(
                "ChartSpecBuilder",
                params={
                    "chart_type": "line",
                    "data": "[{\"activity\":\"lesson-1\",\"score\":88}]",
                    "x_field": "activity",
                    "y_field": "score",
                },
                downstream=["render_0"],
                upstream=["begin"],
            ),
            "render_0": component(
                "ChartRenderer",
                params={"chart_spec": "{chart_0@chart_spec}", "output_format": "svg"},
                downstream=["pack_0"],
                upstream=["chart_0"],
            ),
            "pack_0": component(
                "ArtifactPackager",
                params={"artifacts": "{render_0@downloads}", "manifest": {"kind": "lesson_report"}},
                downstream=["message_0"],
                upstream=["render_0"],
            ),
            "message_0": component("Message", params={"content": ["{pack_0@markdown}"]}, upstream=["pack_0"]),
        }
    }

    result = AgentValidationService.validate_for_publish(dsl)

    assert result["ok"] is True
    assert not any(item["code"] == "incompatible_connection_type" for item in result["errors"])
    assert not any(item["code"] == "artifact_without_message_output" for item in result["warnings"])


def test_publish_validation_allows_rubric_into_pronunciation_judge():
    AgentValidationService = load_validation_service()
    structured = {
        "teacher_plan": "先示范，再分句跟读。",
        "teaching_steps": ["listen", "repeat"],
        "self_score": 86.5,
        "rubric_scores": {
            "pronunciation": 88,
            "word_completeness": 90,
            "fluency": 82,
            "rhythm": 85,
            "stress": 80,
            "intonation": 84,
            "completion": 91,
        },
        "feedback": "整体清晰。",
        "next_step": "继续练习。",
    }
    dsl = {
        "components": {
            "begin": component("Begin", downstream=["rubric_0"]),
            "rubric_0": component(
                "ScoreRubricBuilder",
                downstream=["judge_0"],
                upstream=["begin"],
            ),
            "judge_0": component(
                "PronunciationJudge",
                params={
                    "structured_result": structured,
                    "rubric": "{rubric_0@rubric}",
                },
                downstream=["message_0"],
                upstream=["rubric_0"],
            ),
            "message_0": component("Message", params={"content": ["{judge_0@feedback}"]}, upstream=["judge_0"]),
        }
    }

    result = AgentValidationService.validate_for_publish(dsl)

    assert result["ok"] is True
    assert not any(item["code"] == "incompatible_connection_type" for item in result["errors"])


def test_publish_validation_allows_external_score_into_weighted_calculation():
    AgentValidationService = load_validation_service()
    dsl = {
        "components": {
            "begin": component("Begin", downstream=["webhook_0"]),
            "webhook_0": component(
                "WebhookInput",
                params={
                    "payload": {"judge_id": "external_judge_01", "score": 91, "rubric_scores": {"fluency": 90}},
                    "token": "secret",
                    "expected_token": "secret",
                },
                downstream=["external_0"],
                upstream=["begin"],
            ),
            "external_0": component(
                "ExternalScoreReceiver",
                params={"score_payload": "{webhook_0@event}", "self_score": 86},
                downstream=["calc_0"],
                upstream=["webhook_0"],
            ),
            "calc_0": component(
                "NumberCalculate",
                params={
                    "operation": "weighted_score",
                    "self_score": "86",
                    "self_weight": "0.6",
                    "external_score": "{external_0@external_score}",
                    "external_weight": "0.4",
                },
                downstream=["message_0"],
                upstream=["external_0"],
            ),
            "message_0": component("Message", params={"content": ["{calc_0@summary}"]}, upstream=["calc_0"]),
        }
    }

    result = AgentValidationService.validate_for_publish(dsl)

    assert result["ok"] is True
    assert not any(item["code"] == "incompatible_connection_type" for item in result["errors"])


def test_publish_validation_blocks_file_asset_directly_into_agent_prompt():
    AgentValidationService = load_validation_service()
    dsl = {
        "components": {
            "begin": component(
                "Begin",
                params={"inputs": {"source_file": {"name": "文件", "type": "file"}}},
                downstream=["agent_0"],
            ),
            "agent_0": component(
                "Agent",
                params={
                    "llm_id": "deepseek@test",
                    "prompts": [{"role": "user", "content": "直接分析文件：{begin@source_file_file_assets}"}],
                },
                downstream=["message_0"],
                upstream=["begin"],
            ),
            "message_0": component("Message", params={"content": ["{agent_0@content}"]}, upstream=["agent_0"]),
        }
    }

    result = AgentValidationService.validate_for_publish(dsl)

    assert result["ok"] is False
    issue = next(item for item in result["errors"] if item["code"] == "incompatible_connection_type")
    assert "begin@source_file_file_assets" in issue["message"]
    assert "Agent" in issue["component_name"]


def test_publish_validation_blocks_artifact_directly_into_agent_prompt():
    AgentValidationService = load_validation_service()
    dsl = {
        "components": {
            "begin": component("Begin", downstream=["doc_0"]),
            "doc_0": component(
                "DocGenerator",
                params={"content": "{sys.query}", "output_format": "docx"},
                downstream=["agent_0"],
                upstream=["begin"],
            ),
            "agent_0": component(
                "Agent",
                params={
                    "llm_id": "deepseek@test",
                    "prompts": [{"role": "user", "content": "请阅读附件：{doc_0@attachment}"}],
                },
                downstream=["message_0"],
                upstream=["doc_0"],
            ),
            "message_0": component("Message", params={"content": ["{agent_0@content}"]}, upstream=["agent_0"]),
        }
    }

    result = AgentValidationService.validate_for_publish(dsl)

    assert result["ok"] is False
    issue = next(item for item in result["errors"] if item["code"] == "incompatible_connection_type")
    assert "doc_0@attachment" in issue["message"]
    assert "Artifact" in issue["message"]


def test_publish_validation_warns_but_allows_legacy_node_without_schema():
    AgentValidationService = load_validation_service()
    dsl = {
        "components": {
            "begin": component("Begin", downstream=["legacy_0"]),
            "legacy_0": component("LegacyNode", downstream=["agent_0"], upstream=["begin"]),
            "agent_0": component(
                "Agent",
                params={
                    "llm_id": "deepseek@test",
                    "prompts": [{"role": "user", "content": "旧节点输出：{legacy_0@payload}"}],
                },
                downstream=["message_0"],
                upstream=["legacy_0"],
            ),
            "message_0": component("Message", params={"content": ["{agent_0@content}"]}, upstream=["agent_0"]),
        }
    }

    result = AgentValidationService.validate_for_publish(dsl)

    assert result["ok"] is True
    assert any(item["code"] == "missing_port_schema" for item in result["warnings"])
