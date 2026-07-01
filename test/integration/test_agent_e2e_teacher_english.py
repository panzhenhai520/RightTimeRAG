import io
import json
import wave

import pytest

from agent.artifact_service import ArtifactService
from agent.component import excel_processor as excel_module
from agent.component import file_parser as file_parser_module
from agent.component import voice_nodes as voice_module
from agent.component.chart_spec_builder import ChartSpecBuilder
from agent.component.citation_formatter import CitationFormatter
from agent.component.docs_generator import DocGenerator, DocGeneratorParam
from agent.component.excel_processor import ExcelProcessor, ExcelProcessorParam
from agent.component.external_review import ExternalScoreReceiver, HumanReview
from agent.component.file_parser import FileParser, FileParserParam
from agent.component.multi_agent import AgentFanout, MeetingContextInput, MemoryInject, ResultAggregator
from agent.component.number_calculate import NumberCalculate
from agent.component.output_artifacts import ArtifactPackager, ChartRenderer
from agent.component.scoped_db import ScopedDB
from agent.component.teaching import PromptTemplate, PronunciationJudge, ReportComposer, ScoreRubricBuilder
from agent.component.voice_nodes import ASRTranscribe, ASRTranscribeParam, TTSGenerate, TTSGenerateParam, VoiceReplyOutput
from api.db.services.agent_validation_service import AgentValidationService
from common import settings


TENANT_ID = "tenant-e2e"
RUN_ID = "run-teacher-english-e2e"


class FakeStorage:
    def __init__(self):
        self.saved = {}

    def put(self, tenant_id, doc_id, content):
        self.saved[(tenant_id, doc_id)] = content


class FakeCanvas:
    task_id = "task-e2e"
    _run_id = RUN_ID

    def __init__(self, variables=None):
        self.variables = variables or {}
        self.references = []

    def get_tenant_id(self):
        return TENANT_ID

    def is_canceled(self):
        return False

    def is_reff(self, value):
        return isinstance(value, str) and value in self.variables

    def get_variable_value(self, value):
        return self.variables.get(value)

    def add_reference(self, chunks, doc_infos):
        self.references.append({"chunks": chunks, "doc_infos": doc_infos})


class FakeTTSResponse:
    status_code = 200
    text = ""

    def __init__(self, content):
        self.content = content


class FakeASRResponse:
    status_code = 200
    text = ""

    def json(self):
        return {
            "text": "The quick brown fox jumps over the lazy dog.",
            "confidence": 0.96,
            "language": "en",
            "duration": 2.4,
        }


class FakeScheduler:
    @classmethod
    def start_parallel_runs(cls, **kwargs):
        return {
            "meeting_id": kwargs["meeting_id"],
            "turn_id": kwargs["turn_id"],
            "runs": [
                {
                    "run_id": f"{spec['agent_id']}-run",
                    "agent_id": spec["agent_id"],
                    "session_id": f"{spec['agent_id']}-session",
                    "message_id": f"{spec['agent_id']}-message",
                    "status": "queued",
                    "queued": kwargs["enqueue"],
                    "metadata": {
                        "meeting_id": kwargs["meeting_id"],
                        "turn_id": kwargs["turn_id"],
                        "agent_id": spec["agent_id"],
                        "role": spec.get("role", ""),
                    },
                }
                for spec in kwargs["agents"]
            ],
        }


class FakeMemoryService:
    shared = []
    agent = []

    @classmethod
    def reset(cls):
        cls.shared = []
        cls.agent = []

    @staticmethod
    def get_context(tenant_id, meeting_id, agent_id):
        return {"shared": [], "agent": []}

    @staticmethod
    def build_injection(**kwargs):
        return {**kwargs, "prompt": f"{kwargs['meeting_id']}|{kwargs['turn_id']}|{kwargs['agent_id']}"}

    @classmethod
    def append_shared(cls, tenant_id, meeting_id, turn_id, content, source="system", metadata=None):
        cls.shared.append({"tenant_id": tenant_id, "meeting_id": meeting_id, "turn_id": turn_id, "content": content})

    @classmethod
    def append_agent(cls, tenant_id, meeting_id, agent_id, turn_id, content, run_id=None, role="", metadata=None):
        cls.agent.append({"tenant_id": tenant_id, "meeting_id": meeting_id, "agent_id": agent_id, "turn_id": turn_id, "content": content})


def component(name, params=None, downstream=None, upstream=None):
    return {
        "obj": {"component_name": name, "params": params or {}},
        "downstream": downstream or [],
        "upstream": upstream or [],
    }


def make_wav(duration_s=0.2, rate=16000):
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        wav.writeframes(b"\x00\x00" * int(duration_s * rate))
    return buf.getvalue()


def make_excel_processor(operation, canvas, **kwargs):
    processor = ExcelProcessor.__new__(ExcelProcessor)
    processor._canvas = canvas
    processor._id = f"ExcelProcessor:{operation}"
    processor._param = ExcelProcessorParam()
    processor._param.operation = operation
    for key, value in kwargs.items():
        setattr(processor._param, key, value)
    return processor


def make_file_parser(canvas):
    parser = FileParser.__new__(FileParser)
    parser._canvas = canvas
    parser._id = "FileParser:Materials"
    parser._param = FileParserParam()
    parser._param.input_files = ["teaching_materials"]
    parser._param.query = "pronunciation fluency rhythm teaching method"
    parser._param.top_n = 4
    parser._param.context_window = 0
    return parser


def make_tts(canvas, wav_bytes):
    tts = TTSGenerate.__new__(TTSGenerate)
    tts._canvas = canvas
    tts._id = "TTSGenerate:TeacherVoice"
    tts._param = TTSGenerateParam()
    tts._param.text = "The quick brown fox jumps over the lazy dog."
    tts._param.endpoint = "http://127.0.0.1:50001"
    tts._post = lambda url, payload, timeout: FakeTTSResponse(wav_bytes)
    return tts


def make_asr(canvas, audio_asset):
    asr = ASRTranscribe.__new__(ASRTranscribe)
    asr._canvas = canvas
    asr._id = "ASRTranscribe:StudentVoice"
    asr._param = ASRTranscribeParam()
    asr._param.audio = audio_asset
    asr._param.engine = "qwen3"
    asr._post = lambda endpoint, files, data, timeout: FakeASRResponse()
    return asr


def make_doc_generator(canvas, content):
    doc = DocGenerator.__new__(DocGenerator)
    doc._canvas = canvas
    doc._id = "DocGenerator:TeachingReport"
    doc._param = DocGeneratorParam()
    doc._param.output_format = "docx"
    doc._param.content = content
    doc._param.filename = "teacher_english_report"
    return doc


def test_teacher_english_agent_end_to_end_with_local_fixtures(tmp_path, monkeypatch):
    storage = FakeStorage()
    monkeypatch.setattr(settings, "STORAGE_IMPL", storage)
    monkeypatch.setattr("agent.component.scoped_db.SCOPED_DB_ROOT", str(tmp_path / "scoped_db"))

    workflow = {
        "name": "真人英语老师教学评测智能体",
        "components": {
            "begin": component("Begin", downstream=["parser", "excel_read", "audio_in"]),
            "parser": component("FileParser", params={"input_files": ["begin@materials_file_assets"]}, downstream=["cite"], upstream=["begin"]),
            "cite": component("CitationFormatter", params={"references": "{parser@references}"}, downstream=["prompt"], upstream=["parser"]),
            "excel_read": component("ExcelProcessor", params={"operation": "read", "input_files": ["begin@history_file_assets"]}, downstream=["chart"], upstream=["begin"]),
            "chart": component("ChartSpecBuilder", params={"data": "{excel_read@data}", "chart_type": "line"}, downstream=["render"], upstream=["excel_read"]),
            "render": component("ChartRenderer", params={"chart_spec": "{chart@chart_spec}"}, downstream=["pack"], upstream=["chart"]),
            "pack": component("ArtifactPackager", params={"artifacts": "{render@downloads}"}, downstream=["message"], upstream=["render"]),
            "prompt": component("PromptTemplate", params={"template": "teach {{text}}"}, downstream=["message"], upstream=["cite"]),
            "audio_in": component("AudioInput", downstream=["asr"], upstream=["begin"]),
            "asr": component("ASRTranscribe", params={"audio": "{audio_in@audio}"}, downstream=["message"], upstream=["audio_in"]),
            "message": component("Message", params={"content": ["{pack@markdown}"]}, upstream=["pack", "prompt", "asr"]),
        },
    }
    validation = AgentValidationService.validate_for_publish(workflow)
    assert validation["ok"] is True

    material_text = """
    Pronunciation teaching method: listen, model, repeat, compare, and give targeted feedback.
    Fluency practice should use short chunks first, then whole sentence repetition.
    Rhythm and stress practice helps students read natural English.
    """
    canvas = FakeCanvas(
        {
            "teaching_materials": [
                {
                    "file_id": "material-1",
                    "name": "english_teaching_material.txt",
                    "text": material_text,
                    "created_by": TENANT_ID,
                }
            ],
            "history_file": {"file_id": "history-1", "name": "history.csv", "created_by": TENANT_ID},
        }
    )
    monkeypatch.setattr(file_parser_module.FileService, "get_blob", lambda created_by, file_id: material_text.encode("utf-8"))
    monkeypatch.setattr(
        file_parser_module.FileService,
        "parse_file_to_chunks",
        lambda filename, blob, **kwargs: FileParser._text_chunks(blob.decode("utf-8"), filename, "material-1"),
    )

    parser = make_file_parser(canvas)
    parser._invoke()
    citations = CitationFormatter.normalize_references(parser.output("references"))
    citation_markdown = CitationFormatter.format_markdown(citations, include_content=True)
    assert parser.output("matches")
    assert citations[0]["file_id"] == "material-1"

    history_csv = (
        "student_id,activity,score,pronunciation,fluency,rhythm,intonation,total\n"
        "student-a,lesson-1,82,84,80,78,81,82\n"
        "student-a,lesson-2,88,90,86,84,87,88\n"
    ).encode("utf-8")
    monkeypatch.setattr(excel_module.FileService, "get_blob", lambda created_by, file_id: history_csv)
    excel_read = make_excel_processor("read", canvas, input_files=["history_file"])
    excel_read._invoke()
    excel_data = excel_read.output("data")
    history_records = list(excel_data.values())[0]
    assert len(history_records) == 2

    rubric = ScoreRubricBuilder.build_rubric()
    teacher_prompt = PromptTemplate.render_template(
        "Goal: {{ goal }}\nText: {{ text }}\nEvidence:\n{{ evidence }}",
        {
            "goal": "Teach the student to read one English sentence.",
            "text": "The quick brown fox jumps over the lazy dog.",
            "evidence": citation_markdown,
        },
    )
    structured_teacher_result = {
        "teacher_plan": "Model the sentence, split it into chunks, then ask the student to repeat.",
        "teaching_steps": ["listen", "chunk repeat", "full sentence repeat", "feedback"],
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
        "feedback": "Clear overall. Continue practicing rhythm and stress.",
        "next_step": "Repeat the same sentence at a slower speed.",
    }
    self_score = PronunciationJudge.validate_result(structured_teacher_result, rubric)
    assert teacher_prompt.startswith("Goal:")
    assert self_score["valid"] is True

    wav_bytes = make_wav()
    tts = make_tts(canvas, wav_bytes)
    tts._invoke()
    teacher_voice = tts.output("voice")
    assert teacher_voice["audio"]["artifact"]["doc_id"]

    student_audio_asset = {"file_id": "student-audio-1", "name": "student.wav", "mime_type": "audio/wav", "duration": 2.4, "created_by": TENANT_ID}
    monkeypatch.setattr(voice_module.FileService, "get_blob", lambda created_by, file_id: wav_bytes)
    asr = make_asr(canvas, student_audio_asset)
    asr._invoke()
    asr_text = asr.output("text")
    assert "quick brown fox" in asr_text

    external_score = ExternalScoreReceiver.normalize_score(
        {
            "judge_id": "local_mock_judge",
            "score": 92,
            "rubric_scores": {"pronunciation": 92, "fluency": 90, "rhythm": 89, "intonation": 91},
            "comment": "Good pacing.",
        }
    )
    review = HumanReview.build_review(external_score, "approved", reviewer="teacher-supervisor", comment="accepted")
    final_score = NumberCalculate.weighted_score(self_score["self_score"], 0.6, external_score["score"], 0.4)
    assert review["status"] == "approved"
    assert final_score == 88.7

    db_ref = ScopedDB.connector_ref(TENANT_ID, "teacher_english_agent")
    activity_table = ScopedDB.ensure_table(db_ref, "teaching_activity")
    score_table = ScopedDB.ensure_table(db_ref, "student_score")
    activity_row = ScopedDB.insert_record(
        activity_table,
        {
            "id": "activity-1",
            "student_id": "student-a",
            "activity_id": "lesson-3",
            "lesson_text": "The quick brown fox jumps over the lazy dog.",
            "summary": structured_teacher_result["teacher_plan"],
            "score": final_score,
            "payload_json": {"asr_text": asr_text, "teacher_plan": structured_teacher_result["teacher_plan"]},
        },
    )
    score_row = ScopedDB.insert_record(
        score_table,
        {
            "id": "score-lesson-3",
            "student_id": "student-a",
            "activity_id": "lesson-3",
            "score": final_score,
            "self_score": self_score["self_score"],
            "external_score": external_score["score"],
            "rubric_json": self_score["rubric_scores"],
        },
    )
    score_history = ScopedDB.query_records(score_table, {"student_id": "student-a"}, limit=10)
    assert activity_row["score"] == final_score
    assert score_row["external_score"] == 92
    assert score_history["row_count"] == 1

    chart_records = [
        *history_records,
        {
            "activity": "lesson-3",
            "score": final_score,
            "pronunciation": self_score["rubric_scores"]["pronunciation"],
            "fluency": self_score["rubric_scores"]["fluency"],
            "rhythm": self_score["rubric_scores"]["rhythm"],
            "intonation": self_score["rubric_scores"]["intonation"],
        },
    ]
    trend_chart = ChartSpecBuilder.build_spec("line", chart_records, title="History score trend", x_field="activity", y_field="score")
    radar_chart = ChartSpecBuilder.build_spec(
        "radar",
        chart_records[-1:],
        title="Pronunciation dimensions",
        x_field="activity",
        dimensions=["pronunciation", "fluency", "rhythm", "intonation"],
    )
    trend_download = ChartRenderer.create_chart_download(
        tenant_id=TENANT_ID,
        chart_spec=trend_chart,
        filename="history_score_trend",
        run_id=RUN_ID,
        node_id="ChartRenderer:Trend",
    )
    radar_download = ChartRenderer.create_chart_download(
        tenant_id=TENANT_ID,
        chart_spec=radar_chart,
        filename="pronunciation_radar",
        run_id=RUN_ID,
        node_id="ChartRenderer:Radar",
    )
    assert trend_download["doc_id"] in {key[1] for key in storage.saved}
    assert radar_download["doc_id"] in {key[1] for key in storage.saved}

    meeting_context = MeetingContextInput.build_context(
        tenant_id=TENANT_ID,
        meeting_id="meeting-english-1",
        turn_id="turn-1",
        agent_id="TeacherAgent",
        role="English teacher",
        query="Teach one English sentence.",
        load_persisted_memory=False,
        memory_service=FakeMemoryService,
    )
    fanout = AgentFanout.start_fanout(
        tenant_id=TENANT_ID,
        meeting_context=meeting_context,
        content="Teach one English sentence.",
        agents=[
            {"agent_id": "TeacherAgent", "role": "teacher"},
            {"agent_id": "PronunciationAgent", "role": "pronunciation"},
            {"agent_id": "CurriculumAgent", "role": "curriculum"},
            {"agent_id": "AnalystAgent", "role": "analyst"},
        ],
        enqueue=False,
        scheduler=FakeScheduler,
    )
    run_refs = AgentFanout.normalize_run_refs(fanout)
    aggregated = ResultAggregator.aggregate_results(
        runs=run_refs,
        results=[
            {"agent_id": "TeacherAgent", "reply_text": structured_teacher_result["teacher_plan"]},
            {"agent_id": "PronunciationAgent", "reply_text": self_score["feedback"], "score_result": self_score},
            {"agent_id": "AnalystAgent", "reply_text": "Student score improved from lesson-1 to lesson-3."},
        ],
        citations=citations,
        memory_delta=MemoryInject.build_memory_delta(meeting_context, "Completed lesson-3.", scope="agent"),
    )
    FakeMemoryService.reset()
    MemoryInject.append_memory(aggregated["memory_delta"], memory_service=FakeMemoryService)
    assert len(run_refs) == 4
    assert FakeMemoryService.agent[0]["agent_id"] == "TeacherAgent"
    assert "TeacherAgent" in aggregated["reply_text"]

    report_markdown = ReportComposer.compose_markdown(
        "真人英语老师教学评测报告",
        {
            "Teaching activity summary": structured_teacher_result["teacher_plan"],
            "Teaching steps": structured_teacher_result["teaching_steps"],
            "Student text": "The quick brown fox jumps over the lazy dog.",
            "ASR transcript": asr_text,
            "Scores": {"self_score": self_score["self_score"], "external_score": external_score["score"], "final_score": final_score},
            "Charts": {
                "trend": ChartRenderer.build_markdown(trend_download, "History score trend"),
                "radar": ChartRenderer.build_markdown(radar_download, "Pronunciation dimensions"),
            },
            "Citations": citations,
            "Next step": structured_teacher_result["next_step"],
        },
    )
    doc = make_doc_generator(canvas, report_markdown)
    doc._invoke()
    report_download = doc.output("downloads")[0]
    assert report_download["filename"].endswith(".docx")
    assert report_download["doc_id"] in {key[1] for key in storage.saved}

    package_download, package_manifest = ArtifactPackager.create_package_download(
        tenant_id=TENANT_ID,
        artifacts=[
            report_download,
            trend_download,
            radar_download,
            teacher_voice["audio"]["artifact"],
        ],
        manifest={"activity_id": "lesson-3", "final_score": final_score},
        filename="teacher_english_outputs",
        run_id=RUN_ID,
        node_id="ArtifactPackager:Final",
        fetcher=lambda tenant_id, doc_id: storage.saved[(tenant_id, doc_id)],
    )
    voice_reply = VoiceReplyOutput.build_voice_reply(aggregated["reply_text"], teacher_voice["audio"])

    trace = [
        {"component_id": "FileParser:Materials", "outputs": {"references": citations}},
        {"component_id": "ExcelProcessor:History", "outputs": {"rows": len(history_records)}},
        {"component_id": "TTSGenerate:TeacherVoice", "outputs": {"downloads": [teacher_voice["audio"]["artifact"]]}},
        {"component_id": "ASRTranscribe:StudentVoice", "outputs": {"text": asr_text}},
        {"component_id": "ScopedDB:StudentScore", "outputs": {"row_count": score_history["row_count"]}},
        {"component_id": "ChartRenderer:Trend", "outputs": {"downloads": [trend_download]}},
        {"component_id": "DocGenerator:TeachingReport", "outputs": {"downloads": [ArtifactService.attachment_from_download(report_download)]}},
        {"component_id": "ArtifactPackager:Final", "outputs": {"downloads": [package_download]}},
    ]
    trace_components = {item["component_id"] for item in trace}

    assert package_download["filename"] == "teacher_english_outputs.zip"
    assert package_manifest["artifact_count"] == 4
    assert voice_reply["type"] == "voice_reply"
    assert {"FileParser:Materials", "TTSGenerate:TeacherVoice", "ASRTranscribe:StudentVoice", "DocGenerator:TeachingReport"} <= trace_components
    assert not any("base64" in json.dumps(item, ensure_ascii=False) for item in trace)
