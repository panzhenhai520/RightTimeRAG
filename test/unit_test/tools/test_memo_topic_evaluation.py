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

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def _load_tool_module():
    path = Path(__file__).resolve().parents[3] / "tools" / "scripts" / "evaluate_memo_topic_models.py"
    spec = importlib.util.spec_from_file_location("evaluate_memo_topic_models", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_collect_sanitized_samples_removes_evidence_and_vectors():
    module = _load_tool_module()
    payload = {
        "events": [
            {
                "id": "event-1",
                "created_at": 1710000000000,
                "topic_id": "topic:family-office",
                "topic_label": "Family office",
                "domain": "finance",
                "intent": "research",
                "turns": 3,
                "summary": "家族办公室经营模式和传承规划摘要",
                "keywords": ["家族办公室", "传承", "治理"],
                "evidence": [{"snippet": "raw evidence should not be exported"}],
                "semantic_vector": [0.1, 0.2],
                "terms": ["raw", "terms"],
            }
        ]
    }

    samples = module.collect_sanitized_samples(payload)

    assert len(samples) == 1
    exported = samples[0].to_dict()
    assert exported["topic_label"] == "Family office"
    assert "evidence" not in exported
    assert "semantic_vector" not in exported
    assert "terms" not in exported
    assert "raw evidence" not in str(exported)


def test_lightweight_evaluation_clusters_related_samples():
    module = _load_tool_module()
    payload = {
        "events": [
            {
                "id": "event-1",
                "created_at": 1710000000000,
                "topic_id": "topic:family-office",
                "topic_label": "Family office",
                "domain": "finance",
                "intent": "research",
                "turns": 2,
                "summary": "家族办公室经营模式",
                "keywords": ["家族办公室", "经营模式"],
            },
            {
                "id": "event-2",
                "created_at": 1710100000000,
                "topic_id": "topic:family-office",
                "topic_label": "家族办公室",
                "domain": "enterprise",
                "intent": "decision",
                "turns": 4,
                "summary": "家族办公室传承和治理",
                "keywords": ["家族办公室", "治理"],
            },
            {
                "id": "event-3",
                "created_at": 1710200000000,
                "topic_id": "topic:trust-law",
                "topic_label": "Trust law",
                "domain": "law",
                "intent": "risk",
                "turns": 1,
                "summary": "租金及契诺法律责任",
                "keywords": ["租金", "契诺", "责任"],
            },
        ]
    }

    result = module.evaluate_payload(payload)

    assert result["sample_count"] == 3
    assert result["lightweight_ctfidf"]["status"] == "ok"
    assert result["lightweight_ctfidf"]["topic_count"] <= 3
    assert result["decision"]["recommendation"] == "continue_current_algorithm"


def test_report_contains_comparison_and_boundary():
    module = _load_tool_module()
    result = module.evaluate_payload({"events": []})

    report = module.build_report(result)

    assert "Current Lightweight Topics" in report
    assert "BERTopic Evaluation" in report
    assert "Dynamic Topic Model Evaluation" in report
    assert "offline-only" in report
