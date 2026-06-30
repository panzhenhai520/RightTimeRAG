from api.db.services.file_service import FileService


def test_file_assets_expose_legacy_text_documents_and_chunks():
    assets = [
        {
            "id": "file-1",
            "name": "meeting.txt",
            "mime_type": "text/plain",
            "size": 26,
            "text": "abcdefghijklmnopqrstuvwxyz",
        }
    ]

    assert FileService.file_assets_to_texts(assets) == ["abcdefghijklmnopqrstuvwxyz"]

    documents = FileService.file_assets_to_text_documents(assets)
    assert documents == [
        {
            "type": "text_document",
            "file_id": "file-1",
            "name": "meeting.txt",
            "mime_type": "text/plain",
            "size": 26,
            "content": "abcdefghijklmnopqrstuvwxyz",
            "char_count": 26,
        }
    ]

    chunks = FileService.file_assets_to_text_chunks(assets, max_chars=10, overlap=2)
    assert [chunk["content"] for chunk in chunks] == ["abcdefghij", "ijklmnopqr", "qrstuvwxyz"]
    assert [chunk["chunk_id"] for chunk in chunks] == ["file-1:0", "file-1:1", "file-1:2"]
    assert chunks[1]["start_char"] == 8
    assert chunks[1]["end_char"] == 18


def test_file_assets_skip_empty_text_chunks_but_keep_document_metadata():
    assets = [
        {
            "id": "file-empty",
            "name": "empty.pdf",
            "mime_type": "application/pdf",
            "size": 0,
        }
    ]

    documents = FileService.file_assets_to_text_documents(assets)
    chunks = FileService.file_assets_to_text_chunks(assets)

    assert documents[0]["content"] == ""
    assert documents[0]["char_count"] == 0
    assert chunks == []
