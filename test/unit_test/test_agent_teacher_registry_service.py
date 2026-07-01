from api.db.services.agent_teacher_registry_service import AgentTeacherRegistryService


def test_default_ai_teacher_registry_contains_four_stable_teachers():
    teachers = AgentTeacherRegistryService.list_default_teachers()
    validation = AgentTeacherRegistryService.validate_registry()

    assert validation == {"ok": True, "errors": [], "total": 4}
    assert [item["agent_id"] for item in teachers] == [
        "ai_teacher_lead",
        "ai_teacher_phonetics",
        "ai_teacher_grammar",
        "ai_teacher_coach",
    ]
    assert len({item["workflow_id"] for item in teachers}) == 4
    assert all(item["output_schema"]["required"] == ["answer", "intention", "target", "confidence"] for item in teachers)


def test_default_ai_teacher_registry_smoke_context_is_ready_for_turn_injection():
    teacher = AgentTeacherRegistryService.get_default_teacher("ai_teacher_phonetics")
    context = AgentTeacherRegistryService.build_smoke_context(teacher, query="Please read: good morning.")

    assert context["meeting_topic"] == "零基础英语跟读训练"
    assert context["student_last_utterance"] == "Please read: good morning."
    assert context["teacher_personality_summary"] == teacher["persona"]
    assert context["language_style_constraints"] == teacher["language_style"]
    assert context["current_task"] in teacher["default_intentions"]
    assert context["target_listener"] == "student"
    assert "answer" in context["output_schema"]["properties"]


def test_default_ai_teacher_registry_rejects_incomplete_teacher():
    errors = AgentTeacherRegistryService.validate_teacher({"agent_id": "teacher-only"})

    assert "workflow_id is required" not in errors
    assert "name is required" in errors
    assert "dataset_roles must contain at least one role" in errors

