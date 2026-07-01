import os

import pytest

from agent.component.scoped_db import ScopedDB


def test_scoped_db_ensures_table_in_agent_namespace_and_inserts_queries(tmp_path, monkeypatch):
    root = tmp_path / "scoped"
    monkeypatch.setattr("agent.component.scoped_db.SCOPED_DB_ROOT", str(root))
    db_ref = ScopedDB.connector_ref("tenant-1", "Teacher Agent")

    table_ref = ScopedDB.ensure_table(db_ref, "student_score")
    row = ScopedDB.insert_record(
        table_ref,
        {
            "id": "score-1",
            "student_id": "student-a",
            "activity_id": "lesson-1",
            "score": 88.7,
            "self_score": 86.5,
            "external_score": 92,
            "ignored_field": "blocked",
        },
    )
    result = ScopedDB.query_records(table_ref, {"student_id": "student-a"}, limit=10)

    assert table_ref["table_name"] == "agent_teacher_agent_student_score"
    assert os.path.exists(db_ref["db_path"])
    assert row["tenant_id"] == "tenant-1"
    assert row["agent_id"] == "teacher_agent"
    assert "ignored_field" not in row
    assert result["row_count"] == 1
    assert result["rows"][0]["score"] == 88.7


def test_scoped_db_blocks_unsupported_template_and_unsafe_path(tmp_path):
    with pytest.raises(ValueError):
        ScopedDB.safe_table_name("agent", "drop table users")

    with pytest.raises(ValueError):
        ScopedDB.ensure_safe_db_path(str(tmp_path / "outside.sqlite3"))


def test_scoped_db_blocks_cross_tenant_reference(tmp_path, monkeypatch):
    monkeypatch.setattr("agent.component.scoped_db.SCOPED_DB_ROOT", str(tmp_path))
    db_ref = ScopedDB.connector_ref("tenant-a", "agent-a")

    with pytest.raises(PermissionError):
        ScopedDB.assert_tenant(db_ref, "tenant-b")
