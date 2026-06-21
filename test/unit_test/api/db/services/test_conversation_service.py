from types import SimpleNamespace

from api.db.services.conversation_service import structure_answer


def test_structure_answer_keeps_process_blocks_only_in_persisted_history():
    conv = SimpleNamespace(
        message=[
            {
                "role": "assistant",
                "content": "<retrieving>Searching\n</retrieving><think>Reviewing\n</think>streamed answer",
            }
        ],
        reference=[{"chunks": [], "doc_aggs": []}],
    )
    ans = {
        "answer": "final answer [ID:0]",
        "reference": {"chunks": [], "doc_aggs": []},
        "final": True,
    }

    structured = structure_answer(conv, ans, "msg-1", "session-1")

    assert structured["answer"] == "final answer [ID:0]"
    assert conv.message[-1]["content"] == (
        "<retrieving>Searching\n</retrieving><think>Reviewing\n</think>final answer [ID:0]"
    )
