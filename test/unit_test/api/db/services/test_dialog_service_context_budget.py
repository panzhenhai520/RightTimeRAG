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

from api.db.services import dialog_service


def test_error_history_patterns_cover_ds4_context_and_connection_errors():
    messages = [
        {"role": "user", "content": "在租金及契诺方面的法律责任的保障有哪些"},
        {
            "role": "assistant",
            "content": "**ERROR**: INVALID_REQUEST - layer-slice token span exceeds context",
        },
        {"role": "assistant", "content": "CONNECTION_ERROR - Connection error."},
        {"role": "assistant", "content": "kv payload staging failed"},
        {"role": "user", "content": "继续"},
    ]

    sanitized = dialog_service._sanitize_chat_history(messages)

    assert [message["role"] for message in sanitized] == ["user", "user"]
    assert all("ERROR" not in message["content"] for message in sanitized)
    assert all("CONNECTION_ERROR" not in message["content"] for message in sanitized)
    assert all("kv payload staging failed" not in message["content"] for message in sanitized)
    assert dialog_service._is_context_span_error("layer-slice token span exceeds context")
    assert dialog_service._is_context_span_error("kv payload staging failed")


def test_process_blocks_are_removed_before_rag_history_and_summary():
    messages = [
        {"id": "u1", "role": "user", "content": "香港PWM行业长期竞争力是什么？"},
        {
            "id": "a1",
            "role": "assistant",
            "content": "<retrieving>Searching datasets</retrieving><think>hidden reasoning</think>正式回答：人才、产品、监管。",
        },
        {"id": "u2", "role": "user", "content": "监管框架有哪些进展？"},
        {"id": "a2", "role": "assistant", "content": "包括复杂产品分类和跨境互通机制。"},
        {"id": "u3", "role": "user", "content": "还有什么？"},
        {"id": "a3", "role": "assistant", "content": "数字资产监管也很重要。"},
        {"id": "u4", "role": "user", "content": "其中监管方面展开说。"},
    ]

    rag_messages = dialog_service._rag_generation_messages(
        dialog_service._sanitize_chat_history(messages),
        "其中监管方面展开说。",
        depends_on_history=True,
        token_budget=512,
    )
    summary_messages, source_ids = dialog_service._messages_to_summarize(messages, None)

    combined = "\n".join(message["content"] for message in rag_messages + summary_messages)
    assert "<retrieving>" not in combined
    assert "<think>" not in combined
    assert "hidden reasoning" not in combined
    assert rag_messages[-1]["content"] == "其中监管方面展开说。"
    assert source_ids


def test_independent_question_drops_history_and_topic_reset_triggers():
    messages = [
        {"role": "user", "content": "张三是谁？"},
        {"role": "assistant", "content": "张三是AI领域专家。"},
        {"role": "user", "content": "你的模型参数是多少？"},
    ]
    summary = {"content": "已确认事实:\n- 张三是AI领域专家。\n重要实体:\n- 张三"}

    rag_messages = dialog_service._rag_generation_messages(
        messages,
        "你的模型参数是多少？",
        depends_on_history=False,
        token_budget=512,
    )
    reset, reason = dialog_service._should_reset_topic(
        "你的模型参数是多少？",
        summary,
        messages,
        depends_on_history=False,
    )

    assert rag_messages == [{"role": "user", "content": "你的模型参数是多少？"}]
    assert reset is True
    assert reason == "model_self_question"


def test_deepseek_v4_context_budget_keeps_safe_prompt_headroom():
    dialog = SimpleNamespace(
        llm_id="deepseek-v4-flash",
        llm_setting={"max_tokens": 512},
    )
    llm_config = {"llm_name": "DeepSeek-V4-Flash", "max_tokens": 131072}

    budget = dialog_service._resolve_context_budgets(llm_config, dialog)
    prompt_limit = dialog_service._prompt_hard_limit(budget, budget["output"])
    retry_budget = dialog_service._resolve_retry_context_budgets(budget)

    assert budget["model"] == dialog_service.DEEPSEEK_V4_EFFECTIVE_CONTEXT_TOKENS
    assert budget["output"] == dialog_service.DEEPSEEK_V4_RAG_OUTPUT_TOKENS
    assert prompt_limit <= dialog_service.DEEPSEEK_V4_PROMPT_HARD_TOKENS
    assert prompt_limit + budget["output"] <= budget["model"]
    assert retry_budget["model"] == dialog_service.DEEPSEEK_V4_RETRY_CONTEXT_TOKENS
    assert retry_budget["knowledge"] < budget["knowledge"]


def test_fit_messages_to_budget_preserves_current_question_under_hard_limit():
    context_budget = {
        "model": 65536,
        "output": 4096,
        "prompt": 61440,
        "knowledge": 18432,
        "fit": 120,
    }
    messages = [
        {"role": "system", "content": "系统提示 " * 3000},
        {"role": "assistant", "content": "旧回答 " * 3000},
        {"role": "user", "content": "当前问题：在租金及契诺方面的法律责任的保障有哪些？"},
    ]

    used_tokens, fitted, prompt_limit = dialog_service._fit_messages_to_budget(
        messages,
        context_budget,
        {"max_tokens": 4096},
        "unit_test",
    )

    assert prompt_limit == 120
    assert used_tokens <= prompt_limit
    assert [message["role"] for message in fitted] == ["system", "user"]
    assert fitted[-1]["content"].startswith("当前问题")
