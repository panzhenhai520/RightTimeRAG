#
#  Copyright 2026 The InfiniFlow Authors. All Rights Reserved.
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#

from __future__ import annotations

from copy import deepcopy
from typing import Any

from api.db.services.agent_task_model_service import AgentTaskError, AgentTaskModelService, AgentTaskStatus
from api.db.services.agent_task_state_service import AgentTaskStateService


HIGH_RISK_TASK_TYPES = {
    "write_file",
    "apply_patch",
    "workspace_file_write",
    "workspace_patch_apply",
    "run_command",
    "call_external_api",
    "send_email",
    "delete_artifact",
}

EXTERNAL_IO_TASK_TYPES = {"call_external_api", "send_email"}
WRITE_TASK_TYPES = {"write_file", "apply_patch", "workspace_file_write", "workspace_patch_apply", "delete_artifact"}
COMMAND_TASK_TYPES = {"run_command"}

DEFAULT_CONFIRMATION_POLICY = {
    "auto_allow_low_risk": True,
    "ask_before_write": True,
    "ask_before_external_io": True,
    "deny_command_execution": True,
}


class AgentTaskApprovalError(Exception):
    def __init__(self, code: str, message: str, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.code = code
        self.details = details or {}

    def to_dict(self) -> dict[str, Any]:
        return {"error_code": self.code, "message": str(self), "details": self.details}


class AgentTaskSecurityPolicy:
    @classmethod
    def assess(cls, task: dict[str, Any], *, policy: dict[str, Any] | None = None) -> dict[str, Any]:
        policy = {**DEFAULT_CONFIRMATION_POLICY, **(policy or {})}
        task_type = str(task.get("task_type") or "").strip()
        risk_level = str(task.get("risk_level") or ("high" if task_type in HIGH_RISK_TASK_TYPES else "low")).lower()
        reasons = []
        denied = False
        requires_confirmation = False
        if task_type in COMMAND_TASK_TYPES and policy.get("deny_command_execution", True):
            denied = True
            reasons.append("command_execution_denied")
        if task_type in WRITE_TASK_TYPES and policy.get("ask_before_write", True):
            requires_confirmation = True
            reasons.append("write_requires_confirmation")
        if task_type in EXTERNAL_IO_TASK_TYPES and policy.get("ask_before_external_io", True):
            requires_confirmation = True
            reasons.append("external_io_requires_confirmation")
        if risk_level == "high" or task.get("requires_user_confirmation"):
            requires_confirmation = True
            reasons.append("high_risk_requires_confirmation")
        if risk_level == "low" and not policy.get("auto_allow_low_risk", True) and not denied and not requires_confirmation:
            allowed = False
            reasons.append("low_risk_auto_allow_disabled")
        elif risk_level == "low" and policy.get("auto_allow_low_risk", True) and not denied and not requires_confirmation:
            allowed = True
        else:
            allowed = not denied and not requires_confirmation
        return {
            "schema_version": 1,
            "task_id": str(task.get("task_id") or task.get("node_id") or ""),
            "task_type": task_type,
            "risk_level": risk_level,
            "allowed": allowed,
            "denied": denied,
            "requires_confirmation": requires_confirmation,
            "reasons": sorted(set(reasons)),
            "policy": deepcopy(policy),
        }


class AgentTaskApprovalService:
    _approvals: dict[str, dict[str, Any]] = {}

    @classmethod
    def reset(cls) -> None:
        cls._approvals = {}

    @classmethod
    def request(
        cls,
        *,
        task: dict[str, Any],
        requester_id: str = "",
        policy: dict[str, Any] | None = None,
        content: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        assessment = AgentTaskSecurityPolicy.assess(task, policy=policy)
        status = "denied" if assessment["denied"] else ("pending" if assessment["requires_confirmation"] else "approved")
        approval_id = AgentTaskModelService.new_id("approval")
        record = {
            "schema_version": 1,
            "approval_id": approval_id,
            "task_id": assessment["task_id"],
            "task_type": assessment["task_type"],
            "status": status,
            "requester_id": requester_id,
            "reviewer_id": "",
            "reason": "",
            "assessment": assessment,
            "content": deepcopy(content or {}),
            "created_at": AgentTaskModelService.now(),
            "updated_at": AgentTaskModelService.now(),
        }
        cls._approvals[approval_id] = record
        cls.audit(record, action="approval_requested")
        return deepcopy(record)

    @classmethod
    def decide(
        cls,
        approval_id: str,
        *,
        approved: bool,
        reviewer_id: str = "",
        reason: str = "",
        alternative_plan: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if approval_id not in cls._approvals:
            raise AgentTaskApprovalError("APPROVAL_NOT_FOUND", "Approval record not found.", {"approval_id": approval_id})
        before = deepcopy(cls._approvals[approval_id])
        record = cls._approvals[approval_id]
        if record["status"] not in {"pending", "approved", "denied"}:
            raise AgentTaskApprovalError("APPROVAL_NOT_DECIDABLE", "Approval record cannot be decided.", {"approval_id": approval_id})
        if approved and record["assessment"].get("denied"):
            raise AgentTaskApprovalError("ACTION_DENIED_BY_POLICY", "Denied action cannot be approved under current policy.", {"approval_id": approval_id})
        record["status"] = "approved" if approved else "rejected"
        record["reviewer_id"] = reviewer_id
        record["reason"] = reason
        record["alternative_plan"] = deepcopy(alternative_plan or {})
        record["updated_at"] = AgentTaskModelService.now()
        cls._approvals[approval_id] = record
        cls.apply_decision_to_task(record)
        cls.audit(record, action="approval_decided", before=before)
        return deepcopy(record)

    @classmethod
    def enforce(cls, *, task: dict[str, Any], policy: dict[str, Any] | None = None) -> dict[str, Any]:
        assessment = AgentTaskSecurityPolicy.assess(task, policy=policy)
        if assessment["allowed"]:
            return {"allowed": True, "assessment": assessment, "approval": None}
        approvals = cls.list(task_id=assessment["task_id"])
        approved = next((item for item in approvals if item["status"] == "approved"), None)
        if approved and not assessment["denied"]:
            return {"allowed": True, "assessment": assessment, "approval": approved}
        pending = next((item for item in approvals if item["status"] == "pending"), None)
        return {"allowed": False, "assessment": assessment, "approval": pending, "reason": "approval_required_or_denied"}

    @classmethod
    def list(cls, *, task_id: str = "", status: str = "") -> list[dict[str, Any]]:
        return [
            deepcopy(item)
            for item in cls._approvals.values()
            if (not task_id or item["task_id"] == task_id) and (not status or item["status"] == status)
        ]

    @classmethod
    def get(cls, approval_id: str) -> dict[str, Any]:
        if approval_id not in cls._approvals:
            raise AgentTaskApprovalError("APPROVAL_NOT_FOUND", "Approval record not found.", {"approval_id": approval_id})
        return deepcopy(cls._approvals[approval_id])

    @classmethod
    def apply_decision_to_task(cls, record: dict[str, Any]) -> None:
        task_id = record.get("task_id")
        if not task_id:
            return
        try:
            task = AgentTaskModelService.get_task(task_id)
        except AgentTaskError:
            return
        metadata = deepcopy(task.get("metadata") or {})
        metadata.setdefault("approvals", []).append(
            {
                "approval_id": record["approval_id"],
                "status": record["status"],
                "reviewer_id": record.get("reviewer_id", ""),
                "reason": record.get("reason", ""),
            }
        )
        if record.get("alternative_plan"):
            metadata["alternative_plan"] = deepcopy(record["alternative_plan"])
        AgentTaskModelService.update_task(task_id, metadata=metadata)
        current = AgentTaskModelService.get_task(task_id)["status"]
        if record["status"] == "approved" and current in {AgentTaskStatus.PENDING.value, AgentTaskStatus.WAITING_INPUT.value, AgentTaskStatus.BLOCKED.value}:
            AgentTaskStateService.transition(task_id, AgentTaskStatus.READY.value, reason="approval granted")
        if record["status"] == "rejected" and current in {AgentTaskStatus.PENDING.value, AgentTaskStatus.READY.value, AgentTaskStatus.WAITING_INPUT.value, AgentTaskStatus.BLOCKED.value}:
            AgentTaskStateService.transition(task_id, AgentTaskStatus.CANCELED.value, reason="approval rejected")

    @classmethod
    def audit(cls, record: dict[str, Any], *, action: str, before: dict[str, Any] | None = None) -> None:
        task_id = record.get("task_id", "")
        goal_id = ""
        if task_id:
            try:
                goal_id = AgentTaskModelService.get_task(task_id)["goal_id"]
            except AgentTaskError:
                goal_id = ""
        AgentTaskModelService.record_audit(
            goal_id=goal_id,
            task_id=task_id,
            action=action,
            actor=record.get("reviewer_id") or record.get("requester_id") or "system",
            before=before,
            after=record,
        )
