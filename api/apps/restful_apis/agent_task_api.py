#
#  Copyright 2026 The InfiniFlow Authors. All Rights Reserved.
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#

from api.apps import login_required
from api.db.services.agent_goal_intent_service import AgentGoalIntentService
from api.db.services.agent_task_execution_service import AgentTaskExecutionService
from api.db.services.agent_task_approval_service import AgentTaskApprovalError, AgentTaskApprovalService, AgentTaskSecurityPolicy
from api.db.services.agent_task_model_service import AgentTaskError, AgentTaskModelService
from api.db.services.agent_task_planner_service import TaskPlanner, TaskPlanningError
from api.db.services.agent_task_precondition_service import DependencyResolver, PreconditionChecker
from api.db.services.agent_task_state_service import AgentTaskStateService
from api.db.services.agent_task_taxonomy_service import TaskFeedbackService, TaskTaxonomyError, TaskTaxonomyService
from api.db.services.agent_task_verifier_service import TaskResultVerifier
from api.utils.api_utils import get_json_result, get_request_json, server_error_response
from common.constants import RetCode


def _task_error_response(exc: AgentTaskError):
    return get_json_result(data=exc.to_dict(), code=RetCode.ARGUMENT_ERROR, message=str(exc))


def _taxonomy_error_response(exc: TaskTaxonomyError):
    return get_json_result(data=exc.to_dict(), code=RetCode.ARGUMENT_ERROR, message=str(exc))


def _approval_error_response(exc: AgentTaskApprovalError):
    return get_json_result(data=exc.to_dict(), code=RetCode.ARGUMENT_ERROR, message=str(exc))


@manager.route("/agents/tasks/analyze", methods=["POST"])  # noqa: F821
@login_required
async def analyze_agent_task_goal():
    req = await get_request_json()
    try:
        return get_json_result(
            data=AgentGoalIntentService.classify(
                str(req.get("request") or req.get("raw_request") or ""),
                context=req.get("context") if isinstance(req.get("context"), dict) else {},
            )
        )
    except Exception as exc:
        return server_error_response(exc)


@manager.route("/agents/tasks/security/assess", methods=["POST"])  # noqa: F821
@login_required
async def assess_agent_task_security():
    req = await get_request_json()
    try:
        return get_json_result(
            data=AgentTaskSecurityPolicy.assess(
                req.get("task") if isinstance(req.get("task"), dict) else {},
                policy=req.get("policy") if isinstance(req.get("policy"), dict) else {},
            )
        )
    except Exception as exc:
        return server_error_response(exc)


@manager.route("/agents/tasks/approvals", methods=["POST"])  # noqa: F821
@login_required
async def request_agent_task_approval():
    req = await get_request_json()
    try:
        return get_json_result(
            data=AgentTaskApprovalService.request(
                task=req.get("task") if isinstance(req.get("task"), dict) else {},
                requester_id=str(req.get("requester_id") or ""),
                policy=req.get("policy") if isinstance(req.get("policy"), dict) else {},
                content=req.get("content") if isinstance(req.get("content"), dict) else {},
            )
        )
    except AgentTaskApprovalError as exc:
        return _approval_error_response(exc)
    except Exception as exc:
        return server_error_response(exc)


@manager.route("/agents/tasks/approvals/<approval_id>", methods=["POST"])  # noqa: F821
@login_required
async def decide_agent_task_approval(approval_id):
    req = await get_request_json()
    try:
        return get_json_result(
            data=AgentTaskApprovalService.decide(
                approval_id,
                approved=bool(req.get("approved")),
                reviewer_id=str(req.get("reviewer_id") or ""),
                reason=str(req.get("reason") or ""),
                alternative_plan=req.get("alternative_plan") if isinstance(req.get("alternative_plan"), dict) else {},
            )
        )
    except AgentTaskApprovalError as exc:
        return _approval_error_response(exc)
    except AgentTaskError as exc:
        return _task_error_response(exc)
    except Exception as exc:
        return server_error_response(exc)


@manager.route("/agents/tasks/taxonomies", methods=["POST"])  # noqa: F821
@login_required
async def create_agent_task_taxonomy():
    req = await get_request_json()
    try:
        return get_json_result(data=TaskTaxonomyService.create_taxonomy(**req))
    except TaskTaxonomyError as exc:
        return _taxonomy_error_response(exc)
    except Exception as exc:
        return server_error_response(exc)


@manager.route("/agents/tasks/taxonomies/<name>", methods=["GET"])  # noqa: F821
@login_required
def get_agent_task_taxonomy(name):
    try:
        return get_json_result(data=TaskTaxonomyService.get_taxonomy(name=name))
    except TaskTaxonomyError as exc:
        return _taxonomy_error_response(exc)
    except Exception as exc:
        return server_error_response(exc)


@manager.route("/agents/tasks/taxonomies/<name>/<version>/examples", methods=["POST"])  # noqa: F821
@login_required
async def add_agent_task_taxonomy_example(name, version):
    req = await get_request_json()
    try:
        return get_json_result(data=TaskTaxonomyService.add_example(name=name, version=version, **req))
    except TaskTaxonomyError as exc:
        return _taxonomy_error_response(exc)
    except Exception as exc:
        return server_error_response(exc)


@manager.route("/agents/tasks/taxonomies/<name>/evaluate", methods=["POST"])  # noqa: F821
@login_required
async def evaluate_agent_task_taxonomy(name):
    req = await get_request_json()
    try:
        return get_json_result(
            data=TaskTaxonomyService.evaluate(
                name=name,
                version=str(req.get("version") or ""),
                examples=req.get("examples") if isinstance(req.get("examples"), list) else [],
            )
        )
    except TaskTaxonomyError as exc:
        return _taxonomy_error_response(exc)
    except Exception as exc:
        return server_error_response(exc)


@manager.route("/agents/tasks/feedback", methods=["POST"])  # noqa: F821
@login_required
async def record_agent_task_feedback():
    req = await get_request_json()
    try:
        return get_json_result(data=TaskFeedbackService.record(**req))
    except Exception as exc:
        return server_error_response(exc)


@manager.route("/agents/tasks/feedback", methods=["GET"])  # noqa: F821
@login_required
def list_agent_task_feedback():
    try:
        return get_json_result(data=TaskFeedbackService.list())
    except Exception as exc:
        return server_error_response(exc)


@manager.route("/agents/tasks/goals", methods=["POST"])  # noqa: F821
@login_required
async def create_agent_task_goal():
    req = await get_request_json()
    try:
        return get_json_result(data=AgentTaskModelService.create_goal(**req))
    except AgentTaskError as exc:
        return _task_error_response(exc)
    except Exception as exc:
        return server_error_response(exc)


@manager.route("/agents/tasks/plan", methods=["POST"])  # noqa: F821
@login_required
async def plan_agent_task_goal():
    req = await get_request_json()
    try:
        return get_json_result(
            data=TaskPlanner.plan(
                goal_intent=req.get("goal_intent") if isinstance(req.get("goal_intent"), dict) else {},
                context_bundle=req.get("context_bundle") if isinstance(req.get("context_bundle"), dict) else {},
                max_depth=int(req.get("max_depth") or 4),
                max_child_tasks=int(req.get("max_child_tasks") or 20),
                persist=bool(req.get("persist")),
            )
        )
    except TaskPlanningError as exc:
        return get_json_result(data=exc.to_dict(), code=RetCode.ARGUMENT_ERROR, message=str(exc))
    except AgentTaskError as exc:
        return _task_error_response(exc)
    except Exception as exc:
        return server_error_response(exc)


@manager.route("/agents/tasks", methods=["POST"])  # noqa: F821
@login_required
async def create_agent_task():
    req = await get_request_json()
    try:
        return get_json_result(data=AgentTaskModelService.create_task(**req))
    except AgentTaskError as exc:
        return _task_error_response(exc)
    except Exception as exc:
        return server_error_response(exc)


@manager.route("/agents/tasks/<task_id>", methods=["GET"])  # noqa: F821
@login_required
def get_agent_task(task_id):
    try:
        return get_json_result(data=AgentTaskModelService.get_task(task_id))
    except AgentTaskError as exc:
        return _task_error_response(exc)
    except Exception as exc:
        return server_error_response(exc)


@manager.route("/agents/tasks/<task_id>/tree", methods=["GET"])  # noqa: F821
@login_required
def get_agent_task_tree(task_id):
    try:
        return get_json_result(data=AgentTaskModelService.task_tree(task_id))
    except AgentTaskError as exc:
        return _task_error_response(exc)
    except Exception as exc:
        return server_error_response(exc)


@manager.route("/agents/tasks/<task_id>/preconditions", methods=["POST"])  # noqa: F821
@login_required
async def check_agent_task_preconditions(task_id):
    req = await get_request_json()
    try:
        return get_json_result(
            data=PreconditionChecker.check_model_task(
                task_id,
                runtime_context=req.get("runtime_context") if isinstance(req.get("runtime_context"), dict) else {},
                root=str(req.get("root") or ""),
                mark_ready=bool(req.get("mark_ready", True)),
            )
        )
    except AgentTaskError as exc:
        return _task_error_response(exc)
    except Exception as exc:
        return server_error_response(exc)


@manager.route("/agents/tasks/<task_id>/execute", methods=["POST"])  # noqa: F821
@login_required
async def execute_agent_task(task_id):
    req = await get_request_json()
    try:
        return get_json_result(
            data=AgentTaskExecutionService.execute_leaf_task(
                task_id,
                frame_id=str(req.get("frame_id") or ""),
                parent_frame_id=str(req.get("parent_frame_id") or ""),
                continuation_pointer=str(req.get("continuation_pointer") or ""),
                runtime_context=req.get("runtime_context") if isinstance(req.get("runtime_context"), dict) else {},
                root=str(req.get("root") or ""),
                max_retry=int(req.get("max_retry") or 1),
            )
        )
    except AgentTaskError as exc:
        return _task_error_response(exc)
    except Exception as exc:
        return server_error_response(exc)


@manager.route("/agents/tasks/<task_id>/verify", methods=["POST"])  # noqa: F821
@login_required
async def verify_agent_task_result(task_id):
    req = await get_request_json()
    try:
        return get_json_result(
            data=TaskResultVerifier.verify_model_task(
                task_id,
                result=req.get("result") if isinstance(req.get("result"), dict) else None,
                runtime_context=req.get("runtime_context") if isinstance(req.get("runtime_context"), dict) else {},
                checks=req.get("checks") if isinstance(req.get("checks"), list) else None,
                mark_verified=bool(req.get("mark_verified")),
            )
        )
    except AgentTaskError as exc:
        return _task_error_response(exc)
    except Exception as exc:
        return server_error_response(exc)


@manager.route("/agents/tasks/frames", methods=["POST"])  # noqa: F821
@login_required
async def control_agent_task_frame():
    req = await get_request_json()
    try:
        action = str(req.get("action") or "continue")
        if action == "enter_child":
            data = AgentTaskExecutionService.enter_child_task(
                child_task_id=str(req.get("child_task_id") or req.get("task_id") or ""),
                parent_frame_id=str(req.get("parent_frame_id") or ""),
                return_to_task_id=str(req.get("return_to_task_id") or ""),
                continuation_pointer=str(req.get("continuation_pointer") or ""),
                local_context=req.get("local_context") if isinstance(req.get("local_context"), dict) else {},
            )
        elif action == "pause":
            data = AgentTaskExecutionService.pause_frame(str(req.get("frame_id") or ""), reason=str(req.get("reason") or ""))
        elif action == "resume":
            data = AgentTaskExecutionService.resume_frame(str(req.get("frame_id") or ""))
        else:
            data = AgentTaskExecutionService.continue_from_frame(str(req.get("frame_id") or ""))
        return get_json_result(data=data)
    except AgentTaskError as exc:
        return _task_error_response(exc)
    except Exception as exc:
        return server_error_response(exc)


@manager.route("/agents/tasks/dependencies", methods=["POST"])  # noqa: F821
@login_required
async def resolve_agent_task_dependencies():
    req = await get_request_json()
    try:
        return get_json_result(
            data=DependencyResolver.resolve(
                req.get("task") if isinstance(req.get("task"), dict) else {},
                tasks=req.get("tasks") if isinstance(req.get("tasks"), list) else [],
                runtime_context=req.get("runtime_context") if isinstance(req.get("runtime_context"), dict) else {},
            )
        )
    except AgentTaskError as exc:
        return _task_error_response(exc)
    except Exception as exc:
        return server_error_response(exc)


@manager.route("/agents/tasks/<task_id>/state", methods=["POST"])  # noqa: F821
@login_required
async def update_agent_task_state(task_id):
    req = await get_request_json()
    try:
        return get_json_result(data=AgentTaskStateService.transition(task_id, str(req.get("status") or ""), reason=str(req.get("reason") or "")))
    except AgentTaskError as exc:
        return _task_error_response(exc)
    except Exception as exc:
        return server_error_response(exc)


@manager.route("/agents/tasks/<task_id>/audit", methods=["GET"])  # noqa: F821
@login_required
def get_agent_task_audit(task_id):
    try:
        task = AgentTaskModelService.get_task(task_id)
        return get_json_result(data={"audit": AgentTaskModelService.list_audit(goal_id=task["goal_id"], task_id=task_id)})
    except AgentTaskError as exc:
        return _task_error_response(exc)
    except Exception as exc:
        return server_error_response(exc)
