import pytest

from agent.component.teaching import (
    DEFAULT_PRONUNCIATION_DIMENSIONS,
    PromptTemplate,
    PronunciationJudge,
    ReportComposer,
    ScoreRubricBuilder,
    SummaryNode,
)


def valid_structured_result():
    return {
        "teacher_plan": "先示范，再分句跟读。",
        "teaching_steps": ["listen", "repeat", "feedback"],
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
        "feedback": "整体清晰，重音还可加强。",
        "next_step": "继续练习重音和节奏。",
    }


def test_score_rubric_builder_uses_default_pronunciation_dimensions():
    rubric = ScoreRubricBuilder.build_rubric()

    assert rubric["schema_version"] == 1
    assert [item["key"] for item in rubric["dimensions"]] == [
        item["key"] for item in DEFAULT_PRONUNCIATION_DIMENSIONS
    ]


def test_pronunciation_judge_validates_fixed_structured_llm_output():
    score_result = PronunciationJudge.validate_result(valid_structured_result())

    assert score_result["valid"] is True
    assert score_result["self_score"] == 86.5
    assert score_result["rubric_scores"]["pronunciation"] == 88.0
    assert score_result["feedback"] == "整体清晰，重音还可加强。"


def test_pronunciation_judge_fails_when_required_score_dimension_missing():
    payload = valid_structured_result()
    payload["rubric_scores"].pop("rhythm")

    with pytest.raises(ValueError, match="rubric_scores missing required dimension `rhythm`"):
        PronunciationJudge.validate_result(payload)


def test_prompt_template_summary_and_report_composer_are_deterministic():
    prompt = PromptTemplate.render_template("请教学生朗读：{{ text }}", {"text": "The quick brown fox."})
    summary = SummaryNode.summarize("第一句。\n\n第二句。", max_chars=10)
    report = ReportComposer.compose_markdown("教学报告", {"评分": {"score": 88.7}})

    assert prompt == "请教学生朗读：The quick brown fox."
    assert summary == "第一句。 第二句。"
    assert "# 教学报告" in report
    assert '"score": 88.7' in report
