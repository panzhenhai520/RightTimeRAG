import sys
import types

from agent.component.schema import (
    build_field_schema,
    build_component_manifest,
    build_runtime_capabilities,
    build_schema_from_io,
    list_operator_manifests,
    normalize_schema_type,
)
from agent.component.docs_generator import DocGeneratorParam
from agent.component.excel_processor import ExcelProcessorParam
from agent.component.file_parser import FileParserParam
from agent.component.citation_formatter import CitationFormatterParam
from agent.component.compliance import (
    ClauseMatcherParam,
    ComplianceChecklistGeneratorParam,
    ComplianceReportComposerParam,
    ComplianceVerifierParam,
    ContractClauseExtractorParam,
    RiskScorerParam,
)
from agent.component.number_calculate import NumberCalculateParam
from agent.component.chart_spec_builder import ChartSpecBuilderParam
from agent.component.output_artifacts import ArtifactPackagerParam, ChartRendererParam
from agent.component.teaching import PronunciationJudgeParam, ScoreRubricBuilderParam
from agent.component.voice_nodes import ASRTranscribeParam, TTSGenerateParam, VoiceReplyOutputParam
from agent.component.external_review import ExternalScoreReceiverParam, WebhookInputParam

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
    assert normalize_schema_type("audio") == "AudioAsset"
    assert normalize_schema_type("VoiceReply") == "VoiceReply"
    assert normalize_schema_type("AgentRunRef") == "AgentRunRef"
    assert normalize_schema_type("MeetingContext") == "MeetingContext"
    assert normalize_schema_type("ScoreRubric") == "ScoreRubric"
    assert normalize_schema_type("ScoreResult") == "ScoreResult"
    assert normalize_schema_type("ChartSpec[]") == "Array<ChartSpec>"


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
    citation_outputs = CitationFormatterParam().get_output_schema()
    clause_outputs = ContractClauseExtractorParam().get_output_schema()
    checklist_outputs = ComplianceChecklistGeneratorParam().get_output_schema()
    matcher_outputs = ClauseMatcherParam().get_output_schema()
    verifier_outputs = ComplianceVerifierParam().get_output_schema()
    risk_outputs = RiskScorerParam().get_output_schema()
    compliance_report_outputs = ComplianceReportComposerParam().get_output_schema()
    number_outputs = NumberCalculateParam().get_output_schema()
    chart_outputs = ChartSpecBuilderParam().get_output_schema()
    chart_renderer_outputs = ChartRendererParam().get_output_schema()
    artifact_packager_outputs = ArtifactPackagerParam().get_output_schema()
    rubric_outputs = ScoreRubricBuilderParam().get_output_schema()
    judge_outputs = PronunciationJudgeParam().get_output_schema()
    tts_outputs = TTSGenerateParam().get_output_schema()
    asr_outputs = ASRTranscribeParam().get_output_schema()
    voice_outputs = VoiceReplyOutputParam().get_output_schema()
    webhook_outputs = WebhookInputParam().get_output_schema()
    external_outputs = ExternalScoreReceiverParam().get_output_schema()
    doc_outputs = DocGeneratorParam().get_output_schema()
    sql_outputs = ExeSQLParam().get_output_schema()

    assert excel_outputs["data"]["type"] == "TableData"
    assert excel_outputs["downloads"]["type"] == "Array<Artifact>"
    assert file_outputs["chunks"]["type"] == "Array<TextChunk>"
    assert citation_outputs["citations"]["type"] == "Array<JSON>"
    assert citation_outputs["markdown"]["type"] == "String"
    assert clause_outputs["clauses"]["type"] == "Array<JSON>"
    assert checklist_outputs["checklist"]["type"] == "Array<JSON>"
    assert matcher_outputs["matches"]["type"] == "Array<JSON>"
    assert verifier_outputs["verification_results"]["type"] == "Array<JSON>"
    assert risk_outputs["risk_summary"]["type"] == "JSON"
    assert compliance_report_outputs["markdown"]["type"] == "String"
    assert number_outputs["result"]["type"] == "Number"
    assert chart_outputs["chart_spec"]["type"] == "ChartSpec"
    assert chart_renderer_outputs["chart_artifact"]["type"] == "Artifact"
    assert chart_renderer_outputs["downloads"]["type"] == "Array<Artifact>"
    assert artifact_packager_outputs["package"]["type"] == "Artifact"
    assert artifact_packager_outputs["downloads"]["type"] == "Array<Artifact>"
    assert rubric_outputs["rubric"]["type"] == "ScoreRubric"
    assert judge_outputs["score_result"]["type"] == "ScoreResult"
    assert tts_outputs["audio"]["type"] == "AudioAsset"
    assert asr_outputs["transcript"]["type"] == "String"
    assert voice_outputs["voice"]["type"] == "VoiceReply"
    assert webhook_outputs["event"]["type"] == "JSON"
    assert external_outputs["score_result"]["type"] == "ScoreResult"
    assert doc_outputs["attachment"]["type"] == "Artifact"
    assert sql_outputs["sql_result"]["type"] == "SQLResult"


def test_operator_manifests_publish_category_risk_and_service_dependencies():
    manifests = {item["operator"]: item for item in list_operator_manifests()}

    assert manifests["TTSGenerate"]["category"] == "voice_multi_agent"
    assert manifests["TTSGenerate"]["risk_level"] == "medium"
    assert "cosyvoice3" in manifests["TTSGenerate"]["requires_service"]
    assert manifests["ASRTranscribe"]["category"] == "voice_multi_agent"
    assert "qwen3_asr" in manifests["ASRTranscribe"]["requires_service"]
    assert manifests["ExeSQL"]["category"] == "database"
    assert manifests["ExeSQL"]["risk_level"] == "high"
    assert "database" in manifests["ExeSQL"]["requires_service"]
    assert manifests["SafeRecordInsert"]["category"] == "database"
    assert manifests["SafeRecordInsert"]["risk_level"] == "medium"
    assert "scoped_sqlite" in manifests["SafeRecordInsert"]["requires_service"]
    assert manifests["ChartRenderer"]["category"] == "output"
    assert "ragflow_file_storage" in manifests["ChartRenderer"]["requires_service"]
    assert manifests["ArtifactPackager"]["category"] == "output"
    assert manifests["ArtifactPackager"]["risk_level"] == "medium"
    assert manifests["ContractClauseExtractor"]["category"] == "compliance"
    assert manifests["ComplianceVerifier"]["category"] == "compliance"
    assert manifests["WenCai"]["category"] == "retrieval"
    assert manifests["YahooFinance"]["category"] == "retrieval"
    assert "network" in manifests["WenCai"]["requires_service"]
    assert "network" in manifests["YahooFinance"]["requires_service"]


def test_component_manifest_uses_real_component_schema_and_legacy_contract_keys():
    param = ExcelProcessorParam()
    manifest = param.get_manifest("ExcelProcessor")

    assert manifest["operator"] == "ExcelProcessor"
    assert manifest["category"] == "table"
    assert manifest["output_schema"]["data"]["type"] == "TableData"
    assert manifest["output_schema"]["downloads"]["type"] == "Array<Artifact>"
    assert manifest["runtime_capabilities"]["produces_artifacts"] is True
    assert "ragflow_file_storage" in manifest["requires_service"]


def test_build_component_manifest_allows_explicit_overrides():
    manifest = build_component_manifest(
        "CustomNode",
        input_schema={"audio": {"name": "audio", "type": "AudioAsset"}},
        output_schema={"score": {"name": "score", "type": "ScoreResult"}},
        runtime_capabilities={"long_running": True},
        category="voice_multi_agent",
        risk_level="medium",
        requires_service=["local_asr"],
    )

    assert manifest["category"] == "voice_multi_agent"
    assert manifest["risk_level"] == "medium"
    assert manifest["requires_service"] == ["local_asr"]
    assert manifest["runtime_capabilities"]["long_running"] is True
