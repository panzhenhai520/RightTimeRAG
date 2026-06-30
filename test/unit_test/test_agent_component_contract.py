import sys
import types

from agent.component.schema import (
    build_field_schema,
    build_runtime_capabilities,
    build_schema_from_io,
    normalize_schema_type,
)
from agent.component.docs_generator import DocGeneratorParam
from agent.component.excel_processor import ExcelProcessorParam
from agent.component.file_parser import FileParserParam

sys.modules.setdefault("pyodbc", types.SimpleNamespace(connect=lambda *_, **__: None))
from agent.tools.exesql import ExeSQLParam


def test_normalize_schema_type_supports_runtime_type_strings():
    assert normalize_schema_type("<class 'str'>") == "String"
    assert normalize_schema_type("Array<Object>") == "Array<JSON>"
    assert normalize_schema_type("file") == "FileAsset"
    assert normalize_schema_type("TextDocument") == "TextDocument"
    assert normalize_schema_type("TextChunk[]") == "Array<TextChunk>"
    assert normalize_schema_type("TableData") == "TableData"
    assert normalize_schema_type("sql_result") == "SQLResult"
    assert normalize_schema_type("Artifact[]") == "Array<Artifact>"


def test_build_field_schema_does_not_expose_runtime_value():
    field = build_field_schema("answer", {"type": "str", "name": "Answer", "value": "secret"})

    assert field["name"] == "answer"
    assert field["type"] == "String"
    assert field["label"] == "Answer"
    assert "value" not in field


def test_schema_is_derived_from_legacy_forms():
    inputs = build_schema_from_io(
        {
            "query": {"type": "text", "name": "Query"},
            "source_file": {"type": "file", "name": "Source file"},
        },
        default_required=True,
    )
    outputs = build_schema_from_io(
        {
            "text": {"type": "str", "value": ""},
            "count": {"type": "number", "value": 0},
        }
    )

    assert inputs["query"]["type"] == "String"
    assert inputs["query"]["required"] is True
    assert inputs["source_file"]["type"] == "FileAsset"
    assert outputs["text"]["type"] == "String"
    assert outputs["count"]["type"] == "Number"


def test_runtime_capabilities_are_inferred_and_can_be_overridden():
    inputs = build_schema_from_io({"source_file": {"type": "file"}})
    outputs = build_schema_from_io({"markdown": {"type": "str"}})

    caps = build_runtime_capabilities(
        "ExcelProcessor",
        {"supports_cancel": False},
        inputs,
        outputs,
    )

    assert caps["long_running"] is True
    assert caps["produces_artifacts"] is True
    assert caps["accepts_files"] is True
    assert caps["supports_cancel"] is False


def test_artifact_array_marks_component_as_artifact_producer():
    caps = build_runtime_capabilities(
        "Message",
        None,
        {},
        build_schema_from_io({"downloads": {"type": "Artifact[]"}}),
    )

    assert caps["produces_artifacts"] is True


def test_core_business_components_publish_standard_output_schemas():
    excel_outputs = ExcelProcessorParam().get_output_schema()
    file_outputs = FileParserParam().get_output_schema()
    doc_outputs = DocGeneratorParam().get_output_schema()
    sql_outputs = ExeSQLParam().get_output_schema()

    assert excel_outputs["data"]["type"] == "TableData"
    assert excel_outputs["downloads"]["type"] == "Array<Artifact>"
    assert file_outputs["chunks"]["type"] == "Array<TextChunk>"
    assert doc_outputs["attachment"]["type"] == "Artifact"
    assert sql_outputs["sql_result"]["type"] == "SQLResult"
