import pytest

from agent.component.external_review import (
    ExternalScoreReceiver,
    HumanReview,
    WebhookInput,
)


def test_webhook_input_token_verification():
    assert WebhookInput.verify_token("secret", "secret") is True
    assert WebhookInput.verify_token("wrong", "secret") is False
    assert WebhookInput.verify_token("secret", "") is False


def test_external_score_receiver_normalizes_structured_score():
    result = ExternalScoreReceiver.normalize_score(
        {
            "judge_id": "external_judge_01",
            "score": 91.0,
            "rubric_scores": {"pronunciation": 92, "fluency": 90},
            "comment": "clear",
        }
    )

    assert result["source"] == "external_judge"
    assert result["score"] == 91.0
    assert result["rubric_scores"]["pronunciation"] == 92.0
    assert result["comment"] == "clear"


def test_external_score_receiver_rejects_invalid_payload_and_supports_fallback():
    with pytest.raises(ValueError, match="missing judge_id"):
        ExternalScoreReceiver.normalize_score({"score": 91})

    fallback = ExternalScoreReceiver.fallback_score(86.5, reason="timeout")
    assert fallback["source"] == "self_score_fallback"
    assert fallback["score"] == 86.5
    assert fallback["comment"] == "timeout"


def test_human_review_builds_traceable_review():
    review = HumanReview.build_review({"score": 88}, "approved", reviewer="teacher-a", comment="ok")

    assert review["schema_version"] == 1
    assert review["status"] == "approved"
    assert review["reviewer"] == "teacher-a"
    assert review["review_data"] == {"score": 88}
    assert review["reviewed_at"]
