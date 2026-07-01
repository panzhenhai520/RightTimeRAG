from api.db.services.agent_public_response_service import AgentPublicResponseService


def test_public_answer_strips_hidden_thoughts():
    response = AgentPublicResponseService.build_response(
        agent_id="agent-1",
        run_id="run-1",
        session_id="session-1",
        answer="<think>internal reasoning</think>\nVisible answer.",
    )

    assert response["answer"] == "Visible answer."
    assert "internal reasoning" not in response["answer"]


def test_public_trace_summary_does_not_expose_internal_node_payloads():
    trace = {
        "state": {"status": "succeeded", "api_key": "hidden"},
        "event_count": 2,
        "duration": 1.5,
        "progress": {
            "percent": 1,
            "total_nodes": 1,
            "succeeded_nodes": 1,
            "failed_nodes": 0,
            "running_nodes": 0,
            "current_nodes": [{"component_id": "n1", "component_name": "LLM", "thoughts": "secret"}],
        },
        "nodes": [
            {
                "component_id": "n1",
                "component_name": "LLM",
                "component_type": "Generate",
                "status": "succeeded",
                "thoughts": "secret",
                "inputs": {"password": "secret"},
                "outputs": {"content": "hidden output"},
                "latest_output": "hidden latest",
                "elapsed_time": 1.2,
            }
        ],
        "workflow": {"status": "succeeded", "outputs": {"token": "hidden"}},
    }

    response = AgentPublicResponseService.build_response(agent_id="agent-1", trace=trace)
    summary = response["trace_summary"]
    serialized = str(summary)

    assert summary["nodes"] == [
        {
            "component_id": "n1",
            "component_name": "LLM",
            "component_type": "Generate",
            "status": "succeeded",
            "elapsed_time": 1.2,
        }
    ]
    assert "thoughts" not in serialized
    assert "inputs" not in serialized
    assert "outputs" not in serialized
    assert "latest_output" not in serialized
    assert "secret" not in serialized


def test_public_references_and_downloads_are_whitelisted_and_deduplicated():
    final_answer = {
        "event": "message_end",
        "data": {
            "content": "answer",
            "reference": {
                "chunks": [
                    {
                        "chunk_id": "chunk-1",
                        "doc_id": "doc-1",
                        "docnm_kwd": "report.pdf",
                        "kb_id": "kb-1",
                        "standard_type": "law",
                        "jurisdiction": "CN",
                        "version": "2024",
                        "effective_from": "2024-01-01",
                        "article_no": "第50条",
                        "metadata_incomplete": False,
                        "content_with_weight": "evidence text",
                        "vector": [0.1, 0.2],
                        "content_ltks": "hidden",
                    }
                ],
                "doc_aggs": [{"doc_id": "doc-1", "count": 1}],
            },
            "downloads": [
                {"doc_id": "file-1", "filename": "a.docx", "base64": "hidden"},
                {"doc_id": "file-1", "filename": "a.docx"},
            ],
        },
    }

    response = AgentPublicResponseService.from_final_answer(
        agent_id="agent-1",
        run_id="run-1",
        session_id="session-1",
        message_id="message-1",
        final_answer=final_answer,
    )

    assert response["references"] == [
        {
            "id": "chunk-1",
            "chunk_id": "chunk-1",
            "document_id": "doc-1",
            "document_name": "report.pdf",
            "dataset_id": "kb-1",
            "standard_type": "law",
            "jurisdiction": "CN",
            "effective_from": "2024-01-01",
            "version": "2024",
            "article_no": "第50条",
            "metadata_incomplete": False,
            "content": "evidence text",
        }
    ]
    assert response["downloads"] == [
        {
            "artifact_id": "file-1",
            "doc_id": "file-1",
            "filename": "a.docx",
        }
    ]


def test_public_error_shape_is_structured():
    error = AgentPublicResponseService.normalize_error(
        "TIMEOUT",
        "<think>hidden</think>Timed out.",
        retryable=True,
    )

    assert error == {"code": "TIMEOUT", "message": "Timed out.", "retryable": True}


def test_public_response_extracts_structured_agent_fields_and_latency():
    final_answer = {
        "event": "message_end",
        "data": {
            "content": "fallback answer",
            "structured": {
                "OutputFormatter:Result": {
                    "answer": "<think>hidden</think>Visible structured answer.",
                    "intention": "teach",
                    "target": "student",
                    "reply_to": "teacher-2",
                    "confidence": 1.5,
                    "knowledge_used": [
                        {
                            "doc_id": "doc-1",
                            "chunk_id": "chunk-1",
                            "api_key": "hidden",
                        }
                    ],
                    "suggested_next_action": "ask_student_repeat",
                }
            },
        },
    }
    trace = {
        "state": {
            "status": "succeeded",
            "metadata": {"workflow_id": "workflow-1", "workflow_version": "v3"},
        },
        "duration": 1.234,
        "workflow": {"status": "succeeded"},
    }

    response = AgentPublicResponseService.from_final_answer(
        agent_id="agent-1",
        workflow_id="workflow-1",
        run_id="run-1",
        session_id="session-1",
        message_id="message-1",
        final_answer=final_answer,
        trace=trace,
    )

    assert response["answer"] == "Visible structured answer."
    assert response["intention"] == "teach"
    assert response["target"] == "student"
    assert response["reply_to"] == "teacher-2"
    assert response["confidence"] == 1.0
    assert response["suggested_next_action"] == "ask_student_repeat"
    assert response["knowledge_used"] == [{"doc_id": "doc-1", "chunk_id": "chunk-1"}]
    assert response["latency_ms"] == 1234
    assert response["error_code"] == ""
    assert response["trace_summary"]["workflow_id"] == "workflow-1"
    assert response["trace_summary"]["workflow_version"] == "v3"


def test_public_response_exposes_top_level_error_code():
    error = AgentPublicResponseService.normalize_error("WORKFLOW_FAILED", "bad")
    response = AgentPublicResponseService.build_response(agent_id="agent-1", status="failed", error=error)

    assert response["error_code"] == "WORKFLOW_FAILED"


def test_public_response_redacts_sensitive_error_and_trace_text():
    error = AgentPublicResponseService.normalize_error("WORKFLOW_FAILED", "api_key=abc123 password:secret")
    trace = {
        "state": {"status": "failed"},
        "workflow": {"status": "failed", "error": "authorization=BearerSecret token=raw"},
        "nodes": [{"component_id": "n1", "component_name": "LLM", "status": "failed", "error": "secret=value"}],
    }

    response = AgentPublicResponseService.build_response(agent_id="agent-1", status="failed", error=error, trace=trace)
    serialized = str(response)

    assert "abc123" not in serialized
    assert "BearerSecret" not in serialized
    assert "raw" not in serialized
    assert "secret=value" not in serialized
    assert "api_key=***" in serialized


def test_public_trace_summary_exposes_context_hash_not_context_inputs():
    trace = {
        "state": {"status": "running", "metadata": {"workflow_id": "workflow-1"}},
        "workflow": {
            "status": "running",
            "context_hash": "h" * 64,
            "constraint_hash": "c" * 64,
            "context_missing": ["meeting_topic"],
            "context_issues": [{"code": "INVALID_TARGET", "message": "invalid target"}],
            "inputs": {"ai_teacher_turn_context": {"student_last_utterance": "private"}},
        },
    }

    response = AgentPublicResponseService.build_response(agent_id="agent-1", trace=trace)
    summary = response["trace_summary"]
    serialized = str(summary)

    assert summary["context_hash"] == "h" * 64
    assert summary["constraint_hash"] == "c" * 64
    assert summary["context_missing"] == ["meeting_topic"]
    assert "student_last_utterance" not in serialized
    assert "private" not in serialized
