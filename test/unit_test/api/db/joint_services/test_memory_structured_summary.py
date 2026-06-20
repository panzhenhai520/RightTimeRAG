#
#  Copyright 2026 The InfiniFlow Authors. All Rights Reserved.
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.
#

from types import SimpleNamespace

import pytest

from api.db.joint_services import memory_message_service
from api.db.joint_services.memory_message_service import (
    _build_structured_summary_message,
    _memory_supports_structured_summary,
)
from common.constants import MemoryType


pytestmark = pytest.mark.p1


def test_memory_supports_structured_summary_only_when_semantic_enabled():
    assert _memory_supports_structured_summary(SimpleNamespace(memory_type=MemoryType.SEMANTIC.value))
    assert _memory_supports_structured_summary(
        SimpleNamespace(memory_type=MemoryType.RAW.value | MemoryType.SEMANTIC.value)
    )
    assert not _memory_supports_structured_summary(SimpleNamespace(memory_type=MemoryType.RAW.value))
    assert not _memory_supports_structured_summary(SimpleNamespace(memory_type=None))


def test_build_structured_summary_message_is_derived_from_raw_and_clean():
    message = _build_structured_summary_message(
        "memory-1",
        {
            "user_id": "user-1",
            "agent_id": "chat-1",
            "session_id": "session-1",
            "memo_topic": "租金及契诺责任保障",
            "related_kb_ids": ["kb-trust-law"],
            "user_input": """
<retrieving>Searching datasets...</retrieving>
User: 在租金及契诺方面的法律责任的保障有哪些？
Assistant: 根据第28条，受托人履责并预留基金后可免除个人责任。
ERROR: INVALID_REQUEST - layer-slice token span exceeds context
""",
            "agent_response": "",
        },
        source_message_id=77,
        message_id=78,
    )

    assert message["message_id"] == 78
    assert message["message_type"] == MemoryType.SEMANTIC.name.lower()
    assert message["source_id"] == 77
    assert message["memory_id"] == "memory-1"
    assert "Title: 租金及契诺责任保障" in message["content"]
    assert "Related KB IDs: kb-trust-law" in message["content"]
    assert "Searching datasets" not in message["content"]
    assert "ERROR:" not in message["content"]


@pytest.mark.asyncio
async def test_handle_save_to_memory_task_does_not_fail_when_structured_summary_fails(monkeypatch):
    progress_updates = []

    class FakeTask:
        id = "task-1"
        progress = 0

    monkeypatch.setattr(memory_message_service.TaskService, "get_by_id", lambda task_id: (True, FakeTask()))
    monkeypatch.setattr(memory_message_service.TaskService, "update_by_id", lambda task_id, payload: True)
    monkeypatch.setattr(
        memory_message_service.TaskService,
        "update_progress",
        lambda task_id, payload: progress_updates.append((task_id, payload)) or True,
    )

    async def fail_structured(*args, **kwargs):
        return False, "structured summary failed"

    async def succeed_extraction(*args, **kwargs):
        return True, "Message saved successfully."

    monkeypatch.setattr(memory_message_service, "save_structured_summary_to_memory_only", fail_structured)
    monkeypatch.setattr(memory_message_service, "save_extracted_to_memory_only", succeed_extraction)

    ok, msg = await memory_message_service.handle_save_to_memory_task(
        {
            "id": "task-1",
            "memory_id": "memory-1",
            "source_id": 77,
            "message_dict": {
                "user_id": "user-1",
                "agent_id": "chat-1",
                "session_id": "session-1",
                "user_input": "User Input: important memo",
                "agent_response": "",
            },
        }
    )

    assert ok is True
    assert msg == "Message saved successfully."
    assert progress_updates[-1][1]["progress"] == 1.0
