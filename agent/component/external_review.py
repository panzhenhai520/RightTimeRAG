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

import hmac
import json
import os
from abc import ABC
from datetime import datetime, timezone
from typing import Any

from agent.component.base import ComponentBase, ComponentParamBase
from api.utils.api_utils import timeout


def _parse_json_like(value: Any, default: Any = None) -> Any:
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return default
        try:
            return json.loads(text)
        except Exception:
            return default
    return value if value is not None else default


def _score(value: Any, field: str) -> float:
    try:
        result = float(value)
    except Exception as exc:
        raise ValueError(f"{field} must be numeric") from exc
    if result < 0 or result > 100:
        raise ValueError(f"{field} must be in range [0, 100]")
    return result


class WebhookInputParam(ComponentParamBase):
    def __init__(self):
        super().__init__()
        self.payload = {}
        self.token = ""
        self.expected_token = ""
        self.outputs = {
            "event": {"value": {}, "type": "JSON"},
            "verified": {"value": False, "type": "boolean"},
        }

    def check(self):
        return True


class WebhookInput(ComponentBase, ABC):
    component_name = "WebhookInput"

    @staticmethod
    def verify_token(token: str, expected_token: str) -> bool:
        if not expected_token:
            return False
        return hmac.compare_digest(str(token or ""), str(expected_token or ""))

    @timeout(int(os.environ.get("COMPONENT_EXEC_TIMEOUT", 10 * 60)))
    def _invoke(self, **kwargs):
        payload = _parse_json_like(self._param.payload, {}) or {}
        verified = self.verify_token(self._param.token, self._param.expected_token)
        if not verified:
            raise PermissionError("WebhookInput token verification failed")
        self.set_output("event", payload)
        self.set_output("verified", True)


class ExternalScoreReceiverParam(ComponentParamBase):
    def __init__(self):
        super().__init__()
        self.score_payload = {}
        self.timeout_policy = "fallback_self_score"
        self.self_score = 0
        self.outputs = {
            "score_result": {"value": {}, "type": "ScoreResult"},
            "external_score": {"value": 0, "type": "number"},
            "rubric_scores": {"value": {}, "type": "JSON"},
            "source": {"value": "", "type": "string"},
        }
        self.input_schema = {"score_payload": {"type": "JSON", "required": False}}

    def check(self):
        self.check_valid_value(
            self.timeout_policy,
            "[ExternalScoreReceiver] Timeout policy",
            ["fallback_self_score", "fail", "empty"],
        )


class ExternalScoreReceiver(ComponentBase, ABC):
    component_name = "ExternalScoreReceiver"

    @staticmethod
    def normalize_score(payload: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(payload, dict) or not payload:
            raise ValueError("external score payload is empty")
        if not payload.get("judge_id"):
            raise ValueError("external score missing judge_id")
        score = _score(payload.get("score"), "score")
        rubric_scores = payload.get("rubric_scores") or {}
        if not isinstance(rubric_scores, dict):
            raise ValueError("rubric_scores must be an object")
        normalized_rubric = {str(key): _score(value, f"rubric_scores.{key}") for key, value in rubric_scores.items()}
        return {
            "schema_version": 1,
            "source": "external_judge",
            "judge_id": str(payload.get("judge_id")),
            "score": score,
            "rubric_scores": normalized_rubric,
            "comment": str(payload.get("comment") or ""),
            "received_at": payload.get("received_at") or datetime.now(timezone.utc).isoformat(),
        }

    @staticmethod
    def fallback_score(self_score: float, reason: str = "timeout") -> dict[str, Any]:
        score = _score(self_score, "self_score")
        return {
            "schema_version": 1,
            "source": "self_score_fallback",
            "judge_id": "",
            "score": score,
            "rubric_scores": {},
            "comment": reason,
            "received_at": datetime.now(timezone.utc).isoformat(),
        }

    def _resolve_payload(self):
        value = self._param.score_payload
        if isinstance(value, str) and self._canvas.is_reff(value):
            value = self._canvas.get_variable_value(value)
        return _parse_json_like(value, {})

    @timeout(int(os.environ.get("COMPONENT_EXEC_TIMEOUT", 10 * 60)))
    def _invoke(self, **kwargs):
        payload = self._resolve_payload()
        try:
            result = self.normalize_score(payload if isinstance(payload, dict) else {})
        except Exception:
            if self._param.timeout_policy == "fallback_self_score":
                result = self.fallback_score(self._param.self_score)
            elif self._param.timeout_policy == "empty":
                result = {}
            else:
                raise
        self.set_output("score_result", result)
        self.set_output("external_score", result.get("score", 0) if isinstance(result, dict) else 0)
        self.set_output("rubric_scores", result.get("rubric_scores", {}) if isinstance(result, dict) else {})
        self.set_output("source", result.get("source", "") if isinstance(result, dict) else "")


class HumanReviewParam(ComponentParamBase):
    def __init__(self):
        super().__init__()
        self.review_data = {}
        self.status = "pending"
        self.reviewer = ""
        self.comment = ""
        self.outputs = {"review": {"value": {}, "type": "JSON"}}

    def check(self):
        self.check_valid_value(self.status, "[HumanReview] Status", ["pending", "approved", "rejected"])


class HumanReview(ComponentBase, ABC):
    component_name = "HumanReview"

    @staticmethod
    def build_review(review_data: Any, status: str, reviewer: str = "", comment: str = "") -> dict[str, Any]:
        return {
            "schema_version": 1,
            "status": status,
            "reviewer": reviewer,
            "comment": comment,
            "review_data": review_data,
            "reviewed_at": datetime.now(timezone.utc).isoformat() if status != "pending" else "",
        }

    @timeout(int(os.environ.get("COMPONENT_EXEC_TIMEOUT", 10 * 60)))
    def _invoke(self, **kwargs):
        data = _parse_json_like(self._param.review_data, self._param.review_data)
        self.set_output("review", self.build_review(data, self._param.status, self._param.reviewer, self._param.comment))


class ManualApproveParam(ComponentParamBase):
    def __init__(self):
        super().__init__()
        self.approved = False
        self.comment = ""
        self.outputs = {
            "approved": {"value": False, "type": "boolean"},
            "review": {"value": {}, "type": "JSON"},
        }
        self.input_schema = {
            "task": {"type": "JSON", "required": False},
            "policy": {"type": "JSON", "required": False},
            "approved": {"type": "Boolean", "required": False},
            "comment": {"type": "String", "required": False},
        }

    def check(self):
        return True


class ManualApprove(ComponentBase, ABC):
    component_name = "ManualApprove"

    @timeout(int(os.environ.get("COMPONENT_EXEC_TIMEOUT", 10 * 60)))
    def _invoke(self, **kwargs):
        status = "approved" if bool(self._param.approved) else "rejected"
        review = HumanReview.build_review({}, status, comment=self._param.comment)
        self.set_output("approved", bool(self._param.approved))
        self.set_output("review", review)
