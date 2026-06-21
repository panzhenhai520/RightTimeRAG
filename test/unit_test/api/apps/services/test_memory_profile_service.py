import importlib.util
import json
import sys
import types
from pathlib import Path


def load_memory_profile_service():
    module_path = (
        Path(__file__).resolve().parents[5]
        / "api"
        / "apps"
        / "services"
        / "memory_profile_service.py"
    )

    memory_api_service = types.ModuleType("api.apps.services.memory_api_service")
    memory_api_service._compact_memory_preview = lambda value: str(value or "")[:300]
    memory_api_service._extract_structured_summary_from_message = lambda _: {}
    memory_api_service._joined_tenant_ids = lambda user_id: {user_id}
    memory_api_service._memory_topic_text = (
        lambda memory, structured, display_name, preview: " ".join(
            str(part or "") for part in [display_name, preview, memory.get("description")]
        )
    )

    memory_service = types.ModuleType("api.db.services.memory_service")
    memory_service.MemoryService = type("MemoryService", (), {"get_by_filter": staticmethod(lambda *_, **__: ([], 0))})

    memory_utils = types.ModuleType("api.utils.memory_utils")
    memory_utils.get_memory_display_name = lambda name, description=None: description or name or ""
    memory_utils.get_memory_type_human = lambda memory_type: memory_type
    memory_utils.is_chat_memo_name = lambda name: str(name or "").startswith("chat-memo-")

    common_misc_utils = types.ModuleType("common.misc_utils")

    async def thread_pool_exec(func, *args, **kwargs):
        return func(*args, **kwargs)

    common_misc_utils.thread_pool_exec = thread_pool_exec

    messages = types.ModuleType("memory.services.messages")
    messages.MessageService = type("MessageService", (), {"list_message": staticmethod(lambda *_, **__: {"total_count": 0, "message_list": []})})

    redis_conn = types.ModuleType("rag.utils.redis_conn")

    class FakeRedisConn:
        REDIS = None

        def __init__(self):
            self.store = {}

        def get(self, key, *_):
            return self.store.get(key)

        def set(self, key, value, *_args, **_kwargs):
            self.store[key] = value
            return True

        def set_obj(self, key, value, *_args, **_kwargs):
            self.store[key] = json.dumps(value)
            return True

        def exist(self, key, *_):
            return key in self.store

    redis_conn.REDIS_CONN = FakeRedisConn()

    stubs = {
        "api.apps": types.ModuleType("api.apps"),
        "api.apps.services": types.ModuleType("api.apps.services"),
        "api.apps.services.memory_api_service": memory_api_service,
        "api.db.services.memory_service": memory_service,
        "api.utils.memory_utils": memory_utils,
        "common.misc_utils": common_misc_utils,
        "memory": types.ModuleType("memory"),
        "memory.services": types.ModuleType("memory.services"),
        "memory.services.messages": messages,
        "rag": types.ModuleType("rag"),
        "rag.utils": types.ModuleType("rag.utils"),
        "rag.utils.redis_conn": redis_conn,
    }

    old_modules = {key: sys.modules.get(key) for key in stubs}
    sys.modules.update(stubs)
    try:
        spec = importlib.util.spec_from_file_location("memory_profile_service_under_test", module_path)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        return module
    finally:
        sys.modules.pop("memory_profile_service_under_test", None)
        for key, old_module in old_modules.items():
            if old_module is None:
                sys.modules.pop(key, None)
            else:
                sys.modules[key] = old_module


def make_memory(memory_id, title, summary, created_at, kb_ids=None, message_count=3):
    return {
        "id": memory_id,
        "tenant_id": "tenant-admin",
        "name": f"chat-memo-{memory_id}",
        "description": title,
        "display_name": title,
        "memory_type": ["semantic"],
        "is_chat_memo": True,
        "message_count": message_count,
        "latest_content_preview": summary,
        "latest_agent_id": "chat-new",
        "latest_session_id": "session-1",
        "create_time": created_at,
        "structured_summary": {
            "display_title": title,
            "aliases": [],
            "entities": [],
            "facts": [{"text": summary}],
            "related_kb_ids": kb_ids or [],
        },
        "canonical_topic": {},
    }


def test_profile_analysis_builds_explainable_path():
    svc = load_memory_profile_service()
    memories = [
        make_memory(
            "m1",
            "家族办公室经营模式",
            "研究单一家族办公室、联合家族办公室和家族企业治理。",
            1_720_000_000,
            ["kb-family"],
        ),
        make_memory(
            "m2",
            "Family office investment governance",
            "Compare family office portfolio decisions and governance model.",
            1_720_086_400,
            ["kb-family"],
        ),
        make_memory(
            "m3",
            "量化模型服务家族企业理财",
            "用数学算法和量化模型分析家族企业理财方案。",
            1_720_172_800,
            ["kb-family"],
        ),
    ]

    events = svc._build_events(memories)
    clusters = svc._cluster_events(events)
    edges = svc._build_edges(events)
    summary = svc._build_summary(events, clusters, edges)
    predictions = svc._build_predictions(events, clusters, edges)

    assert len(events) == 3
    assert events[0]["domain"] == "enterprise"
    assert any(event["domain"] in {"math", "finance"} for event in events)
    assert clusters
    assert edges
    assert all(edge["reason"] for edge in edges)
    assert all(edge["evidence_event_ids"] for edge in edges)
    assert all("semantic" in edge["score_parts"] for edge in edges)
    assert "家族" in summary["headline"] or "Family" in summary["headline"]
    assert predictions
    assert predictions[0]["evidence_event_ids"]

    public_event = svc._public_event(events[0])
    assert "semantic_vector" not in public_event
    assert "terms" not in public_event
    assert public_event["semantic_model"] == svc.TOPIC_VECTOR_MODEL


def test_profile_analysis_handles_empty_and_noise_text():
    svc = load_memory_profile_service()
    assert svc._clean_text("<retrieving>noise</retrieving><think>hidden</think> 正式内容") == "正式内容"
    assert svc._build_summary([], [], [])["focus_domains"] == []
    assert svc._classify_from_rules("AI 算法 模型", svc.DOMAIN_RULES, "general") == "math"


def test_profile_semantic_vector_is_cached():
    svc = load_memory_profile_service()
    text = "家族办公室 family office governance investment"
    first_vector, first_hit = svc._semantic_vector(text)
    second_vector, second_hit = svc._semantic_vector(text)

    assert len(first_vector) == svc.TOPIC_VECTOR_DIMENSIONS
    assert first_vector == second_vector
    assert first_hit is False
    assert second_hit is True


def test_profile_topic_merge_rules_apply_and_invalidate_snapshot():
    svc = load_memory_profile_service()
    user_id = "user-admin"
    svc._json_set(svc._snapshot_key(user_id), {"status": "ready"})
    assert svc.REDIS_CONN.exist(svc._snapshot_key(user_id))

    merges = svc.upsert_topic_merge(
        user_id,
        ["topic:family-enterprise"],
        "topic:family-office",
        target_label="Family office",
        reason="same advisory theme",
    )

    assert not svc.REDIS_CONN.exist(svc._snapshot_key(user_id))
    assert merges["rules"]["topic:family-enterprise"]["target_topic_id"] == "topic:family-office"

    events = [
        {"id": "event:1", "topic_id": "topic:family-enterprise", "topic_label": "家族企业"},
        {"id": "event:2", "topic_id": "topic:trust-law", "topic_label": "Trust law"},
    ]
    merged_events = svc._apply_topic_merges(events, merges)
    assert merged_events[0]["topic_id"] == "topic:family-office"
    assert merged_events[0]["topic_label"] == "Family office"
    assert merged_events[0]["original_topic_id"] == "topic:family-enterprise"
    assert merged_events[1]["topic_id"] == "topic:trust-law"

    remaining = svc.delete_topic_merge(user_id, source_topic_ids=["topic:family-enterprise"])
    assert remaining["rules"] == {}


def test_profile_topic_merge_suggestions_use_semantic_similarity():
    svc = load_memory_profile_service()
    vector_a = [1.0] + [0.0] * (svc.TOPIC_VECTOR_DIMENSIONS - 1)
    vector_b = [0.92, 0.08] + [0.0] * (svc.TOPIC_VECTOR_DIMENSIONS - 2)
    events_by_id = {
        "event:1": {"semantic_vector": vector_a},
        "event:2": {"semantic_vector": vector_b},
    }
    clusters = [
        svc.TopicCluster(
            id="cluster:1",
            label="Family office",
            domain="enterprise",
            event_ids=["event:1"],
            keywords=["family", "office"],
            score=5,
            source_topic_ids=["topic:family-office"],
        ),
        svc.TopicCluster(
            id="cluster:2",
            label="家族办公室经营",
            domain="enterprise",
            event_ids=["event:2"],
            keywords=["家族", "办公室"],
            score=2,
            source_topic_ids=["topic:family-office-management"],
        ),
    ]

    suggestions = svc._build_topic_merge_suggestions(clusters, events_by_id)

    assert suggestions
    assert suggestions[0]["target_topic_id"] == "topic:family-office"
    assert suggestions[0]["source_topic_ids"] == ["topic:family-office-management"]
    assert suggestions[0]["semantic_score"] >= svc.TOPIC_MERGE_SUGGESTION_THRESHOLD


def test_profile_topic_cache_stabilizes_cluster_identity():
    svc = load_memory_profile_service()
    user_id = "user-cache"
    memories = [
        make_memory(
            "m1",
            "家族办公室经营模式",
            "研究单一家族办公室、联合家族办公室和家族企业治理。",
            1_720_000_000,
            ["kb-family"],
        ),
        make_memory(
            "m2",
            "Family office investment governance",
            "Compare family office portfolio decisions and governance model.",
            1_720_086_400,
            ["kb-family"],
        ),
    ]
    events = svc._build_events(memories)
    events_by_id = {event["id"]: event for event in events}
    first_clusters = svc._stabilize_topic_clusters(
        user_id,
        svc._cluster_events(events),
        events_by_id,
    )
    assert first_clusters
    first_cluster = first_clusters[0]
    cached = svc._load_topic_cache(user_id)
    assert cached["version"] == svc.TOPIC_CACHE_VERSION
    assert cached["topics"]

    rebuilt_cluster = svc.TopicCluster(
        id="cluster:999",
        label="Different generated label",
        domain=first_cluster.domain,
        event_ids=first_cluster.event_ids,
        keywords=first_cluster.keywords,
        score=first_cluster.score,
        source_topic_ids=first_cluster.source_topic_ids,
    )
    second_clusters = svc._stabilize_topic_clusters(user_id, [rebuilt_cluster], events_by_id)

    assert second_clusters[0].id == first_cluster.id
    assert second_clusters[0].label == first_cluster.label
