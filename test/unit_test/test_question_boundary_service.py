import asyncio
import importlib.util
from pathlib import Path


def _load_boundary_module():
    root = Path(__file__).resolve().parents[2]
    path = root / "api" / "db" / "services" / "question_boundary_service.py"
    spec = importlib.util.spec_from_file_location("question_boundary_service", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _plan(module, question):
    async def run():
        frame = await module.parse_question_boundary(question, question)
        return module.build_retrieval_plan(question, question, module.normalize_boundary_slots(frame))

    return asyncio.run(run())


def _filter_status(module, question, doc_name, content):
    plan = _plan(module, question)
    kbinfos = {
        "chunks": [{"docnm_kwd": doc_name, "content_with_weight": content, "doc_id": doc_name}],
        "doc_aggs": [{"doc_id": doc_name}],
    }
    module.enforce_boundary_constraints(kbinfos, plan)
    return (kbinfos.get("boundary_constraints") or {}).get("status"), kbinfos


def test_congress_near_miss_is_not_direct_evidence():
    module = _load_boundary_module()
    status, kbinfos = _filter_status(
        module,
        "党的十八大报告有关于信托行业的发展相关的政策或论述吗？",
        "党的十九大报告解读.pdf",
        "党的十九大报告明确指出，信托行业应服务人民。",
    )
    assert status == "no_direct_evidence"
    assert not kbinfos["chunks"]
    assert not kbinfos["doc_aggs"]
    assert kbinfos.get("total") == 0
    assert kbinfos["constraint_audit_chunks"][0]["constraint_result"]["status"] == "near_miss"


def test_congress_direct_evidence_is_kept():
    module = _load_boundary_module()
    status, kbinfos = _filter_status(
        module,
        "党的十八大报告有关于信托行业的发展相关的政策或论述吗？",
        "党的十八大报告资料.pdf",
        "党的十八大报告 信托行业 相关政策论述。",
    )
    assert status == "has_direct_evidence"
    assert len(kbinfos["chunks"]) == 1


def test_spatial_near_miss_is_not_direct_evidence():
    module = _load_boundary_module()
    status, kbinfos = _filter_status(
        module,
        "香港吸引家族办公室落户的措施有哪些？",
        "新加坡家族办公室政策.txt",
        "新加坡为 family offices 提供税收优惠。",
    )
    assert status == "no_direct_evidence"
    assert not kbinfos["doc_aggs"]
    assert kbinfos.get("total") == 0
    assert kbinfos["constraint_audit_chunks"][0]["constraint_result"]["status"] == "near_miss"


def test_temporal_spatial_comparison_keeps_matching_evidence():
    module = _load_boundary_module()
    status, kbinfos = _filter_status(
        module,
        "到2017年底，亚太地区的私人财富规模会不会超过西欧？",
        "Global Wealth Report 2017.pdf",
        "By the end of 2017, private wealth in Asia-Pacific is projected to surpass Western Europe.",
    )
    assert status == "has_direct_evidence"
    assert len(kbinfos["chunks"]) == 1


def test_current_version_is_not_over_strict_text_constraint():
    module = _load_boundary_module()
    status, kbinfos = _filter_status(
        module,
        "《信托法》第十五条在现行版本中如何规定？",
        "信托法.pdf",
        "第十五条 信托财产与委托人未设立信托的其他财产相区别。",
    )
    assert status == "has_direct_evidence"
    assert len(kbinfos["chunks"]) == 1


def test_empty_boundary_response_is_always_non_blank():
    module = _load_boundary_module()
    plan = _plan(module, "党的十八大报告有关于信托行业的发展相关的政策或论述吗？")
    response = module.format_boundary_no_evidence_response("党的十八大报告有关于信托行业的发展相关的政策或论述吗？", plan)
    assert response.strip()


def test_topic_terms_stay_soft_in_retrieval_plan():
    module = _load_boundary_module()
    plan = _plan(module, "党的十九大报告关于信托行业的发展是怎么讲的，有什么观点")
    assert all(
        "信托行业" not in group or len(group) == 1
        for group in plan["must_groups"]
    )
    assert any("信托行业" in term for term in plan["should_terms"])


def test_multilingual_language_queries_follow_assistant_languages():
    module = _load_boundary_module()
    async def run():
        frame = await module.parse_question_boundary(
            "党的十九大报告关于信托行业的发展是怎么讲的，有什么观点",
            "党的十九大报告关于信托行业的发展是怎么讲的，有什么观点",
        )
        return module.build_retrieval_plan(
            "党的十九大报告关于信托行业的发展是怎么讲的，有什么观点",
            "党的十九大报告关于信托行业的发展是怎么讲的，有什么观点",
            module.normalize_boundary_slots(frame),
            target_languages=["Chinese", "English"],
        )

    plan = asyncio.run(run())
    assert "Chinese" in plan["language_queries"]
    assert "Chinese (Traditional)" in plan["language_queries"]
    assert "English" in plan["language_queries"]
    assert "report" in plan["language_queries"]["English"]
    assert "信託" in plan["language_queries"]["Chinese (Traditional)"]
