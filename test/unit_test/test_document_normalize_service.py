from pathlib import Path

from api.db.services.document_normalize_service import DocumentNormalizeService


def make_workspace(tmp_path: Path) -> Path:
    root = tmp_path / "workspace"
    root.mkdir()
    (root / "policy.md").write_text(
        "# 总则\n\n第一条 合同应当合法。\n\n## 付款\n\n第二条 付款期限不得超过三十日。\n",
        encoding="utf-8",
    )
    (root / "scores.csv").write_text("name,score\nalice,91\nbob,88\n", encoding="utf-8")
    return root


def test_document_normalize_markdown_sections_paragraphs_and_chunks(tmp_path):
    root = make_workspace(tmp_path)

    document = DocumentNormalizeService.normalize(path="policy.md", roots=[root], chunk_chars=200)

    assert document["filename"] == "policy.md"
    assert document["metadata"]["line_count"] >= 5
    assert [section["title"] for section in document["sections"]] == ["总则", "付款"]
    assert any("付款期限" in paragraph["text"] for paragraph in document["paragraphs"])
    assert document["chunks"]
    assert document["chunks"][0]["source_ref"].startswith("policy.md | paragraphs")
    assert document["audit"]["action"] == "document_normalize"


def test_document_normalize_csv_preserves_table_rows(tmp_path):
    root = make_workspace(tmp_path)

    document = DocumentNormalizeService.normalize(path="scores.csv", roots=[root])

    assert document["tables"][0]["headers"] == ["name", "score"]
    assert document["tables"][0]["rows"][1]["values"]["score"] == "88"
    assert document["metadata"]["table_count"] == 1
    assert document["chunks"][0]["source_ref"] == "scores.csv | table"


def test_document_normalize_builds_stable_line_source_refs(tmp_path):
    root = make_workspace(tmp_path)

    document = DocumentNormalizeService.normalize(path="policy.md", roots=[root])

    line = document["lines"][0]
    assert line["block_type"] == "line"
    assert line["source_ref"] == "policy.md | line 1"
    assert line["document_id"] == document["document_id"]
