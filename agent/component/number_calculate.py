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

import os
from abc import ABC
from typing import Any

from agent.component.base import ComponentBase, ComponentParamBase
from api.utils.api_utils import timeout


class NumberCalculateParam(ComponentParamBase):
    def __init__(self):
        super().__init__()
        self.operation = "weighted_score"
        self.value = ""
        self.coefficient = 1
        self.self_score = ""
        self.self_weight = 0.6
        self.external_score = ""
        self.external_weight = 0.4
        self.result_name = "综合评分"
        self.round_digits = 2
        self.outputs = {
            "result": {"value": 0, "type": "number"},
            "breakdown": {"value": {}, "type": "JSON"},
            "summary": {"value": "", "type": "string"},
        }
        self.input_schema = {
            "value": {"type": "number", "required": False},
            "coefficient": {"type": "number", "required": False},
            "self_score": {"type": "number", "required": False},
            "self_weight": {"type": "number", "required": False},
            "external_score": {"type": "number", "required": False},
            "external_weight": {"type": "number", "required": False},
        }

    def check(self):
        self.check_valid_value(
            self.operation,
            "[NumberCalculate] Operation",
            ["multiply", "weighted_score"],
        )
        if not isinstance(self.round_digits, int) or self.round_digits < 0:
            raise ValueError("[NumberCalculate] Round digits should be a non-negative integer")


class NumberCalculate(ComponentBase, ABC):
    component_name = "NumberCalculate"

    @staticmethod
    def weighted_score(self_score: float, self_weight: float, external_score: float, external_weight: float, round_digits: int = 2) -> float:
        result = float(self_score) * float(self_weight) + float(external_score) * float(external_weight)
        return round(result, int(round_digits))

    @staticmethod
    def multiply(value: float, coefficient: float, round_digits: int = 2) -> float:
        return round(float(value) * float(coefficient), int(round_digits))

    def _resolve_number(self, value: Any, default: float = 0.0) -> float:
        try:
            if isinstance(value, str) and self._canvas.is_reff(value):
                value = self._canvas.get_variable_value(value)
            elif isinstance(value, str):
                refs = self.get_input_elements_from_text(value)
                if len(refs) == 1 and value.strip().strip("{}").strip() in refs:
                    value = next(iter(refs.values())).get("value")
            return float(str(value).replace(",", "").strip())
        except Exception:
            return default

    @timeout(int(os.environ.get("COMPONENT_EXEC_TIMEOUT", 10 * 60)))
    def _invoke(self, **kwargs):
        if self.check_if_canceled("NumberCalculate processing"):
            return
        digits = int(self._param.round_digits)
        if self._param.operation == "multiply":
            value = self._resolve_number(self._param.value, 0.0)
            coefficient = self._resolve_number(self._param.coefficient, 1.0)
            result = self.multiply(value, coefficient, digits)
            breakdown = {
                "operation": "multiply",
                "value": value,
                "coefficient": coefficient,
                "result": result,
            }
            summary = f"{self._param.result_name} = {value:g} x {coefficient:g} = {result:g}"
        else:
            self_score = self._resolve_number(self._param.self_score, 0.0)
            self_weight = self._resolve_number(self._param.self_weight, 0.0)
            external_score = self._resolve_number(self._param.external_score, 0.0)
            external_weight = self._resolve_number(self._param.external_weight, 0.0)
            result = self.weighted_score(self_score, self_weight, external_score, external_weight, digits)
            breakdown = {
                "operation": "weighted_score",
                "formula": "self_score * self_weight + external_score * external_weight",
                "self_score": self_score,
                "self_weight": self_weight,
                "external_score": external_score,
                "external_weight": external_weight,
                "result": result,
            }
            summary = (
                f"{self._param.result_name} = {self_score:g} x {self_weight:g} "
                f"+ {external_score:g} x {external_weight:g} = {result:g}"
            )

        self.set_output("result", result)
        self.set_output("breakdown", breakdown)
        self.set_output("summary", summary)

    def thoughts(self) -> str:
        return "Calculating deterministic numeric result."
