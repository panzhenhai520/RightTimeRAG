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

from common.feature_flags import feature_enabled, get_feature_flags


def test_feature_flags_default_to_enabled(monkeypatch):
    monkeypatch.delenv("RAGFLOW_FEATURE_MEMO_PROFILE", raising=False)
    monkeypatch.delenv("RAGFLOW_FEATURE_MEMORY_CONTEXT", raising=False)

    flags = get_feature_flags()

    assert flags["memo_profile"] is True
    assert flags["memoProfile"] is True
    assert flags["memory_context"] is True
    assert flags["topic_embedding_cache"] is True
    assert flags["topicEmbeddingCache"] is True
    assert feature_enabled("memoProfile") is True


def test_feature_flags_support_environment_overrides(monkeypatch):
    monkeypatch.setenv("RAGFLOW_FEATURE_MEMO_PROFILE", "false")
    monkeypatch.setenv("RAGFLOW_FEATURE_MEMORY_CONTEXT", "0")

    flags = get_feature_flags()

    assert flags["memo_profile"] is False
    assert flags["memoProfile"] is False
    assert flags["memory_context"] is False
    assert flags["memoryContext"] is False
    assert feature_enabled("memory_context") is False


def test_feature_flags_support_topic_embedding_alias(monkeypatch):
    monkeypatch.setenv("RAGFLOW_FEATURE_TOPIC_EMBEDDING_CACHE", "off")

    flags = get_feature_flags()

    assert flags["topic_embedding_cache"] is False
    assert flags["topicEmbeddingCache"] is False
    assert feature_enabled("topicEmbeddingCache") is False
