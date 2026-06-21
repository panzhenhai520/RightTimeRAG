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

from agent.semantic_router import (
    detect_agent_capabilities,
    route_agent_intent,
    sanitize_agent_history_text,
)


def _component(name, **params):
    return {
        "obj": SimpleNamespace(
            component_name=name,
            _param=SimpleNamespace(**params),
        )
    }


def test_ordinary_text_route_does_not_request_visual_tts_or_search():
    route = route_agent_intent(
        "总结家族办公室的经营模式",
        components={
            "begin": _component("Begin"),
            "llm": _component("LLM"),
            "message": _component("Message", auto_play=False),
        },
    )

    assert route["route"] == "ordinary_text"
    assert "vision_component_not_detected" not in route["blocked_capabilities"]
    assert "tts_component_not_detected" not in route["blocked_capabilities"]
    assert "external_search_component_not_detected" not in route["blocked_capabilities"]


def test_visual_route_requires_an_image_when_question_mentions_image():
    route = route_agent_intent(
        "请分析这张图里的合同条款",
        components={"llm": _component("LLM")},
        files=[],
    )

    assert route["route"] == "needs_visual"
    assert "missing_image_file" in route["blocked_capabilities"]
    assert "llm_or_agent" in route["allowed_capabilities"]


def test_visual_route_allows_attached_image_with_llm_component():
    route = route_agent_intent(
        "请分析附件",
        components={"llm": _component("LLM")},
        files=[{"mime_type": "image/png"}],
    )

    assert route["route"] == "needs_visual"
    assert "missing_image_file" not in route["blocked_capabilities"]
    assert "vision_component_not_detected" not in route["blocked_capabilities"]


def test_tavily_route_only_reports_available_when_workflow_has_tavily_tool():
    route = route_agent_intent(
        "搜索最新 SpaceX 股票信息",
        components={
            "agent": _component(
                "Agent",
                tools=[{"component_name": "TavilySearch"}],
            )
        },
    )

    assert route["route"] == "needs_tavily"
    assert "tavily" in route["allowed_capabilities"]
    assert route["blocked_capabilities"] == []


def test_external_search_route_reports_missing_component_when_not_configured():
    route = route_agent_intent(
        "搜索最新 SpaceX 股票信息",
        components={"llm": _component("LLM")},
    )

    assert route["route"] == "needs_external_search"
    assert "external_search_component_not_detected" in route["blocked_capabilities"]


def test_tts_route_respects_message_auto_play_capability():
    route = route_agent_intent(
        "把这段回答朗读出来",
        components={"message": _component("Message", auto_play=True)},
    )

    assert route["route"] == "needs_tts"
    assert "tts" in route["allowed_capabilities"]
    assert route["blocked_capabilities"] == []


def test_detect_agent_capabilities_reads_loaded_components_and_agent_tools():
    capabilities = detect_agent_capabilities(
        {
            "retrieval": _component("Retrieval"),
            "agent": _component("Agent", tools=[{"component_name": "TavilySearch"}]),
            "message": _component("Message", auto_play=True),
        }
    )

    assert capabilities["retrieval"] is True
    assert capabilities["tavily"] is True
    assert capabilities["external_search"] is True
    assert capabilities["tts"] is True


def test_sanitize_agent_history_removes_errors_and_process_blocks():
    text = """<retrieving>Searching datasets for: bad query</retrieving>
Thought
Reviewing retrieved evidence and composing the answer.
<think>hidden reasoning</think>
正式回答：家族信托可以用于慈善目的。
ERROR: INVALID_REQUEST - layer-slice token span exceeds context
CONNECTION_ERROR - Connection error.
"""

    cleaned = sanitize_agent_history_text(text)

    assert "正式回答" in cleaned
    assert "retrieving" not in cleaned
    assert "hidden reasoning" not in cleaned
    assert "Reviewing retrieved evidence" not in cleaned
    assert "INVALID_REQUEST" not in cleaned
    assert "CONNECTION_ERROR" not in cleaned
