from api.db.services.agent_goal_intent_service import AgentGoalIntentService


def test_goal_intent_examples_cover_supported_goal_types():
    examples = [
        ("找到最近写的智能体计划文档", "find_file"),
        ("打开 智能体自定义平台开发改进计划-v4.md 看一下", "read_document"),
        ("修改 v4.md，新增任务分解章节", "edit_document"),
        ("比较 a.md 和 b.md 的差异", "compare_documents"),
        ("抽取这份合同里的付款条款", "extract_information"),
        ("根据比对结果生成报告", "generate_report"),
        ("运行测试脚本", "run_workflow"),
        ("这个系统是什么作用", "ask_question"),
        ("", "needs_clarification"),
    ]

    for text, expected in examples:
        assert AgentGoalIntentService.classify(text)["goal_type"] == expected
